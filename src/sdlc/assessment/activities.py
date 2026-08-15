"""E-46 scan activities (FR-912). One activity per computed signal,
deliberately: a signal that crashes or times out yields not_collected for
ITSELF while every other signal still reports (E-41 spec D3).

Every signal reads blob bytes at the pinned commit. NOTHING here executes the
assessed repository's code -- the init phase's build probe remains the only
place that happens (NFR-9, E-46 D12).
"""
from __future__ import annotations

import logging

from collections.abc import Sequence
from pydantic import BaseModel, Field
from temporalio import activity

from ..activities import _git
from ..capability.matcher import resolve
from ..capability.models import (
    Advisory, IdentityAttachment, ProposedCapability,
)
from ..capability.rows import identity_rows
from ..capability.store import BoardIdentityStore
from ..measurement import Measurement
from ..triage.activities import tracked_paths
from ..triage.gitread import is_over_size_limit, read_tree
from .discover import memo as discover_memo
from .discover.context import build_context
from .discover.map import CapabilityMap, DiscoverContext, GraphSummary
from .scan import memo
from .scan.models import (
    CATEGORIES, ScanResult, ScanSignalId, ScanSignalResult, ScanUpstream,
    SignalOutput, SignalSource, family_of,
)
from .scan.registry import SCAN_SIGNALS
from .scan.signals import (
    ci as ci_signal, config_infra, coverage as coverage_signal, entrypoints,
    frontend, packages, schema, sensitivity, security_static, testability,
    tests_inventory,
)
from .scan.configpaths import is_config_path
from .scan.sources import SOURCE_EXTENSIONS
from .scan.testpaths import is_test_path

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
    ScanSignalId.S1, ScanSignalId.S2, ScanSignalId.S3, ScanSignalId.S4,
    ScanSignalId.SS1, ScanSignalId.SS3, ScanSignalId.SS4, ScanSignalId.QS1,
    ScanSignalId.QS2, ScanSignalId.QS3, ScanSignalId.QS4,
})

# Which plan owes each remaining signal's body. Empty after plan 3: every
# declared activity has landed.
OWED_BY: dict[ScanSignalId, str] = {}


def _assert_bodies_are_accounted_for() -> None:
    """A body that lands without its OWED_BY entry removed reports 'not
    implemented' forever; removing the entry without landing the body is a
    KeyError in unbuilt_signal. Asserted at import, not at the first
    assessment -- the discipline validate_registry applies to agents.yaml.
    """
    declared = {s for s, spec in SCAN_SIGNALS.items() if spec.activity}
    if BUILT | set(OWED_BY) != declared or (BUILT & set(OWED_BY)):
        raise RuntimeError(
            f"BUILT {sorted(s.value for s in BUILT)} and OWED_BY "
            f"{sorted(s.value for s in OWED_BY)} must partition the declared "
            f"activities {sorted(s.value for s in declared)}")


_assert_bodies_are_accounted_for()


class ScanSignalInput(BaseModel):
    """One signal's activity input. `upstream` is empty for wave 1 and carries
    the DECLARED consumed signals' payloads plus their row-level `collected`
    for wave 2 (spec section 5, P3-D4)."""
    repo_dir: str
    commit_sha: str
    tree_hash: str
    upstream: ScanUpstream = Field(default_factory=ScanUpstream)


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


