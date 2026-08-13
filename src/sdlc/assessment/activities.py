"""E-46 scan activities (FR-912). One activity per computed signal,
deliberately: a signal that crashes or times out yields not_collected for
ITSELF while every other signal still reports (E-41 spec D3).

Every signal reads blob bytes at the pinned commit. NOTHING here executes the
assessed repository's code -- the init phase's build probe remains the only
place that happens (NFR-9, E-46 D12).
"""
from __future__ import annotations

import logging

from pydantic import BaseModel
from temporalio import activity

from ..activities import _git
from ..measurement import Measurement
from ..triage.activities import tracked_paths
from ..triage.gitread import is_over_size_limit, read_tree
from .scan import memo
from .scan.models import (
    CATEGORIES, ScanSignalId, ScanSignalResult, SignalOutput, SignalSource,
    SourceCandidate, family_of,
)
from .scan.registry import SCAN_SIGNALS
from .scan.signals import entrypoints, packages
from .scan.sources import SOURCE_EXTENSIONS

_log = logging.getLogger(__name__)


class AssessmentTreeInput(BaseModel):
    repo_dir: str
    commit_sha: str


class AssessmentTree(BaseModel):
    tree_hash: str


@activity.defn
async def assessment_resolve_tree(
        inp: AssessmentTreeInput) -> AssessmentTree:
    """The tree object of the pinned commit, which is what the scan memo keys
    on (D10).

    Two commits can share a tree -- amend, rebase, cherry-pick -- and a
    commit-keyed cache would miss on all of them, which E-54's incremental
    re-assessment and E-44's before/after re-triage both lean on.

    Deliberately NOT never-raising, matching triage_resolve_commit: a commit
    that does not resolve is not a not_collected dimension, it is the absence
    of the tree the whole artifact claims to describe.
    """
    proc = _git(["rev-parse", "--verify", f"{inp.commit_sha}^{{tree}}"],
                cwd=inp.repo_dir)
    if proc.returncode != 0:
        raise RuntimeError(
            f"commit {inp.commit_sha!r} does not resolve to a tree in "
            f"{inp.repo_dir}: {proc.stderr.strip()}")
    return AssessmentTree(tree_hash=proc.stdout.strip())


# Signals whose body has landed. Kept beside OWED_BY and asserted disjoint
# from it: a body that lands without its OWED_BY entry removed would report
# "not implemented" forever, and removing the entry without landing the body
# is a KeyError in unbuilt_signal.
BUILT: frozenset[ScanSignalId] = frozenset({
    ScanSignalId.S1, ScanSignalId.S3,
})

# Which plan owes each remaining signal's body.
OWED_BY: dict[ScanSignalId, str] = {
    ScanSignalId.S2: "plan 3",
    ScanSignalId.S4: "plan 3",
    ScanSignalId.SS1: "plan 3",
    ScanSignalId.SS3: "plan 3",
    ScanSignalId.SS4: "plan 3",
    ScanSignalId.QS1: "plan 3",
    ScanSignalId.QS2: "plan 3",
    ScanSignalId.QS3: "plan 3",
    ScanSignalId.QS4: "plan 3",
}


class ScanSignalInput(BaseModel):
    """One signal's activity input. `upstream` is empty for wave 1 and carries
    the consumed signals' candidates for wave 2 (spec section 5)."""
    repo_dir: str
    commit_sha: str
    tree_hash: str
    upstream: list[SourceCandidate] = []


def unbuilt_signal(signal_id: ScanSignalId) -> SignalOutput:
    """A signal whose body is a later plan. Never Measurement.measured(0.0):
    a signal that did not run has no value (FR-915).

    `source` is COMPUTED and `producer` is None regardless of the registry's
    declaration: this is the ACTIVITY's half of the row, and the workflow
    folds the inherited producer in afterwards (D7).
    """
    reason = (f"{signal_id.value} not implemented "
              f"({OWED_BY[signal_id]}, E-46)")
    return SignalOutput(row=ScanSignalResult(
        signal=signal_id, family=family_of(signal_id),
        version=SCAN_SIGNALS[signal_id].version,
        source=SignalSource.COMPUTED,
        collected=Measurement.not_collected(reason),
        categories={k: Measurement.not_collected(reason)
                    for k in CATEGORIES[signal_id]}))


