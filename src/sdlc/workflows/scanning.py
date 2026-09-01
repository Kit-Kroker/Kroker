"""E-84 D1: the scan fan-out, shared by both tiers.

AssessmentWorkflow calls this with a RepoTriage; FeatureWorkflow's brownfield
context stage calls it with triage=None. One function means the audit tier and
the pipeline physically cannot produce two different maps of one tree, because
they run the same waves against the same memo -- and a brownfield run over a
tree an assessment already scanned pays nothing.

Workflow-context code: it calls workflow.execute_activity and must only be
invoked from inside a workflow.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import timedelta

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..assessment.activities import (
        AssessmentTree,
        AssessmentTreeInput,
        ScanSignalInput,
        assessment_resolve_tree,
        scan_ci,
        scan_config_infra,
        scan_coverage,
        scan_entrypoints,
        scan_frontend,
        scan_packages,
        scan_schema,
        scan_security_static,
        scan_sensitivity,
        scan_testability,
        scan_tests_inventory,
    )
    from ..assessment.models import PhaseId, PhaseResult
    from ..assessment.scan.inherit import InheritedHalf, inherited_halves
    from ..assessment.scan.merge import MergeOutput, merge
    from ..assessment.scan.models import (
        C_MERGE,
        CATEGORIES,
        SCAN_ORDER,
        ScanResult,
        ScanSignalId,
        ScanSignalResult,
        ScanUpstream,
        SignalOutput,
        SignalSource,
        family_of,
    )
    from ..assessment.scan.registry import SCAN_SIGNALS, WAVES
    from ..measurement import CollectionState, Measurement
    from ..triage.models import RepoTriage
    from .fanout import run_or_degrade


# Deterministic given a tree; the retry covers FS/git blips only. Mirrors
# triage's SIGNAL_ACT, which these signals are the Tier 2 analogue of.
SCAN_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=2)
)
TREE_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=2), retry_policy=RetryPolicy(maximum_attempts=3)
)

# Registry `activity` names resolved to the callables. A name the registry
# declares and this table lacks is a boot-time KeyError in _scan rather than a
# silent skip, which is why test_scan_stub_activities asserts they agree.
SCAN_ACTIVITIES = {
    "scan_packages": scan_packages,
    "scan_schema": scan_schema,
    "scan_entrypoints": scan_entrypoints,
    "scan_frontend": scan_frontend,
    "scan_security_static": scan_security_static,
    "scan_config_infra": scan_config_infra,
    "scan_sensitivity": scan_sensitivity,
    "scan_tests_inventory": scan_tests_inventory,
    "scan_coverage": scan_coverage,
    "scan_testability": scan_testability,
    "scan_ci": scan_ci,
}


class ScanOutcome(BaseModel):
    """scan's two halves, mirroring InitOutcome: a failed phase yields a row
    but no artifact.

    `tree_hash` travels with them because discover keys its memo on the same
    tree scan did (DD10). Resolving it a second time would let the two phases
    describe different trees if a concurrent write landed between them.
    """

    result: PhaseResult
    scan: ScanResult | None = None
    tree_hash: str = ""


def skipped_scan_signal(signal_id: ScanSignalId, reason: str) -> ScanSignalResult:
    """A signal that did not run. Its owed categories come from the artifact's
    declaration, so a failed signal reports not_collected for exactly those
    rather than leaving them unreported (the E-42 D8a discipline)."""
    nc = Measurement.not_collected(reason)
    return ScanSignalResult(
        signal=signal_id,
        family=family_of(signal_id),
        version=SCAN_SIGNALS[signal_id].version,
        source=SignalSource.COMPUTED,
        collected=nc,
        categories={k: nc for k in CATEGORIES[signal_id]},
    )


def fold_row(activity_row: ScanSignalResult, half: InheritedHalf | None) -> ScanSignalResult:
    """Union the activity's computed half with the inherited half (D7).

    The inherited half wins its OWN categories and nothing else -- it is the
    authority on what Tier 0 measured, and the activity is the authority on
    what this phase computed. Neither can overwrite the other's keys.
    """
    if half is None:
        return activity_row
    return activity_row.model_copy(
        update={
            "source": SignalSource.EXTENDED,
            "producer": half.producer,
            "categories": activity_row.categories | half.categories,
        }
    )


def _collected_from_categories(categories: Mapping[str, Measurement]) -> Measurement:
    """A signal's overall collected state, DERIVED from its category
    measurements: measured (record count) when every owed category measured,
    else not_collected carrying a representative reason.

    The row-level analogue of compute_readiness deriving a verdict from its
    dimensions. Used for a purely-inherited signal (SS2), whose row has no
    activity to set `collected` -- hardcoding not_collected would report a
    measured inherited fact as unmeasured, the reverse of the FR-915
    conflation the type exists to prevent.
    """
    if categories and all(m.state is CollectionState.MEASURED for m in categories.values()):
        return Measurement.measured(sum(m.value or 0.0 for m in categories.values()))
    nc = next((m for m in categories.values() if m.state is not CollectionState.MEASURED), None)
    return Measurement.not_collected(
        nc.reason if nc and nc.reason else "one or more owed categories not measured"
    )


def _inherited_row(signal_id: ScanSignalId, half: InheritedHalf) -> ScanSignalResult:
    """A purely-inherited signal's row (SS2): the half IS the whole signal.

    source is INHERITED, not EXTENDED -- D12 cut the computed half, so there
    is no activity contribution to extend. `collected` is derived from the
    categories the half carried, so a triage signal that collected reads as
    collected here (FR-915).
    """
    return ScanSignalResult(
        signal=signal_id,
        family=family_of(signal_id),
        version=SCAN_SIGNALS[signal_id].version,
        source=SignalSource.INHERITED,
        collected=_collected_from_categories(half.categories),
        categories=dict(half.categories),
        producer=half.producer,
    )


def upstream_for(
    signal_id: ScanSignalId, outputs: Mapping[ScanSignalId, SignalOutput]
) -> ScanUpstream:
    """Everything one signal is allowed to read: the payloads AND the row
    states of the signals it declares in `consumes`.

    `consumes` already drives the fan-out wave (wave_of) and the memo key
    (rules_sha). Driving the payload from the SAME declaration makes reading
    undeclared data impossible rather than merely discouraged -- otherwise a
    wave-2 signal could read an S1 candidate while declaring only S3, and
    editing S1's pattern table would not move its memo key. That is the
    precise stale-cache setup D10 exists to prevent.

    `collected` travels with the payloads so a dependent signal can tell "the
    upstream measured zero" from "the upstream did not collect" (P3-D4) --
    the same pair merge() has always taken.
    """
    consumes = SCAN_SIGNALS[signal_id].consumes
    present = [c for c in consumes if c in outputs]
    return ScanUpstream(
        sources=sorted(
            (c for sid in present for c in outputs[sid].sources),
            key=lambda c: (c.signal.value, c.local_id),
        ),
        tests=sorted((t for sid in present for t in outputs[sid].tests), key=lambda t: t.path),
        collected={sid: outputs[sid].row.collected for sid in present},
    )


def _merged_row(out: MergeOutput) -> ScanSignalResult:
    """S5's row. COMPUTED with no producer: S5 inherits nothing -- it is a
    derivation over signals this phase computed, which is why it runs in
    workflow code rather than as an activity (D6)."""
    return ScanSignalResult(
        signal=ScanSignalId.S5,
        family=family_of(ScanSignalId.S5),
        version=SCAN_SIGNALS[ScanSignalId.S5].version,
        source=SignalSource.COMPUTED,
        collected=out.collected,
        categories={C_MERGE: out.collected},
    )


async def scan_tree(
    repo_dir: str, commit_sha: str, triage: RepoTriage | None = None
) -> ScanOutcome:
    """Thirteen signals over one pinned tree.

    `triage=None` is a supported call, not a degraded one: inherit.py gives
    every inherited category an explicit absent branch, so the five signals
    with an inherited half (SS1, SS2, SS3, QS1, QS4) report not_collected
    naming the missing triage signal, while S1-S5 -- which take no inherited
    half at all -- are unaffected. Requiring a triage would have meant
    requiring a human-approved Tier 2 admission before any brownfield feature
    run, making P2 depend on P6 (D5).

    Nothing here executes the scanned repository's code: every signal reads
    blob bytes at the pinned commit (NFR-9).
    """
    try:
        tree: AssessmentTree = await workflow.execute_activity(
            assessment_resolve_tree,
            AssessmentTreeInput(repo_dir=repo_dir, commit_sha=commit_sha),
            **TREE_ACT,
        )
    except Exception as e:  # noqa: BLE001
        # Without a tree hash nothing can be memoized or reproduced, so a
        # scan that proceeded would be unverifiable.
        return ScanOutcome(
            result=PhaseResult(
                phase=PhaseId.SCAN,
                collected=Measurement.not_collected(
                    f"could not resolve the tree hash: {type(e).__name__}: {e}"[:300]
                ),
            )
        )

    halves = inherited_halves(triage) if triage is not None else {}
    outputs: dict[ScanSignalId, SignalOutput] = {}

    for wave in WAVES:
        jobs = []
        for sid in wave:
            # D10: each signal's upstream is filtered to the signals it
            # declares in `consumes`, so reading undeclared data is
            # impossible and rules_sha (same `consumes`) cannot miss it.
            arg = ScanSignalInput(
                repo_dir=repo_dir,
                commit_sha=commit_sha,
                tree_hash=tree.tree_hash,
                upstream=upstream_for(sid, outputs),
            )

            def _fallback(sid: ScanSignalId = sid) -> SignalOutput:
                return SignalOutput(
                    row=skipped_scan_signal(sid, f"{sid.value} activity failed or timed out")
                )

            jobs.append(
                run_or_degrade(
                    SCAN_ACTIVITIES[SCAN_SIGNALS[sid].activity],
                    arg,
                    SCAN_ACT,
                    fallback=_fallback,
                )
            )
        results = await asyncio.gather(*jobs)
        outputs.update(zip(wave, results, strict=False))

    # SS2 is purely inherited (D12 cut its computed half), so the half IS
    # the signal: it reads INHERITED and collected when triage collected,
    # not as a skipped stub.
    for sid in SCAN_ORDER:
        if sid in outputs or SCAN_SIGNALS[sid].activity or sid is ScanSignalId.S5:
            continue
        half = halves.get(sid)
        if half is not None:
            row = _inherited_row(sid, half)
        else:
            reason = (
                f"{sid.value} is purely inherited and no triage was supplied"
                if triage is None
                else f"{sid.value} has no activity and no inherited half"
            )
            row = skipped_scan_signal(sid, reason)
        outputs[sid] = SignalOutput(row=row)

    # S5 last: it is a merge over the other source signals' candidates,
    # filtered by its declared `consumes` (the same declaration that
    # drives its wave and its memo key), so it cannot read undeclared
    # data. Its candidates are the phase's headline output.
    merged_upstream = upstream_for(ScanSignalId.S5, outputs)
    merged = merge(merged_upstream.sources, merged_upstream.collected)
    outputs[ScanSignalId.S5] = SignalOutput(row=_merged_row(merged))

    # Activity signals get their inherited half folded in (D7); the
    # synthesized rows above are already final (SS2 IS its half; S5 has
    # no half to fold), so fold_row would wrongly promote SS2 to EXTENDED.
    rows = [
        fold_row(outputs[sid].row, halves.get(sid))
        if SCAN_SIGNALS[sid].activity
        else outputs[sid].row
        for sid in SCAN_ORDER
    ]
    sources = sorted(
        (c for out in outputs.values() for c in out.sources),
        key=lambda c: (c.signal.value, c.local_id),
    )
    scan = ScanResult(
        signals=rows,
        sources=sources,
        candidates=merged.candidates,
        data_sensitivity=sorted(
            (r for out in outputs.values() for r in out.data_sensitivity),
            key=lambda r: (r.classification.value, r.entity),
        ),
        testability=sorted(
            (f for out in outputs.values() for f in out.testability),
            key=lambda f: (f.path, f.pattern, f.key),
        ),
        security=sorted(
            (o for out in outputs.values() for o in out.security),
            key=lambda o: (o.signal.value, o.category, o.path, o.rule, o.line or 0),
        ),
        tests=sorted((t for out in outputs.values() for t in out.tests), key=lambda t: t.path),
        coverage=sorted(
            (c for out in outputs.values() for c in out.coverage), key=lambda c: (c.scope, c.path)
        ),
        ci=sorted(
            (c for out in outputs.values() for c in out.ci),
            key=lambda c: (c.workflow, c.order, c.stage),
        ),
        environments=sorted(
            (e for out in outputs.values() for e in out.environments), key=lambda e: e.name
        ),
    )
    measured = sum(1 for r in rows if r.collected.state is CollectionState.MEASURED)
    return ScanOutcome(
        result=PhaseResult(phase=PhaseId.SCAN, collected=Measurement.measured(float(measured))),
        scan=scan,
        tree_hash=tree.tree_hash,
    )
