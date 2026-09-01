"""E-84: ScanResult -> CodebaseMap.

A projection, not an extraction. Every fact here was produced by the scan
signals E-46 built; this module chooses which of them the Architect needs and
in what order. Building a second extractor over the same tree would yield two
maps that can disagree about one repository, with no rule for which is right
(D1).

Pure: no temporalio, no activities, no I/O.
"""

from __future__ import annotations

import hashlib

from ..assessment.discover.models import CONTRACT_KINDS
from ..assessment.scan.models import ScanResult, ScanSignalId
from ..measurement import CollectionState, Measurement
from .models import CodebaseMap, HotSpot, MapContract, MapModule


def _row_collected(scan: ScanResult, sid: ScanSignalId) -> Measurement:
    """One signal's collection state, or a not_collected naming its absence."""
    row = next((r for r in scan.signals if r.signal is sid), None)
    if row is None:
        return Measurement.not_collected(f"{sid.value} is not present in this scan")
    return row.collected


def _reason(m: Measurement, sid: ScanSignalId) -> str:
    return f"{sid.value}: {m.reason or m.state.value}"


def project(scan: ScanResult, tree_hash: str, commit_sha: str) -> CodebaseMap:
    """The map for one scanned tree.

    Modules and contracts share ONE collection state because they share one
    source: both are read off S5's merged candidates, so a claim that
    contracts collected while modules did not would be a claim about nothing.
    Hot spots have their own, because QS2 and QS3 degrade independently.
    """
    s5 = _row_collected(scan, ScanSignalId.S5)
    if s5.state is CollectionState.MEASURED:
        modules = tuple(
            sorted(
                (
                    MapModule(
                        name=c.name,
                        member_paths=tuple(sorted({m.path for m in c.members if m.path})),
                        confidence=c.confidence,
                    )
                    for c in scan.candidates
                ),
                key=lambda x: (x.name, x.member_paths),
            )
        )
        contracts = tuple(
            sorted(
                (
                    MapContract(kind=m.kind, value=m.value, path=m.path, line=m.line)
                    for c in scan.candidates
                    for m in c.members
                    if m.kind in CONTRACT_KINDS
                ),
                key=lambda x: (x.kind.value, x.value, x.path, x.line or 0),
            )
        )
        members = Measurement.measured(float(len(modules)))
        contracts_collected = Measurement.measured(float(len(contracts)))
    else:
        modules, contracts = (), ()
        members = Measurement.not_collected(f"no modules: {_reason(s5, ScanSignalId.S5)}")
        contracts_collected = Measurement.not_collected(
            f"no contracts: {_reason(s5, ScanSignalId.S5)}"
        )

    qs2 = _row_collected(scan, ScanSignalId.QS2)
    qs3 = _row_collected(scan, ScanSignalId.QS3)
    if qs2.state is CollectionState.MEASURED or qs3.state is CollectionState.MEASURED:
        spots: list[HotSpot] = []
        if qs3.state is CollectionState.MEASURED:
            spots.extend(
                HotSpot(
                    path=f.path,
                    source="testability",
                    reason=f"{f.severity}: {f.pattern}",
                    metric=Measurement.measured(float(_SEVERITY_RANK[f.severity])),
                )
                for f in scan.testability
            )
        if qs2.state is CollectionState.MEASURED:
            spots.extend(
                HotSpot(
                    path=r.path,
                    source="coverage",
                    reason=f"coverage from {r.source}{' (' + r.tool + ')' if r.tool else ''}",
                    metric=r.covered,
                )
                for r in scan.coverage
                if r.scope == "file" and r.covered.state is CollectionState.MEASURED
            )
        hot_spots = tuple(sorted(spots, key=lambda h: (h.path, h.source, h.reason)))
        hot_collected = Measurement.measured(float(len(hot_spots)))
    else:
        hot_spots = ()
        hot_collected = Measurement.not_collected(
            f"no hot spots: {_reason(qs2, ScanSignalId.QS2)}; {_reason(qs3, ScanSignalId.QS3)}"
        )

    # The map's defining content is its modules: without them there is nothing
    # for the delta to be grounded against, which is what D6 fails closed on.
    if members.state is CollectionState.MEASURED:
        collected = Measurement.measured(float(len(modules)))
    else:
        modules, contracts, hot_spots = (), (), ()
        collected = Measurement.not_collected(members.reason)
    return CodebaseMap(
        tree_hash=tree_hash,
        commit_sha=commit_sha,
        modules=modules,
        contracts=contracts,
        hot_spots=hot_spots,
        modules_collected=members,
        contracts_collected=contracts_collected,
        hot_spots_collected=hot_collected,
        collected=collected,
    )


_SEVERITY_RANK = {"blocks": 3, "impedes": 2, "smell": 1}


def map_digest(m: CodebaseMap) -> str:
    """A canonical digest for the architect memo key (D11).

    Digests the model rather than hand-listing fields, following brief_digest
    and E-48's context_digest: a field added later cannot escape the key.
    Canonical because project() sorts every collection it emits, which
    test_projection_is_order_independent asserts as byte-identical JSON.
    """
    return hashlib.sha256(m.model_dump_json().encode("utf-8")).hexdigest()