def failed_signal(signal_id: ScanSignalId, exc: Exception) -> SignalOutput:
    """A signal whose body raised. Never re-raised: one signal that cannot
    read the tree must not take the other twelve down with it (E-41 D3).
    Distinct from unbuilt_signal because "we tried and could not" is not
    "nobody has written this yet" -- the reason strings must not converge."""
    reason = (f"{signal_id.value} failed: "
              f"{type(exc).__name__}: {exc}"[:300])
    return SignalOutput(row=ScanSignalResult(
        signal=signal_id, family=family_of(signal_id),
        version=SCAN_SIGNALS[signal_id].version,
        source=SignalSource.COMPUTED,
        collected=Measurement.not_collected(reason),
        categories={k: Measurement.not_collected(reason)
                    for k in CATEGORIES[signal_id]}))


def _source_blobs(repo_dir: str, commit_sha: str, paths: list[str],
                  extensions: tuple[str, ...]
                  ) -> tuple[dict[str, str], list[str]]:
    """(blobs, skipped) for source files at the pinned commit.

    `skipped` carries the oversized ones so a caller can report a partial
    count as not_collected rather than as a smaller number (spec section 6).
    """
    wanted = sorted(p for p in paths if p.endswith(extensions))
    blobs: dict[str, str] = {}
    for path, text in read_tree(repo_dir, commit_sha, wanted):
        if is_over_size_limit(text):
            continue
        blobs[path] = text
    return blobs, [p for p in wanted if p not in blobs]


@activity.defn
async def scan_packages(inp: ScanSignalInput) -> SignalOutput:
    """S1 -- package structure at depth 1-3.

    The scan memo's first production caller: plan 1 built load/store, and
    every stub it shipped was refused by store's not-MEASURED rule.
    """
    if (hit := memo.load(ScanSignalId.S1, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, skipped = _source_blobs(inp.repo_dir, inp.commit_sha, paths,
                                       SOURCE_EXTENSIONS)
        loc = {p: text.count("\n") + 1 for p, text in blobs.items()}
        out = packages.evaluate(paths, loc, skipped)
    except Exception as exc:                        # noqa: BLE001 -- see helper
        _log.warning("S1 failed: %s", exc)
        return failed_signal(ScanSignalId.S1, exc)
    memo.store(ScanSignalId.S1, inp.tree_hash, out)
    return out


@activity.defn
async def scan_schema(inp: ScanSignalInput) -> SignalOutput:
    """S2 -- database schema clusters. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.S2)


@activity.defn
async def scan_entrypoints(inp: ScanSignalInput) -> SignalOutput:
    """S3 -- backend entry points, the Contract tier."""
    if (hit := memo.load(ScanSignalId.S3, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, _ = _source_blobs(inp.repo_dir, inp.commit_sha, paths,
                                 SOURCE_EXTENSIONS)
        out = entrypoints.evaluate(blobs)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("S3 failed: %s", exc)
        return failed_signal(ScanSignalId.S3, exc)
    memo.store(ScanSignalId.S3, inp.tree_hash, out)
    return out


@activity.defn
async def scan_frontend(inp: ScanSignalInput) -> SignalOutput:
    """S4 -- frontend entry points. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.S4)


@activity.defn
async def scan_security_static(inp: ScanSignalInput) -> SignalOutput:
    """SS1 -- TLS and input validation. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.SS1)


@activity.defn
async def scan_config_infra(inp: ScanSignalInput) -> SignalOutput:
    """SS3 -- ports, env divergence, DB security, log masking. Plan 3."""
    return unbuilt_signal(ScanSignalId.SS3)


@activity.defn
async def scan_sensitivity(inp: ScanSignalInput) -> SignalOutput:
    """SS4 -- data sensitivity classification. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.SS4)


@activity.defn
async def scan_tests_inventory(inp: ScanSignalInput) -> SignalOutput:
    """QS1 -- test levels and test->file mapping. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.QS1)


@activity.defn
async def scan_coverage(inp: ScanSignalInput) -> SignalOutput:
    """QS2 -- committed report or proxy. Never runs the suite (D12). Plan 3."""
    return unbuilt_signal(ScanSignalId.QS2)


@activity.defn
async def scan_testability(inp: ScanSignalInput) -> SignalOutput:
    """QS3 -- testability findings. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.QS3)


@activity.defn
async def scan_ci(inp: ScanSignalInput) -> SignalOutput:
    """QS4 -- CI stages and env drift. Body lands in plan 3."""
    return unbuilt_signal(ScanSignalId.QS4)