def _blobs_for(repo_dir: str, commit_sha: str,
               paths: Sequence[str]) -> tuple[dict[str, str], list[str]]:
    """(blobs, skipped) for an explicit path list, size-guarded.

    The companion to _source_blobs, which selects by extension. A config file,
    a CI workflow and a coverage report have no extension in common, so the
    signals that read them select by name and share this reader. `skipped`
    carries the paths that were over MAX_BLOB_BYTES or unreadable, so a signal
    can record them in its owing category's reason rather than silently
    dropping them (spec section 6).
    """
    wanted = sorted(paths)
    out: dict[str, str] = {}
    for path, text in read_tree(repo_dir, commit_sha, wanted):
        if not is_over_size_limit(text):
            out[path] = text
    return out, [p for p in wanted if p not in out]


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
    """S2 -- database schema clusters.

    Reads the source extensions S1/S3 read plus schema.EXTRA_EXTENSIONS: a
    .sql or .prisma file is not source code, but it is where a schema is
    declared.
    """
    if (hit := memo.load(ScanSignalId.S2, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, skipped = _source_blobs(inp.repo_dir, inp.commit_sha, paths,
                                       SOURCE_EXTENSIONS + schema.EXTRA_EXTENSIONS)
        out = schema.evaluate(blobs, skipped)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("S2 failed: %s", exc)
        return failed_signal(ScanSignalId.S2, exc)
    memo.store(ScanSignalId.S2, inp.tree_hash, out)
    return out


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
    """S4 -- frontend entry points. Reads package.json too: a dependency list
    is the honest framework detector (an import can be a comment)."""
    if (hit := memo.load(ScanSignalId.S4, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, skipped = _source_blobs(inp.repo_dir, inp.commit_sha, paths,
                                       frontend.FRONTEND_EXTENSIONS)
        out = frontend.evaluate(blobs, skipped)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("S4 failed: %s", exc)
        return failed_signal(ScanSignalId.S4, exc)
    memo.store(ScanSignalId.S4, inp.tree_hash, out)
    return out


@activity.defn
async def scan_security_static(inp: ScanSignalInput) -> SignalOutput:
    """SS1 -- TLS enforcement and input validation. Wave 2: consumes S3."""
    if (hit := memo.load(ScanSignalId.SS1, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, skipped = _source_blobs(inp.repo_dir, inp.commit_sha, paths,
                                       SOURCE_EXTENSIONS)
        out = security_static.evaluate(blobs, inp.upstream, skipped)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("SS1 failed: %s", exc)
        return failed_signal(ScanSignalId.SS1, exc)
    memo.store(ScanSignalId.SS1, inp.tree_hash, out, inp.upstream)
    return out


@activity.defn
async def scan_config_infra(inp: ScanSignalInput) -> SignalOutput:
    """SS3 -- ports, env divergence, DB security, log masking.

    Reads config and infrastructure paths (which have no single extension)
    plus source blobs, because a log call lives in code.
    """
    if (hit := memo.load(ScanSignalId.SS3, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        wanted = sorted({p for p in paths
                         if is_config_path(p)
                         or p.endswith(SOURCE_EXTENSIONS)})
        blobs, skipped = _blobs_for(inp.repo_dir, inp.commit_sha, wanted)
        out = config_infra.evaluate(blobs, skipped)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("SS3 failed: %s", exc)
        return failed_signal(ScanSignalId.SS3, exc)
    memo.store(ScanSignalId.SS3, inp.tree_hash, out)
    return out


@activity.defn
async def scan_sensitivity(inp: ScanSignalInput) -> SignalOutput:
    """SS4 -- data sensitivity. Wave 2: consumes S2's tables and S3's entry
    points, so its output is only cacheable when both collected (P3-D5)."""
    if (hit := memo.load(ScanSignalId.SS4, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, skipped = _source_blobs(inp.repo_dir, inp.commit_sha, paths,
                                       SOURCE_EXTENSIONS + schema.EXTRA_EXTENSIONS)
        out = sensitivity.evaluate(blobs, inp.upstream, skipped)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("SS4 failed: %s", exc)
        return failed_signal(ScanSignalId.SS4, exc)
    memo.store(ScanSignalId.SS4, inp.tree_hash, out, inp.upstream)
    return out


@activity.defn
async def scan_tests_inventory(inp: ScanSignalInput) -> SignalOutput:
    """QS1 -- test levels and the test->file mapping. Reads only the test
    files' blobs; the mapping targets come from the path list."""
    if (hit := memo.load(ScanSignalId.QS1, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        test_paths = [p for p in paths if is_test_path(p)]
        blobs, skipped = _blobs_for(inp.repo_dir, inp.commit_sha, test_paths)
        out = tests_inventory.evaluate(paths, blobs, skipped)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("QS1 failed: %s", exc)
        return failed_signal(ScanSignalId.QS1, exc)
    memo.store(ScanSignalId.QS1, inp.tree_hash, out)
    return out


@activity.defn
async def scan_coverage(inp: ScanSignalInput) -> SignalOutput:
    """QS2 -- a committed report, else QS1's proxy. NEVER runs the suite
    (D12). Wave 2: consumes QS1."""
    if (hit := memo.load(ScanSignalId.QS2, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        tracked = set(paths)
        reports, skipped_reports = _blobs_for(
            inp.repo_dir, inp.commit_sha,
            [p for p in coverage_signal.REPORT_PATHS if p in tracked])
        out = coverage_signal.evaluate(paths, reports, inp.upstream,
                                       skipped_reports)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("QS2 failed: %s", exc)
        return failed_signal(ScanSignalId.QS2, exc)
    memo.store(ScanSignalId.QS2, inp.tree_hash, out, inp.upstream)
    return out


@activity.defn
async def scan_testability(inp: ScanSignalInput) -> SignalOutput:
    """QS3 -- testability findings over production source blobs."""
    if (hit := memo.load(ScanSignalId.QS3, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, skipped = _source_blobs(inp.repo_dir, inp.commit_sha, paths,
                                       SOURCE_EXTENSIONS)
        out = testability.evaluate(blobs, skipped)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("QS3 failed: %s", exc)
        return failed_signal(ScanSignalId.QS3, exc)
    memo.store(ScanSignalId.QS3, inp.tree_hash, out)
    return out


@activity.defn
async def scan_ci(inp: ScanSignalInput) -> SignalOutput:
    """QS4 -- CI stages and environment drift. Reads the pipeline files; the
    config side of the drift comparison comes from the path list alone."""
    if (hit := memo.load(ScanSignalId.QS4, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        ci_paths = [p for p in paths if ci_signal.is_ci_path(p)]
        blobs, skipped = _blobs_for(inp.repo_dir, inp.commit_sha, ci_paths)
        out = ci_signal.evaluate(paths, blobs, skipped)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("QS4 failed: %s", exc)
        return failed_signal(ScanSignalId.QS4, exc)
    memo.store(ScanSignalId.QS4, inp.tree_hash, out)
    return out


class DiscoverContextInput(BaseModel):
    """Discover's read of the tree. `tree_hash` is carried for DD10's memo
    key even though this activity does not itself memoize -- the phase does."""
    repo_dir: str
    commit_sha: str
    tree_hash: str
    scan: ScanResult


def _no_context(reason: str) -> DiscoverContext:
    """A packet that could not be built. Never an empty MEASURED packet: a
    tree we could not read is not a tree with no capabilities (FR-915)."""
    return DiscoverContext(
        collected=Measurement.not_collected(reason),
        graph=GraphSummary(
            parsed=0, unparsed=0, edges=0,
            unresolved_relative_rate=Measurement.not_collected(reason)))


@activity.defn
async def discover_context(inp: DiscoverContextInput) -> DiscoverContext:
    """Read the tree at the pinned commit and compute everything code can
    say about the candidate set (E-48 DD1).

    Degrades rather than raising, exactly as the scan signals do: one
    unreadable tree must report not_collected, not surface as a traceback the
    phase has to interpret.
    """
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, skipped = _source_blobs(inp.repo_dir, inp.commit_sha, paths,
                                       SOURCE_EXTENSIONS)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("discover_context tree read failed: %s", exc)
        return _no_context(
            f"could not read the tree: {type(exc).__name__}: {exc}"[:300])

    try:
        return build_context(inp.scan, blobs, skipped)
    except Exception as exc:                        # noqa: BLE001
        _log.warning("discover_context build_context failed: %s", exc)
        return _no_context(
            f"could not build context: {type(exc).__name__}: {exc}"[:300])


class DiscoverMemoInput(BaseModel):
    """DD10's key terms the workflow supplies. `identity_registry_version` is
    deliberately absent: it is store state, and a workflow that carried a
    stale one would key against a registry that had already moved."""
    project: str
    tree_hash: str
    context_digest: str
    prompt_sha: str
    model: str


class DiscoverMemoStoreInput(BaseModel):
    key: DiscoverMemoInput
    # The version discover_lock returned. Read fresh here rather than passed
    # in would be equivalent today and racy tomorrow; see P2-D3.
    registry_version: int
    out: CapabilityMap


@activity.defn
async def discover_memo_load(inp: DiscoverMemoInput) -> CapabilityMap | None:
    """DD10's lookup. Reads the registry version itself (P2-D3): before the
    lock, the store's current version IS the one this run's map would be
    keyed at."""
    store = BoardIdentityStore()
    try:
        version = store.registry_version(inp.project)
    finally:
        store.close()
    return discover_memo.load(
        project=inp.project, tree_hash=inp.tree_hash,
        context_digest=inp.context_digest, registry_version=version,
        prompt_sha=inp.prompt_sha, model=inp.model)


@activity.defn
async def discover_memo_store(inp: DiscoverMemoStoreInput) -> bool:
    """DD10's write, keyed at the POST-lock registry version -- the version
    whose ids the map actually carries. Keying it at the pre-lock version
    would guarantee a miss on every subsequent run (P2-D3)."""
    return discover_memo.store(
        project=inp.key.project, tree_hash=inp.key.tree_hash,
        context_digest=inp.key.context_digest,
        registry_version=inp.registry_version,
        prompt_sha=inp.key.prompt_sha, model=inp.key.model, out=inp.out)


class DiscoverLockInput(BaseModel):
    """Clause D4's input: the boundaries that survived disposition, each with
    the fingerprint this assessment observed."""
    project: str
    run_id: str
    proposed: list[ProposedCapability] = Field(default_factory=list)


class DiscoverLockOutcome(BaseModel):
    attachments: list[IdentityAttachment] = Field(default_factory=list)
    advisories: list[Advisory] = Field(default_factory=list)
    registry_version: int


@activity.defn
async def discover_lock(inp: DiscoverLockInput) -> DiscoverLockOutcome:
    """Attach a durable BC-NNN to every surviving boundary (D4, DD5).

    Deliberately NOT never-raising, unlike every other activity in this phase.
    A scan signal that cannot read the tree degrades to not_collected because
    the other twelve still report; an identity store that cannot be read or
    written has no such containment -- proceeding "produces a complete,
    plausible-looking map in which every id is wrong, and the next successful
    write commits that corruption" (E-47a). The workflow turns the raise into
    a not_collected PHASE (DD9).

    Its RetryPolicy is what implements E-47a's concurrency rule: an
    IdentityConflictError means another assessment wrote first, and a retry
    re-reads the registry and re-matches rather than replaying computed
    attachments. Ordinals burned by a failed attempt are gaps, never reuse --
    the allocator's documented behaviour.
    """
    store = BoardIdentityStore()
    try:
        version = store.registry_version(inp.project)
        registry = store.load(inp.project)
        result = resolve(inp.proposed, registry,
                         allocate=store.allocator(inp.project))
        rows = identity_rows(
            inp.project, inp.run_id, result,
            {p.local_key: p.fingerprint for p in inp.proposed}, registry)
        # P2-D7: a write with no rows bumps the version and records nothing,
        # invalidating every project memo for a change that did not happen.
        new_version = (
            store.apply(inp.project, rows, expected_version=version,
                        actor="assessment", operation="resolve")
            if rows else version)
    finally:
        store.close()
    return DiscoverLockOutcome(attachments=result.attachments,
                               advisories=result.advisories,
                               registry_version=new_version)


