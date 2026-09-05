# E-48 discover proposers — plan 2 of 3: the deterministic spine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the DISCOVER phase from `unbuilt` to **measured with no model in it** — DD6's baseline disposes, DD8's structural checks verify, `resolve()` locks identity, `attribute()`/`decompose()`/`assign()` finalize, DD10's memo caches the result, and `terminal_status` derives `assessed:partial`.

**Architecture:** One new pure module (`discover/apply.py`), one new pure identity helper (`capability/rows.py`), one activity-side memo (`discover/memo.py` + a `discover_key` sibling in `memoization/cache.py`), four new activities, and `_discover` wired in the workflow. Plan 3 inserts a proposer between `baseline_dispositions` and `stamp` and adds nothing else to this spine — which is why the three are separate functions rather than one.

**Tech Stack:** Python 3.14, Pydantic v2, Temporal (`temporalio`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-15-e48-discover-proposers-design.md`
**Predecessor:** `docs/superpowers/plans/2026-08-15-e48-discover-plan-1.md` (landed `02b6c20`…`66879a9`)

## Global Constraints

- **Purity.** `discover/` modules import Pydantic, `measurement.py`, `capability/models.py`, and scan **rule** modules only. They must never import `sdlc/models.py`, `sdlc/assessment/activities.py`, or `temporalio`. A signal module (`scan/signals/*.py`) must never be imported — a signal is a producer with a memo key and a version, and importing one would make this package part of that signal's hashed surface (E-47c D2). **One carve-out, exactly as scan has:** `discover/memo.py` does filesystem I/O and is ACTIVITY-side code a workflow must never call, mirroring `scan/memo.py`'s docstring.
- **`Measurement`, never a bare number.** A value that was never measured must not be representable as a measured value (FR-915). `Measurement.measured(0.0)` is a claim that the answer is zero; use `Measurement.not_collected(reason)` when it is not.
- **Derived, never assigned.** Counts are computed from rows inside a `model_validator`, so a deserialized payload cannot disagree with its own arithmetic.
- **Sorted-and-deduped is asserted, not repaired.** A producer emitting discovery order is an NFR-10 determinism bug; silently sorting it in a validator hides the bug. Raise instead.
- **No repository code executes.** Every input is a blob read at the pinned commit or a parameter (NFR-9).
- **Commit message trailer**, on every commit in this plan:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Test command:** `uv run pytest <path> -v`

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/sdlc/assessment/discover/apply.py` | DD6 baseline, DD8 stamping, disposition application, fingerprints, the map constructor | 1, 2, 3, 4 |
| `src/sdlc/capability/rows.py` | `ResolutionResult` → the registry rows to persist | 5 |
| `src/sdlc/memoization/cache.py` | `discover_key`, `NO_PROPOSER` | 6 |
| `src/sdlc/assessment/discover/map.py` | `context_digest` | 6 |
| `src/sdlc/assessment/discover/memo.py` | DD10's load/store | 6 |
| `src/sdlc/assessment/discover/context.py` | `schema_collected`, `contract_collected` | 8 |
| `src/sdlc/assessment/activities.py` | `discover_memo_load`, `discover_memo_store`, `discover_lock`, `discover_finalize` | 6, 7, 8 |
| `src/sdlc/workflows/assessment.py` | `_discover` wired, `PHASE_OWNER`, `AssessmentInput.project_key`, `ScanOutcome.tree_hash` | 9 |
| `src/sdlc/worker.py` | activity registration | 9 |

`apply.py` is one module across four tasks because its three functions are one pipeline over one vocabulary; splitting them across files would put `baseline` and `stamp` — which must never converge — where a reader cannot see them together.

## Plan-2 decisions

Recorded here because the spec's DD1–DD13 do not contain them, and a later reader will otherwise read them as accidents.

**P2-D1 — the guardrail outranks the duplicate flag.** DD6's table is read top to bottom, so a candidate that is both layer-named and a possible duplicate is `DE_SCOPE`, not `FLAG`. A candidate named like a layer is not a capability whichever other candidate it overlaps, and `FLAG`ging it would ask a human to adjudicate a boundary clause D2 already rejects. Declaration order **is** precedence order, following `BUCKET_PRECEDENCE`.

**P2-D2 — a boundary whose member set changed loses its cohesion and coupling.** `build_context` computed both over the candidate's *original* members and then discarded the reference graph (DD4), so a split part and a merge winner cannot have theirs recomputed. Reporting the old number would attach a measurement to a thing it does not describe, which is the FR-915 conflation. `not_collected` naming the change is the honest answer.

**P2-D3 — the memo's registry version is read fresh on both sides.** `discover_memo_load` reads `registry_version` before the lock; `discover_memo_store` reads it after, where it is the post-lock value because `discover_lock` has already called `store.apply()`. That asymmetry is what makes DD10's claim true — a hit implies the stored map's ids are still the registry's. If a concurrent assessment writes between our lock and our store, our key lands one version ahead and the next run misses. A miss costs a recompute; the alternative direction (a hit against a registry that moved) costs a wrong map, so the race resolves the safe way.

**P2-D4 — `capability/rows.py`, not `discover/`.** `resolve()` returns a `ResolutionResult` of attachments, retirements and merges; nothing turns those into `CapabilityIdentity` rows. That is identity-persistence semantics, not discover's, and E-54's re-assessment is a second caller. Siting it in `discover/` would guarantee two copies that agree only by coincidence.

**P2-D5 — `contract_collected` needs S3 **and** S4.** `decompose()` documents its argument as "S3's (and S4's) collection state", and `CONTRACT_KINDS` includes `FRONTEND_ROUTE`, which only S4 emits. One `Measurement` must therefore represent both: measured only when both measured, else `not_collected` naming the degraded one. Deriving it from S3 alone would let a dead S4 read as a capability that genuinely exposes no frontend route.

**P2-D6 — the memo key never carries an empty `prompt_sha` or `model`.** With no proposer there is no prompt and no model, and `""` is exactly what `signal_key`'s docstring refuses: it "would make 'no model was involved' indistinguishable from a bug that dropped the model id — in the one place where a silently wrong value serves stale results indefinitely." Both terms carry the explicit `NO_PROPOSER` sentinel, so a baseline-only map and a proposer map can never share a key. Plan 3 changes the caller, not the memo.

**P2-D7 — a lock that writes no rows does not move the registry version.** `store.apply()` bumps `registry_version` unconditionally and writes one audit event per row; with zero rows it would bump the version and record nothing, invalidating every project memo for a write that did not happen.

**P2-D8 — entity declarations are re-derived from the blobs, not reconstructed from the `ScanResult`.** `EntityDeclaration` needs `(name, path, line)`. S2's `SourceCandidate` carries names on `members` and lines on `evidence`, with no join between them, so a file declaring two tables cannot be reconstructed. `discover_finalize` calls `schema.declarations()` at the call site instead — which is what `EntityDeclaration`'s docstring anticipated ("E-48 adapts S2's `TableDecl` at the call site, where both are already in scope"). It is a pure function over blobs at the pinned commit, so the result is identical to what S2 saw; the adaptation lives in `activities.py`, which already imports signal modules, so `discover/` still imports no signal.

**P2-D9 — `RetiredReason.ABSORBED` gains no producer.** `resolve()` reports absorption as `merged`, and `CapabilityIdentity._status_fields_agree` forbids a `retired_reason` on a `MERGED` row, so a merge loser is `(MERGED, merged_into=winner, retired_reason=None)` — `corrections._absorb`'s exact shape. The enum value stays reserved and unemitted, like `OwnershipVerb.TRACKS`, rather than being given a synthetic trigger.

---

### Task 1: DD6's baseline disposition

The rule that makes plan 2 a live phase rather than a stub. It is also DD7's fallback when the proposer role is absent, which is the only path plan 2 exercises.

**Files:**
- Create: `src/sdlc/assessment/discover/apply.py`
- Test: `tests/test_discover_baseline.py`

**Interfaces:**
- Consumes: `CandidateContext`, `DiscoverContext`, `CandidateDisposition`, `DiscoverAction`, `DispositionSource` from `sdlc.assessment.discover.map`
- Produces: `baseline(context: CandidateContext) -> CandidateDisposition`, `baseline_dispositions(context: DiscoverContext) -> tuple[CandidateDisposition, ...]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_baseline.py
"""FR-913 (E-48 DD6): the disposition code computes before any model runs."""

from __future__ import annotations

from sdlc.assessment.discover.apply import baseline, baseline_dispositions
from sdlc.assessment.discover.map import (
    DiscoverAction,
    DiscoverContext,
    DispositionSource,
    CandidateContext,
    GraphSummary,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import Measurement

MEASURED = Measurement.measured(1.0)
GRAPH = GraphSummary(
    parsed=4, unparsed=0, edges=3, unresolved_relative_rate=Measurement.measured(0.0)
)


def _ctx(candidate_id="C-01", **kw):
    base = dict(
        candidate_id=candidate_id,
        name="payments",
        confidence=Confidence.HIGH,
        sources=("S3-payments",),
        source_rules=("s3_http_route",),
        members=(
            CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="pay/api.py"),
        ),
        member_paths=("pay/api.py",),
        cohesion=MEASURED,
        coupling=MEASURED,
        guardrail_only=False,
    )
    return CandidateContext(**(base | kw))


def _layer(candidate_id="C-02", **kw):
    return _ctx(
        candidate_id, name="services", source_rules=("s1_layer_name",), guardrail_only=True, **kw
    )


def test_a_layer_named_candidate_is_de_scoped():
    """Clause D2's guardrail, computed rather than asked: delivery channels
    and deployment boundaries are not capabilities."""
    d = baseline(_layer())
    assert d.action is DiscoverAction.DE_SCOPE
    assert d.rule == "baseline_guardrail"


def test_a_possible_duplicate_is_flagged():
    """The honest limit of code: S5 detects the overlap, but only judgment
    decides MERGE versus genuinely-distinct."""
    d = baseline(_ctx(possible_duplicate_of=("C-02",)))
    assert d.action is DiscoverAction.FLAG
    assert d.rule == "baseline_possible_duplicate"


def test_everything_else_is_confirmed():
    d = baseline(_ctx())
    assert d.action is DiscoverAction.CONFIRM
    assert d.rule == "baseline_confirm"


def test_the_guardrail_outranks_the_duplicate_flag():
    """P2-D1: DD6's table is read top to bottom. A candidate named like a
    layer is not a capability whichever other candidate it overlaps, and
    FLAGging it would ask a human to adjudicate a boundary D2 rejects."""
    d = baseline(_layer(possible_duplicate_of=("C-01",)))
    assert d.action is DiscoverAction.DE_SCOPE


def test_a_baseline_names_its_rule_and_carries_no_rationale():
    """A baseline's rule IS its rationale; only a model verdict owes one."""
    d = baseline(_ctx())
    assert d.source is DispositionSource.BASELINE
    assert d.rationale == ""


def test_one_disposition_per_candidate_in_candidate_order():
    ctx = DiscoverContext(
        candidates=(_ctx(), _layer()), graph=GRAPH, collected=Measurement.measured(2.0)
    )
    got = baseline_dispositions(ctx)
    assert [d.candidate_id for d in got] == ["C-01", "C-02"]
    assert [d.action for d in got] == [DiscoverAction.CONFIRM, DiscoverAction.DE_SCOPE]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_baseline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.discover.apply'`

- [ ] **Step 3: Write the implementation**

```python
# src/sdlc/assessment/discover/apply.py
"""FR-913 (E-48 DD6/DD7/DD8): dispositions in, the locked candidate set out.

Pure by design -- Pydantic, measurement.py and capability/models.py only. This
module must never import models.py, activities.py, or temporalio, exactly as
the rest of discover/ must not.

Four things happen here and they are deliberately separate functions:
`baseline_dispositions` is DD6's code-computed verdict, `stamp` is DD8's
structural verification plus DD7's two fallbacks, `apply` turns verified
dispositions into the boundaries the lock will identify, and `build_map` is
the artifact's one constructor. Splitting them is what lets plan 3 insert a
proposer between the first and the second without touching either.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ValidationError, model_validator

from ...capability.models import Advisory, CapabilityFingerprint
from ...measurement import Measurement
from ..scan.models import CandidateMember, Confidence
from .map import (
    REJECTING_ACTIONS,
    Capability,
    CandidateContext,
    CandidateDisposition,
    CapabilityMap,
    DiscoverAction,
    DiscoverContext,
    DiscoverProposal,
    DispositionSource,
    ProposedDisposition,
)
from .models import AttributionReport, DecompositionReport, OwnershipReport
from .tiers import group_by_tier


def baseline(context: CandidateContext) -> CandidateDisposition:
    """DD6's table, read top to bottom. Declaration order IS precedence
    order, following BUCKET_PRECEDENCE -- there is no second list to disagree
    with this one.

    The guardrail outranks the duplicate flag deliberately (P2-D1): a
    candidate named like a layer is not a capability whichever other
    candidate it overlaps, and FLAGging it would ask a human to adjudicate a
    boundary clause D2 already rejects.
    """
    row = dict(candidate_id=context.candidate_id, source=DispositionSource.BASELINE)
    if context.guardrail_only:
        return CandidateDisposition(
            **row, action=DiscoverAction.DE_SCOPE, rule="baseline_guardrail"
        )
    if context.possible_duplicate_of:
        return CandidateDisposition(
            **row, action=DiscoverAction.FLAG, rule="baseline_possible_duplicate"
        )
    return CandidateDisposition(**row, action=DiscoverAction.CONFIRM, rule="baseline_confirm")


def baseline_dispositions(context: DiscoverContext) -> tuple[CandidateDisposition, ...]:
    """One baseline per candidate, in the context's order -- which
    build_context already sorted by candidate_id (NFR-10)."""
    return tuple(baseline(c) for c in context.candidates)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_baseline.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/apply.py tests/test_discover_baseline.py
git commit -m "feat(discover): DD6's baseline disposition, guardrail first (E-48 DD6)"
```

---

### Task 2: DD8's structural verification and DD7's two fallbacks

`stamp()` is where a model's output stops being a suggestion. It enforces DD8 items 1–3 (every `candidate_id` resolves; exactly one disposition per candidate; MERGE targets and SPLIT partitions are real) and holds DD7's rule that a **dropped** verdict and an **absent** proposer must not converge.

Items 4 and 5 — an `EvidenceRef` path resolving at the pinned commit, a quote byte-verifying — need the tree and land in plan 3's `verify_discover_refs`, in front of this function.

**Files:**
- Modify: `src/sdlc/assessment/discover/apply.py` (append)
- Test: `tests/test_discover_stamp.py`

**Interfaces:**
- Consumes: `ProposedDisposition`, `DiscoverProposal`, `SplitPartition` from `sdlc.assessment.discover.map`; task 1's `baseline_dispositions`
- Produces: `StampedProposal`, `stamp(context: DiscoverContext, proposal: DiscoverProposal | None) -> StampedProposal`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_stamp.py
"""FR-913 (E-48 DD7/DD8): what verification refuses, and how it says so."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.apply import StampedProposal, stamp
from sdlc.assessment.discover.map import (
    CandidateContext,
    CandidateDisposition,
    DiscoverAction,
    DiscoverContext,
    DiscoverProposal,
    DispositionSource,
    GraphSummary,
    ProposedDisposition,
    SplitPartition,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import Measurement

MEASURED = Measurement.measured(1.0)
GRAPH = GraphSummary(
    parsed=4, unparsed=0, edges=3, unresolved_relative_rate=Measurement.measured(0.0)
)


def _member(value: str) -> CandidateMember:
    return CandidateMember(kind=MemberKind.HTTP_ROUTE, value=value, path="pay/api.py")


def _ctx(candidate_id="C-01", values=("POST /pay",), **kw):
    members = tuple(_member(v) for v in values)
    base = dict(
        candidate_id=candidate_id,
        name="payments",
        confidence=Confidence.HIGH,
        sources=("S3-payments",),
        source_rules=("s3_http_route",),
        members=members,
        member_paths=("pay/api.py",),
        cohesion=MEASURED,
        coupling=MEASURED,
        guardrail_only=False,
    )
    return CandidateContext(**(base | kw))


def _context(*candidates) -> DiscoverContext:
    return DiscoverContext(
        candidates=candidates or (_ctx(),), graph=GRAPH, collected=Measurement.measured(1.0)
    )


def _prop(**kw) -> ProposedDisposition:
    base = dict(
        candidate_id="C-01",
        action=DiscoverAction.CONFIRM,
        rationale="four routes and a table, one owner",
    )
    return ProposedDisposition(**(base | kw))


def _only(result: StampedProposal) -> CandidateDisposition:
    assert len(result.dispositions) == 1
    return result.dispositions[0]


def test_no_proposal_is_the_baseline_for_every_candidate():
    """DD7's first fallback: the role is not shipped, or the stage is off."""
    got = stamp(_context(), None)
    assert _only(got).source is DispositionSource.BASELINE
    assert got.dropped == 0


def test_a_clean_proposal_is_stamped_proposer():
    got = stamp(_context(), DiscoverProposal(dispositions=[_prop()]))
    d = _only(got)
    assert d.source is DispositionSource.PROPOSER
    assert d.rule == "proposer"
    assert d.rationale.startswith("four routes")


def test_a_missing_disposition_is_dropped_not_baselined():
    """DD7's second fallback, and the reason the two must not converge: the
    model ran and failed to dispose, which is evidence about the candidate.
    Laundering it into a baseline CONFIRM would silently confirm a boundary
    nobody judged (unbuilt_signal vs failed_signal)."""
    got = stamp(_context(), DiscoverProposal(dispositions=[]))
    d = _only(got)
    assert d.action is DiscoverAction.FLAG
    assert d.source is DispositionSource.DROPPED
    assert d.rule == "dropped_missing"
    assert got.dropped == 1


def test_a_duplicated_disposition_is_dropped():
    got = stamp(_context(), DiscoverProposal(dispositions=[_prop(), _prop()]))
    assert _only(got).rule == "dropped_duplicated"


def test_a_disposition_naming_no_candidate_is_recorded_by_id():
    """DD8 item 1. The id is kept rather than only counted: with no row to
    carry it, the id is the only record verification leaves behind."""
    got = stamp(_context(), DiscoverProposal(dispositions=[_prop(), _prop(candidate_id="C-99")]))
    assert got.unknown_candidate_ids == ("C-99",)
    assert _only(got).source is DispositionSource.PROPOSER


def test_a_merge_into_an_unknown_target_is_dropped():
    got = stamp(
        _context(),
        DiscoverProposal(dispositions=[_prop(action=DiscoverAction.MERGE, merge_into="C-99")]),
    )
    assert _only(got).rule == "dropped_merge_target"


def test_a_merge_into_itself_is_dropped():
    got = stamp(
        _context(),
        DiscoverProposal(dispositions=[_prop(action=DiscoverAction.MERGE, merge_into="C-01")]),
    )
    assert _only(got).rule == "dropped_merge_self"


def test_a_merge_into_a_target_that_did_not_survive_is_dropped():
    """The second pass. A merge into a de-scoped or itself-merged candidate
    would fold the loser's members into nothing, and merge CHAINS die here
    too: in A->B->C, B's action is MERGE rather than CONFIRM."""
    got = stamp(
        _context(_ctx("C-01"), _ctx("C-02"), _ctx("C-03")),
        DiscoverProposal(
            dispositions=[
                _prop(candidate_id="C-01", action=DiscoverAction.MERGE, merge_into="C-02"),
                _prop(candidate_id="C-02", action=DiscoverAction.MERGE, merge_into="C-03"),
                _prop(candidate_id="C-03"),
            ]
        ),
    )
    by_id = {d.candidate_id: d for d in got.dispositions}
    assert by_id["C-01"].rule == "dropped_merge_target_not_confirmed"
    assert by_id["C-02"].action is DiscoverAction.MERGE
    assert by_id["C-03"].action is DiscoverAction.CONFIRM


def test_a_split_into_fewer_than_two_partitions_is_dropped():
    got = stamp(
        _context(),
        DiscoverProposal(
            dispositions=[
                _prop(
                    action=DiscoverAction.SPLIT,
                    partitions=(SplitPartition(name="a", member_values=("POST /pay",)),),
                )
            ]
        ),
    )
    assert _only(got).rule == "dropped_split_partitions"


def test_a_split_naming_a_member_the_candidate_lacks_is_dropped():
    """DD8 item 3: a SPLIT partitions the candidate's OWN members. No
    invented members."""
    got = stamp(
        _context(_ctx(values=("POST /pay", "GET /pay"))),
        DiscoverProposal(
            dispositions=[
                _prop(
                    action=DiscoverAction.SPLIT,
                    partitions=(
                        SplitPartition(name="a", member_values=("POST /pay",)),
                        SplitPartition(name="b", member_values=("DELETE /invented",)),
                    ),
                )
            ]
        ),
    )
    assert _only(got).rule == "dropped_split_members"


def test_a_split_with_an_empty_partition_is_dropped():
    got = stamp(
        _context(_ctx(values=("POST /pay", "GET /pay"))),
        DiscoverProposal(
            dispositions=[
                _prop(
                    action=DiscoverAction.SPLIT,
                    partitions=(
                        SplitPartition(name="a", member_values=("POST /pay",)),
                        SplitPartition(name="b", member_values=()),
                    ),
                )
            ]
        ),
    )
    assert _only(got).rule == "dropped_split_members"


def test_a_split_with_overlapping_partitions_is_dropped():
    """A member on both sides is not a partition."""
    got = stamp(
        _context(_ctx(values=("POST /pay", "GET /pay"))),
        DiscoverProposal(
            dispositions=[
                _prop(
                    action=DiscoverAction.SPLIT,
                    partitions=(
                        SplitPartition(name="a", member_values=("GET /pay", "POST /pay")),
                        SplitPartition(name="b", member_values=("POST /pay",)),
                    ),
                )
            ]
        ),
    )
    assert _only(got).rule == "dropped_split_overlap"


def test_a_split_with_duplicate_partition_names_is_dropped():
    """local_key is built from the partition name, and resolve() raises on a
    duplicate local_key -- so this would crash the lock rather than degrade."""
    got = stamp(
        _context(_ctx(values=("POST /pay", "GET /pay"))),
        DiscoverProposal(
            dispositions=[
                _prop(
                    action=DiscoverAction.SPLIT,
                    partitions=(
                        SplitPartition(name="a", member_values=("POST /pay",)),
                        SplitPartition(name="a", member_values=("GET /pay",)),
                    ),
                )
            ]
        ),
    )
    assert _only(got).rule == "dropped_split_names"


def test_a_malformed_disposition_is_dropped_rather_than_raising():
    """The catch-all. ProposedDisposition accepts shapes CandidateDisposition
    refuses -- here, a CONFIRM carrying a merge target -- and a model can
    produce anything. Constructing it must degrade, never crash the phase."""
    got = stamp(
        _context(),
        DiscoverProposal(dispositions=[_prop(action=DiscoverAction.CONFIRM, merge_into="C-02")]),
    )
    assert _only(got).rule == "dropped_malformed"


def test_dropped_is_derived_from_the_rows():
    with pytest.raises(ValidationError, match="derived"):
        StampedProposal(dispositions=(), dropped=3)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_stamp.py -v`
Expected: FAIL — `ImportError: cannot import name 'StampedProposal'`

- [ ] **Step 3: Write the implementation**

Append to `src/sdlc/assessment/discover/apply.py`:

```python
class StampedProposal(BaseModel):
    """Every candidate's verified disposition, plus what verification refused.

    `unknown_candidate_ids` is deliberately not folded into `dropped`: a
    disposition naming a candidate that does not exist has no row to carry
    it, so the id itself is the only record verification leaves behind.
    Counting it and discarding the id would make the citation guard's input
    unauditable.
    """

    dispositions: tuple[CandidateDisposition, ...] = ()
    unknown_candidate_ids: tuple[str, ...] = ()
    dropped: int = 0

    @model_validator(mode="after")
    def _dropped_is_derived(self) -> "StampedProposal":
        actual = sum(1 for d in self.dispositions if d.source is DispositionSource.DROPPED)
        if self.dropped != actual:
            raise ValueError(
                f"dropped={self.dropped} but {actual} disposition(s) carry "
                f"source=dropped -- counts are derived from rows, never "
                f"assigned"
            )
        return self

    @model_validator(mode="after")
    def _one_row_per_candidate_sorted(self) -> "StampedProposal":
        ids = [d.candidate_id for d in self.dispositions]
        if ids != sorted(set(ids)):
            raise ValueError(
                f"candidate ids {ids} are not one-per-candidate and sorted "
                f"-- DD8 requires exactly one disposition per candidate, and "
                f"discovery order must not reach the artifact"
            )
        return self

    @model_validator(mode="after")
    def _unknown_ids_are_sorted(self) -> "StampedProposal":
        if list(self.unknown_candidate_ids) != sorted(set(self.unknown_candidate_ids)):
            raise ValueError(
                f"unknown_candidate_ids {self.unknown_candidate_ids} are not sorted and deduped"
            )
        return self


def _dropped(candidate_id: str, rule: str, detail: str) -> CandidateDisposition:
    """DD7: a refused model verdict becomes FLAG for that candidate, never
    the baseline. "A model decided this and cited something that does not
    exist" is evidence about the candidate; laundering it into a
    code-computed CONFIRM would discard that evidence."""
    return CandidateDisposition(
        candidate_id=candidate_id,
        action=DiscoverAction.FLAG,
        source=DispositionSource.DROPPED,
        rule=rule,
        rationale=detail,
    )


def _split_refusal(context: CandidateContext, proposed: ProposedDisposition) -> str:
    """The rule naming why a SPLIT was refused, or "" when it stands.

    Coverage is NOT required: a partition that leaves members behind loses
    them from the capability set, but they then fall out of attribute()'s
    numerator and the coverage floor reports it. A silent loss would be worth
    refusing; a visible one is not.
    """
    parts = proposed.partitions
    if len(parts) < 2:
        return "dropped_split_partitions"
    names = [p.name for p in parts]
    if len(set(names)) != len(names):
        return "dropped_split_names"
    own = {m.value for m in context.members}
    seen: set[str] = set()
    for part in parts:
        values = set(part.member_values)
        if not values or not values <= own:
            return "dropped_split_members"
        if seen & values:
            return "dropped_split_overlap"
        seen |= values
    return ""


def _merge_refusal(
    context: CandidateContext, proposed: ProposedDisposition, known: Mapping[str, CandidateContext]
) -> str:
    if proposed.merge_into == context.candidate_id:
        return "dropped_merge_self"
    if proposed.merge_into is None or proposed.merge_into not in known:
        return "dropped_merge_target"
    return ""


def _stamp_one(
    context: CandidateContext,
    rows: Sequence[ProposedDisposition],
    known: Mapping[str, CandidateContext],
) -> CandidateDisposition:
    cid = context.candidate_id
    if not rows:
        return _dropped(
            cid, "dropped_missing", "the proposer returned no disposition for this candidate"
        )
    if len(rows) > 1:
        return _dropped(
            cid,
            "dropped_duplicated",
            f"the proposer returned {len(rows)} dispositions for this "
            f"candidate; DD8 requires exactly one",
        )
    proposed = rows[0]
    if proposed.action is DiscoverAction.SPLIT:
        refusal = _split_refusal(context, proposed)
        if refusal:
            return _dropped(
                cid, refusal, "the split does not partition this candidate's own members"
            )
    if proposed.action is DiscoverAction.MERGE:
        refusal = _merge_refusal(context, proposed, known)
        if refusal:
            return _dropped(
                cid,
                refusal,
                f"merge_into={proposed.merge_into!r} does not name another "
                f"candidate in this context",
            )
    try:
        return CandidateDisposition(
            candidate_id=cid,
            action=proposed.action,
            source=DispositionSource.PROPOSER,
            rule="proposer",
            rationale=proposed.rationale,
            merge_into=proposed.merge_into,
            partitions=proposed.partitions,
            evidence=proposed.evidence,
        )
    except ValidationError as exc:
        return _dropped(cid, "dropped_malformed", f"the disposition did not validate: {exc}"[:300])


def stamp(context: DiscoverContext, proposal: DiscoverProposal | None) -> StampedProposal:
    """DD8 items 1-3 and DD7's two fallbacks.

    `proposal is None` is the proposer-ABSENT case (the role is not shipped
    or the stage is off) and yields DD6's baseline. A proposal that is
    present but missing a row is the proposer-FAILED case and yields FLAG.
    The two must not converge -- unbuilt_signal vs failed_signal states the
    rule, and "the reason strings must not converge".

    Items 4 and 5 (an EvidenceRef path resolving at the pinned commit, a
    quote byte-verifying) need the tree and land in plan 3's
    verify_discover_refs, in front of this function.
    """
    if proposal is None:
        return StampedProposal(dispositions=baseline_dispositions(context))

    known = {c.candidate_id: c for c in context.candidates}
    by_candidate: dict[str, list[ProposedDisposition]] = {}
    unknown: set[str] = set()
    for row in proposal.dispositions:
        if row.candidate_id in known:
            by_candidate.setdefault(row.candidate_id, []).append(row)
        else:
            unknown.add(row.candidate_id)

    first = [_stamp_one(c, by_candidate.get(c.candidate_id, ()), known) for c in context.candidates]

    # Second pass. A MERGE whose target did not itself survive would fold the
    # loser's members into nothing, which is the silent-member-loss defect
    # _split_refusal's coverage note explains is worth refusing. Chains die
    # here too: in A->B->C, B's action is MERGE rather than CONFIRM.
    confirmed = {d.candidate_id for d in first if d.action is DiscoverAction.CONFIRM}
    final = tuple(
        d
        if not (d.action is DiscoverAction.MERGE and d.merge_into not in confirmed)
        else _dropped(
            d.candidate_id,
            "dropped_merge_target_not_confirmed",
            f"merge_into={d.merge_into!r} was not itself confirmed, so the "
            f"merge would fold these members into nothing",
        )
        for d in first
    )

    return StampedProposal(
        dispositions=final,
        unknown_candidate_ids=tuple(sorted(unknown)),
        dropped=sum(1 for d in final if d.source is DispositionSource.DROPPED),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_stamp.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/apply.py tests/test_discover_stamp.py
git commit -m "feat(discover): DD8 structural verification, dropped never laundered into a baseline (E-48 DD7/DD8)"
```

---

### Task 3: Applying dispositions to the candidate set

`apply()` turns verified verdicts into the boundaries the lock will identify. The interesting rule is P2-D2: cohesion and coupling survive a CONFIRM untouched and are dropped to `not_collected` on any boundary whose member set changed.

**Files:**
- Modify: `src/sdlc/assessment/discover/apply.py` (append)
- Test: `tests/test_discover_apply.py`

**Interfaces:**
- Consumes: task 2's `StampedProposal`; `REJECTING_ACTIONS`, `Capability` from `sdlc.assessment.discover.map`
- Produces: `LockedCandidate`, `ApplyResult`, `apply(context: DiscoverContext, stamped: StampedProposal) -> ApplyResult`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_apply.py
"""FR-913 (E-48): verified dispositions become the boundaries the lock
identifies."""

from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.apply import (
    ApplyResult,
    LockedCandidate,
    StampedProposal,
    apply,
    stamp,
)
from sdlc.assessment.discover.map import (
    CandidateContext,
    CandidateDisposition,
    DiscoverAction,
    DiscoverContext,
    DiscoverProposal,
    DispositionSource,
    GraphSummary,
    ProposedDisposition,
    SplitPartition,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import CollectionState, Measurement

MEASURED = Measurement.measured(1.0)
GRAPH = GraphSummary(
    parsed=4, unparsed=0, edges=3, unresolved_relative_rate=Measurement.measured(0.0)
)


def _member(value: str, path: str) -> CandidateMember:
    return CandidateMember(kind=MemberKind.HTTP_ROUTE, value=value, path=path)


def _ctx(candidate_id="C-01", name="payments", members=(("POST /pay", "pay/api.py"),), **kw):
    rows = tuple(_member(v, p) for v, p in members)
    base = dict(
        candidate_id=candidate_id,
        name=name,
        confidence=Confidence.HIGH,
        sources=("S3-payments",),
        source_rules=("s3_http_route",),
        members=rows,
        member_paths=tuple(sorted({m.path for m in rows if m.path})),
        cohesion=MEASURED,
        coupling=MEASURED,
        guardrail_only=False,
    )
    return CandidateContext(**(base | kw))


def _context(*candidates) -> DiscoverContext:
    return DiscoverContext(
        candidates=candidates, graph=GRAPH, collected=Measurement.measured(float(len(candidates)))
    )


def _applied(context, *proposed) -> ApplyResult:
    return apply(context, stamp(context, DiscoverProposal(dispositions=list(proposed))))


def _prop(candidate_id, action=DiscoverAction.CONFIRM, **kw):
    return ProposedDisposition(candidate_id=candidate_id, action=action, rationale="judged", **kw)


def test_a_confirmed_candidate_becomes_one_locked_candidate():
    got = apply(_context(_ctx()), stamp(_context(_ctx()), None))
    assert [c.local_key for c in got.locked] == ["C-01"]
    assert got.locked[0].name == "payments"


def test_a_de_scoped_or_flagged_candidate_produces_no_boundary():
    """DE_SCOPE and FLAG are verdicts ABOUT a candidate; only a surviving
    boundary is handed to the lock."""
    context = _context(_ctx("C-01"), _ctx("C-02", name="orders"))
    got = _applied(
        context, _prop("C-01", DiscoverAction.DE_SCOPE), _prop("C-02", DiscoverAction.FLAG)
    )
    assert got.locked == ()
    assert len(got.stamped.dispositions) == 2


def test_a_merged_candidate_folds_its_members_into_the_winner():
    context = _context(
        _ctx("C-01", members=(("POST /pay", "pay/api.py"),)),
        _ctx("C-02", name="billing", members=(("GET /bill", "bill/api.py"),)),
    )
    got = _applied(context, _prop("C-01"), _prop("C-02", DiscoverAction.MERGE, merge_into="C-01"))
    assert [c.local_key for c in got.locked] == ["C-01"]
    winner = got.locked[0]
    assert {m.value for m in winner.members} == {"POST /pay", "GET /bill"}
    assert winner.member_paths == ("bill/api.py", "pay/api.py")


def test_a_merge_winner_loses_its_cohesion_and_coupling():
    """P2-D2: build_context computed both over the ORIGINAL member set and
    then discarded the reference graph (DD4), so the number no longer
    describes this boundary and cannot be recomputed here."""
    context = _context(
        _ctx("C-01"), _ctx("C-02", name="billing", members=(("GET /bill", "bill/api.py"),))
    )
    got = _applied(context, _prop("C-01"), _prop("C-02", DiscoverAction.MERGE, merge_into="C-01"))
    winner = got.locked[0]
    assert winner.cohesion.state is CollectionState.NOT_COLLECTED
    assert "absorbed" in winner.cohesion.reason
    assert winner.coupling.state is CollectionState.NOT_COLLECTED


def test_a_confirmed_candidate_that_absorbed_nothing_keeps_its_metrics():
    got = apply(_context(_ctx()), stamp(_context(_ctx()), None))
    assert got.locked[0].cohesion.value == 1.0
    assert got.locked[0].coupling.value == 1.0


def test_a_split_produces_one_boundary_per_partition():
    context = _context(
        _ctx("C-01", members=(("POST /pay", "pay/api.py"), ("GET /bill", "bill/api.py")))
    )
    got = _applied(
        context,
        _prop(
            "C-01",
            DiscoverAction.SPLIT,
            partitions=(
                SplitPartition(name="billing", member_values=("GET /bill",)),
                SplitPartition(name="charging", member_values=("POST /pay",)),
            ),
        ),
    )
    assert [c.local_key for c in got.locked] == ["C-01#billing", "C-01#charging"]
    billing = got.locked[0]
    assert {m.value for m in billing.members} == {"GET /bill"}
    assert billing.member_paths == ("bill/api.py",)


def test_a_split_part_loses_its_cohesion_and_coupling():
    context = _context(
        _ctx("C-01", members=(("POST /pay", "pay/api.py"), ("GET /bill", "bill/api.py")))
    )
    got = _applied(
        context,
        _prop(
            "C-01",
            DiscoverAction.SPLIT,
            partitions=(
                SplitPartition(name="billing", member_values=("GET /bill",)),
                SplitPartition(name="charging", member_values=("POST /pay",)),
            ),
        ),
    )
    for part in got.locked:
        assert part.cohesion.state is CollectionState.NOT_COLLECTED
        assert "partition" in part.cohesion.reason


def test_local_keys_must_be_unique_and_sorted():
    """resolve() raises on a duplicate local_key, so a caller that produced
    one would crash the lock rather than degrade."""
    locked = LockedCandidate(
        local_key="C-01",
        name="payments",
        confidence=Confidence.HIGH,
        members=(),
        member_paths=(),
        cohesion=MEASURED,
        coupling=MEASURED,
        disposition=CandidateDisposition(
            candidate_id="C-01",
            action=DiscoverAction.CONFIRM,
            source=DispositionSource.BASELINE,
            rule="baseline_confirm",
        ),
    )
    with pytest.raises(ValidationError, match="unique and sorted"):
        ApplyResult(locked=(locked, locked), stamped=StampedProposal())


def test_apply_is_order_independent():
    """NFR-10: byte-identical regardless of the order the candidates and
    dispositions arrive in."""
    candidates = [_ctx("C-01"), _ctx("C-02", name="orders"), _ctx("C-03", name="billing")]
    props = [_prop("C-01"), _prop("C-02"), _prop("C-03", DiscoverAction.MERGE, merge_into="C-01")]
    first = _applied(_context(*candidates), *props).model_dump_json()
    for _ in range(5):
        shuffled = props[:]
        random.shuffle(shuffled)
        assert _applied(_context(*candidates), *shuffled).model_dump_json() == first
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_apply.py -v`
Expected: FAIL — `ImportError: cannot import name 'ApplyResult'`

- [ ] **Step 3: Write the implementation**

Append to `src/sdlc/assessment/discover/apply.py`:

```python
# P2-D2. build_context computed cohesion and coupling over the candidate's
# ORIGINAL members and then discarded the reference graph (DD4), so a
# boundary whose member set changed cannot have them recomputed here.
# Reporting the old number would attach a measurement to a thing it does not
# describe, which is the FR-915 conflation.
_SPLIT_REASON = (
    "this boundary is one partition of a split candidate, and "
    "the metric was computed over the whole candidate"
)
_MERGE_REASON = (
    "this boundary absorbed another candidate's members, and "
    "the metric was computed before the merge"
)


class LockedCandidate(BaseModel):
    """A boundary that survived disposition, before it has a bc_id.

    Capability minus bc_id, deliberately: identity is the lock's to assign
    (D4), and a type that could hold one before the lock ran would let a
    caller mint capability identity in the wrong phase -- the confusion
    ScanCandidate's docstring already warns about for C-NN vs BC-NNN.
    """

    model_config = {"frozen": True}
    local_key: str
    name: str
    confidence: Confidence
    members: tuple[CandidateMember, ...]
    member_paths: tuple[str, ...]
    cohesion: Measurement
    coupling: Measurement
    disposition: CandidateDisposition


class ApplyResult(BaseModel):
    locked: tuple[LockedCandidate, ...] = ()
    stamped: StampedProposal

    @model_validator(mode="after")
    def _local_keys_are_unique_and_sorted(self) -> "ApplyResult":
        keys = [c.local_key for c in self.locked]
        if keys != sorted(set(keys)):
            raise ValueError(
                f"local_keys {keys} are not unique and sorted -- resolve() "
                f"raises on a duplicate local_key, and discovery order must "
                f"not reach the artifact"
            )
        return self


def apply(context: DiscoverContext, stamped: StampedProposal) -> ApplyResult:
    """Verified dispositions in, the boundaries the lock will identify out.

    CONFIRM keeps its measured metrics; a merge winner and a split part lose
    theirs to not_collected (P2-D2). MERGE produces no boundary of its own --
    the loser's members fold into the winner, and only the winner is handed
    to resolve().
    """
    by_id = {c.candidate_id: c for c in context.candidates}
    disposition_of = {d.candidate_id: d for d in stamped.dispositions}

    absorbed: dict[str, list[CandidateContext]] = {}
    for d in stamped.dispositions:
        if d.action is DiscoverAction.MERGE and d.merge_into is not None:
            absorbed.setdefault(d.merge_into, []).append(by_id[d.candidate_id])

    locked: list[LockedCandidate] = []
    for context_row in context.candidates:
        d = disposition_of[context_row.candidate_id]
        if d.action in REJECTING_ACTIONS or d.action is DiscoverAction.MERGE:
            continue

        if d.action is DiscoverAction.SPLIT:
            for part in d.partitions:
                wanted = set(part.member_values)
                members = tuple(m for m in context_row.members if m.value in wanted)
                locked.append(
                    LockedCandidate(
                        local_key=f"{context_row.candidate_id}#{part.name}",
                        name=part.name,
                        confidence=context_row.confidence,
                        members=members,
                        member_paths=tuple(sorted({m.path for m in members if m.path})),
                        cohesion=Measurement.not_collected(_SPLIT_REASON),
                        coupling=Measurement.not_collected(_SPLIT_REASON),
                        disposition=d,
                    )
                )
            continue

        taken = absorbed.get(context_row.candidate_id, [])
        members = tuple(
            sorted(
                set(context_row.members) | {m for a in taken for m in a.members},
                key=CandidateMember.sort_key,
            )
        )
        locked.append(
            LockedCandidate(
                local_key=context_row.candidate_id,
                name=context_row.name,
                confidence=context_row.confidence,
                members=members,
                member_paths=tuple(sorted({m.path for m in members if m.path})),
                cohesion=(
                    Measurement.not_collected(_MERGE_REASON) if taken else context_row.cohesion
                ),
                coupling=(
                    Measurement.not_collected(_MERGE_REASON) if taken else context_row.coupling
                ),
                disposition=d,
            )
        )

    return ApplyResult(locked=tuple(sorted(locked, key=lambda c: c.local_key)), stamped=stamped)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_apply.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/apply.py tests/test_discover_apply.py
git commit -m "feat(discover): dispositions become boundaries, metrics dropped when the member set moves (E-48)"
```

---

### Task 4: Fingerprints and the map constructor

`fingerprint_of` is DD3's map applied to one boundary; `build_map` is the artifact's single constructor, following `assemble()`'s rule that one place where the artifact is built means its derived counts cannot disagree with the rows they were derived from.

**Files:**
- Modify: `src/sdlc/assessment/discover/apply.py` (append)
- Test: `tests/test_discover_map_build.py`

**Interfaces:**
- Consumes: task 3's `ApplyResult`, `LockedCandidate`; `group_by_tier` from `sdlc.assessment.discover.tiers`; `CapabilityFingerprint`, `Advisory` from `sdlc.capability.models`
- Produces: `fingerprint_of(locked: LockedCandidate) -> CapabilityFingerprint`, `build_map(applied, bc_of, *, advisories, attribution, decomposition, ownership) -> CapabilityMap`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_map_build.py
"""FR-913 (E-48): the fingerprint handed to resolve(), and the artifact's one
constructor."""

from __future__ import annotations

import pytest

from sdlc.assessment.discover.apply import (
    ApplyResult,
    LockedCandidate,
    StampedProposal,
    build_map,
    fingerprint_of,
)
from sdlc.assessment.discover.map import (
    CandidateDisposition,
    DiscoverAction,
    DispositionSource,
)
from sdlc.assessment.discover.models import (
    DecompositionReport,
    OwnershipOutcome,
    OwnershipReport,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.capability.models import Advisory, AdvisoryKind, SignalTier
from sdlc.measurement import CollectionState, Measurement

MEASURED = Measurement.measured(1.0)


def _disp(candidate_id="C-01", action=DiscoverAction.CONFIRM):
    return CandidateDisposition(
        candidate_id=candidate_id,
        action=action,
        source=DispositionSource.BASELINE,
        rule="baseline_confirm",
    )


def _locked(local_key="C-01", members=None, **kw):
    rows = tuple(
        members
        if members is not None
        else (
            CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="pay/api.py"),
            CandidateMember(kind=MemberKind.FILE_PATH, value="pay/core.py", path="pay/core.py"),
        )
    )
    base = dict(
        local_key=local_key,
        name="payments",
        confidence=Confidence.HIGH,
        members=rows,
        member_paths=tuple(sorted({m.path for m in rows if m.path})),
        cohesion=MEASURED,
        coupling=MEASURED,
        disposition=_disp(local_key),
    )
    return LockedCandidate(**(base | kw))


def _applied(*locked, stamped=None) -> ApplyResult:
    return ApplyResult(
        locked=tuple(locked),
        stamped=stamped or StampedProposal(dispositions=tuple(c.disposition for c in locked)),
    )


def test_a_fingerprint_groups_members_by_tier():
    fp = fingerprint_of(_locked())
    assert fp.collected.state is CollectionState.MEASURED
    assert fp.tiers[SignalTier.CONTRACT] == ["POST /pay"]
    assert fp.tiers[SignalTier.LOCATIONAL] == ["pay/core.py"]
    assert fp.tiers[SignalTier.BEHAVIORAL] == []


def test_a_memberless_boundary_has_a_not_collected_fingerprint():
    """E-47a's rule: a fingerprint that could not be computed is never scored
    0. score() returns None for a not_collected side, so resolve() mints a
    fresh id and files an IDENTITY_NOT_ASSESSED advisory instead."""
    fp = fingerprint_of(_locked(members=()))
    assert fp.collected.state is CollectionState.NOT_COLLECTED
    assert "no members" in fp.collected.reason


def test_build_map_attaches_the_bc_id_from_the_lock():
    m = build_map(_applied(_locked()), {"C-01": "BC-001"})
    assert [c.bc_id for c in m.capabilities] == ["BC-001"]
    assert m.capabilities[0].local_key == "C-01"
    assert m.collected.value == 1.0


def test_by_action_counts_capabilities_not_dispositions():
    """de_scope, flag and merge occur as verdicts but never as boundaries.
    Listing them here as zeros would read as 'no candidate was de-scoped',
    which is a claim `dispositions` already answers truthfully."""
    stamped = StampedProposal(dispositions=(_disp("C-01"), _disp("C-02", DiscoverAction.DE_SCOPE)))
    m = build_map(_applied(_locked("C-01"), stamped=stamped), {"C-01": "BC-001"})
    assert m.by_action == {DiscoverAction.CONFIRM: 1}
    assert len(m.dispositions) == 2


def test_dropped_dispositions_sums_both_halves_of_the_guard():
    """DD8's leniency is bounded by a rate over references; both a refused
    verdict and a verdict naming a candidate that does not exist feed it."""
    stamped = StampedProposal(
        dispositions=(
            _disp("C-01"),
            CandidateDisposition(
                candidate_id="C-02",
                action=DiscoverAction.FLAG,
                source=DispositionSource.DROPPED,
                rule="dropped_missing",
            ),
        ),
        unknown_candidate_ids=("C-98", "C-99"),
        dropped=1,
    )
    m = build_map(_applied(_locked("C-01"), stamped=stamped), {"C-01": "BC-001"})
    assert m.dropped_dispositions == 3
    # Plan 3 sets this and divides by it; the zero denominator is this plan's.
    assert m.total_references == 0


def test_build_map_refuses_a_boundary_with_no_bc_id():
    """resolve() attaches every proposed capability, so a missing one is a
    lock defect rather than a degraded input -- and a KeyError inside
    workflow code would retry forever."""
    with pytest.raises(ValueError, match="no bc_id was attached"):
        build_map(_applied(_locked("C-01")), {})


def test_build_map_carries_the_reports_and_the_advisories():
    nc = Measurement.not_collected("S3 did not collect")
    m = build_map(
        _applied(_locked()),
        {"C-01": "BC-001"},
        advisories=[
            Advisory(
                kind=AdvisoryKind.POSSIBLE_RENAME, local_key="C-01", detail="closest was BC-004"
            )
        ],
        decomposition=DecompositionReport(collected=nc),
        ownership=OwnershipReport(counts={o: 0 for o in OwnershipOutcome}, collected=nc),
    )
    assert m.advisories[0].kind is AdvisoryKind.POSSIBLE_RENAME
    assert m.decomposition.collected.state is CollectionState.NOT_COLLECTED
    assert m.attribution is None


def test_a_map_with_no_capabilities_is_a_measured_zero():
    """A tree with no capabilities is a real finding. A discover that could
    not run never reaches build_map -- the phase reports not_collected and
    carries no map at all."""
    m = build_map(_applied(), {})
    assert m.collected.state is CollectionState.MEASURED
    assert m.collected.value == 0.0
    assert m.capabilities == ()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_map_build.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_map'`

- [ ] **Step 3: Write the implementation**

Append to `src/sdlc/assessment/discover/apply.py`:

```python
def fingerprint_of(locked: LockedCandidate) -> CapabilityFingerprint:
    """DD3's MemberKind -> SignalTier map applied to one boundary.

    A boundary with no members yields not_collected, never an empty MEASURED
    fingerprint: score() returns None for a not_collected side, so resolve()
    mints a fresh id and files an IDENTITY_NOT_ASSESSED advisory rather than
    scoring it 0.0 against everything -- E-47a's rule, "never scored 0".
    """
    tiers = group_by_tier(locked.members)
    total = sum(len(values) for values in tiers.values())
    if not total:
        return CapabilityFingerprint(
            tiers=tiers,
            collected=Measurement.not_collected(
                f"{locked.local_key} carries no members, so no tier could be "
                f"populated and identity was not assessed"
            ),
        )
    return CapabilityFingerprint(tiers=tiers, collected=Measurement.measured(float(total)))


def build_map(
    applied: ApplyResult,
    bc_of: Mapping[str, str],
    *,
    advisories: Sequence[Advisory] = (),
    attribution: AttributionReport | None = None,
    decomposition: DecompositionReport | None = None,
    ownership: OwnershipReport | None = None,
) -> CapabilityMap:
    """The ONE constructor of a CapabilityMap, following assemble()'s rule:
    one place where the artifact is built means its derived counts cannot
    disagree with the rows they were derived from.

    `bc_of` is local_key -> bc_id, from the lock's attachments. Plan 3 adds
    `domain_model` (clause D7) and `blueprint` (clause D8) here, when their
    producers exist.

    Only ever MEASURED: a discover that could not run reports a not_collected
    PHASE row and carries no map at all, so a not_collected map has no
    producer and Assessment._discover_agrees_with_its_phase would refuse one.
    """
    missing = sorted(c.local_key for c in applied.locked if c.local_key not in bc_of)
    if missing:
        raise ValueError(
            f"no bc_id was attached to {missing} -- resolve() attaches every "
            f"proposed capability, so a missing one is a lock defect rather "
            f"than a degraded input"
        )

    capabilities = tuple(
        Capability(
            bc_id=bc_of[c.local_key],
            local_key=c.local_key,
            name=c.name,
            confidence=c.confidence,
            members=c.members,
            member_paths=c.member_paths,
            cohesion=c.cohesion,
            coupling=c.coupling,
            disposition=c.disposition,
        )
        for c in applied.locked
    )

    return CapabilityMap(
        capabilities=capabilities,
        # Counted over CAPABILITIES, not over dispositions: de_scope, flag and
        # merge occur as verdicts but never as boundaries, and listing them
        # here as zeros would read as "no candidate was de-scoped". The full
        # verdict record is `dispositions`, which carries every one.
        by_action={
            action: sum(1 for c in capabilities if c.disposition.action is action)
            for action in {c.disposition.action for c in capabilities}
        },
        dispositions=applied.stamped.dispositions,
        attribution=attribution,
        decomposition=decomposition,
        ownership=ownership,
        advisories=tuple(advisories),
        # Both halves of what DD8 refused: a verdict verification dropped, and
        # a verdict naming a candidate that does not exist. Plan 3 divides
        # this by total_references for the citation guard -- and must guard
        # the zero denominator this plan always produces.
        dropped_dispositions=(applied.stamped.dropped + len(applied.stamped.unknown_candidate_ids)),
        collected=Measurement.measured(float(len(capabilities))),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_map_build.py tests/test_discover_apply.py tests/test_discover_stamp.py tests/test_discover_baseline.py -v`
Expected: 38 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/apply.py tests/test_discover_map_build.py
git commit -m "feat(discover): fingerprints from the tier map, and CapabilityMap's one constructor (E-48 DD3)"
```

---

### Task 5: `ResolutionResult` → registry rows

`resolve()` returns attachments, retirements and merges; nothing turns those into the `CapabilityIdentity` rows `store.apply()` persists. That gap is E-48's to fill, and it belongs beside `resolve()` rather than inside `discover/` (P2-D4).

**Files:**
- Create: `src/sdlc/capability/rows.py`
- Test: `tests/test_capability_rows.py`

**Interfaces:**
- Consumes: `ResolutionResult`, `CapabilityIdentity`, `CapabilityFingerprint`, `IdentityStatus`, `RetiredReason`, `AdvisoryKind` from `sdlc.capability.models`
- Produces: `identity_rows(project: str, run_id: str, result: ResolutionResult, fingerprints: Mapping[str, CapabilityFingerprint], registry: Sequence[CapabilityIdentity]) -> list[CapabilityIdentity]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_capability_rows.py
"""FR-913 (E-48 P2-D4): a ResolutionResult becomes the rows store.apply()
persists."""

from __future__ import annotations

from sdlc.capability.models import (
    Advisory,
    AdvisoryKind,
    AttachMethod,
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityAttachment,
    IdentityStatus,
    ResolutionResult,
    RetiredReason,
    SignalTier,
)
from sdlc.capability.rows import identity_rows
from sdlc.measurement import Measurement


def _fp(*routes) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier.CONTRACT: list(routes)},
        collected=Measurement.measured(float(len(routes))),
    )


def _stored(bc_id="BC-001", status=IdentityStatus.ACTIVE, **kw):
    base = dict(
        bc_id=bc_id,
        project="acme",
        first_seen_run="run-1",
        status=status,
        fingerprint=_fp("GET /old"),
    )
    return CapabilityIdentity(**(base | kw))


def _matched(local_key="C-01", bc_id="BC-001"):
    return IdentityAttachment(
        local_key=local_key, bc_id=bc_id, method=AttachMethod.MATCHED, match_score=0.9
    )


def _new(local_key="C-01", bc_id="BC-007"):
    return IdentityAttachment(local_key=local_key, bc_id=bc_id, method=AttachMethod.FIRST_DISCOVERY)


def test_a_first_discovery_mints_an_active_row_stamped_with_this_run():
    rows = identity_rows(
        "acme", "run-9", ResolutionResult(attachments=[_new()]), {"C-01": _fp("POST /pay")}, []
    )
    assert len(rows) == 1
    assert rows[0].bc_id == "BC-007"
    assert rows[0].project == "acme"
    assert rows[0].first_seen_run == "run-9"
    assert rows[0].status is IdentityStatus.ACTIVE
    assert rows[0].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /pay"]


def test_a_matched_row_keeps_first_seen_run_and_refreshes_the_fingerprint():
    """Refreshing is what keeps the id attached across a slow drift: next
    run matches against what THIS run observed, not what run 1 did."""
    rows = identity_rows(
        "acme",
        "run-9",
        ResolutionResult(attachments=[_matched()]),
        {"C-01": _fp("POST /pay")},
        [_stored()],
    )
    assert rows[0].first_seen_run == "run-1"
    assert rows[0].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /pay"]


def test_a_matched_retired_row_is_revived():
    """E-47a: retired rows ARE match candidates, and a scan that matches one
    is re-attachment to the same capability, not reuse by a different one."""
    stored = _stored(status=IdentityStatus.RETIRED, retired_reason=RetiredReason.NOT_OBSERVED)
    rows = identity_rows(
        "acme",
        "run-9",
        ResolutionResult(attachments=[_matched()]),
        {"C-01": _fp("POST /pay")},
        [stored],
    )
    assert rows[0].status is IdentityStatus.ACTIVE
    assert rows[0].retired_reason is None


def test_an_unobserved_row_is_retired_with_its_reason():
    rows = identity_rows(
        "acme",
        "run-9",
        ResolutionResult(attachments=[_new(bc_id="BC-007")], retired=["BC-001"]),
        {"C-01": _fp("POST /pay")},
        [_stored()],
    )
    retired = next(r for r in rows if r.bc_id == "BC-001")
    assert retired.status is IdentityStatus.RETIRED
    assert retired.retired_reason is RetiredReason.NOT_OBSERVED


def test_a_merge_loser_points_at_its_winner_and_carries_no_retired_reason():
    """P2-D9: CapabilityIdentity forbids a retired_reason on a MERGED row, so
    RetiredReason.ABSORBED gains no producer here -- it stays reserved and
    unemitted, like OwnershipVerb.TRACKS. This is corrections._absorb's
    exact shape."""
    rows = identity_rows(
        "acme",
        "run-9",
        ResolutionResult(attachments=[_matched(bc_id="BC-002")], merged={"BC-001": "BC-002"}),
        {"C-01": _fp("POST /pay")},
        [_stored("BC-001"), _stored("BC-002")],
    )
    loser = next(r for r in rows if r.bc_id == "BC-001")
    assert loser.status is IdentityStatus.MERGED
    assert loser.merged_into == "BC-002"
    assert loser.retired_reason is None


def test_a_split_advisory_sets_derived_from():
    """resolve() files a SPLIT advisory when a new id was minted because a
    stronger match claimed the id it also matched. derived_from is where
    that provenance lands."""
    result = ResolutionResult(
        attachments=[_matched(bc_id="BC-001"), _new(local_key="C-02", bc_id="BC-007")],
        advisories=[
            Advisory(
                kind=AdvisoryKind.SPLIT,
                local_key="C-02",
                related_bc_id="BC-001",
                score=0.7,
                detail="claimed by a stronger match",
            )
        ],
    )
    rows = identity_rows(
        "acme", "run-9", result, {"C-01": _fp("POST /pay"), "C-02": _fp("GET /pay")}, [_stored()]
    )
    minted = next(r for r in rows if r.bc_id == "BC-007")
    assert minted.derived_from == "BC-001"


def test_rows_are_sorted_by_bc_id():
    """store.apply() writes one audit event per row, so the order is
    observable and must not depend on attachment order (NFR-10)."""
    result = ResolutionResult(
        attachments=[_new(local_key="C-02", bc_id="BC-009"), _new(local_key="C-01", bc_id="BC-003")]
    )
    rows = identity_rows("acme", "run-9", result, {"C-01": _fp("a"), "C-02": _fp("b")}, [])
    assert [r.bc_id for r in rows] == ["BC-003", "BC-009"]


def test_an_id_absent_from_the_registry_is_skipped_not_fabricated():
    """A retired or merged id with no stored row cannot be written: there is
    no fingerprint or first_seen_run to carry, and inventing them would put a
    fabricated row in the registry clients cite."""
    rows = identity_rows(
        "acme", "run-9", ResolutionResult(retired=["BC-404"], merged={"BC-405": "BC-001"}), {}, []
    )
    assert rows == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_capability_rows.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.capability.rows'`

- [ ] **Step 3: Write the implementation**

```python
# src/sdlc/capability/rows.py
"""FR-913 (E-48 P2-D4): a ResolutionResult becomes the rows to persist.

Pure -- fingerprints and attachments in, registry rows out. No I/O and no
temporalio, the tier matcher.py occupies.

Separate from matcher.py deliberately: resolve() answers "which id belongs to
this boundary", and this answers "what does the registry look like
afterwards". They are different questions with different failure modes, and
E-54's incremental re-assessment is the second caller of both. Two copies of
this mapping would agree only by coincidence.

RetiredReason.ABSORBED gains no producer here (P2-D9): resolve() reports
absorption as `merged`, and CapabilityIdentity._status_fields_agree forbids a
retired_reason on a MERGED row. The value stays reserved and unemitted, like
OwnershipVerb.TRACKS -- recorded as a deliberate deferral rather than given a
synthetic trigger.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .models import (
    AdvisoryKind,
    AttachMethod,
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityStatus,
    ResolutionResult,
    RetiredReason,
)


def identity_rows(
    project: str,
    run_id: str,
    result: ResolutionResult,
    fingerprints: Mapping[str, CapabilityFingerprint],
    registry: Sequence[CapabilityIdentity],
) -> list[CapabilityIdentity]:
    """Every row this assessment changes, sorted by bc_id.

    `fingerprints` is local_key -> what THIS assessment observed. A missing
    key is a KeyError rather than a skip: resolve() attaches every proposed
    capability, so a caller that lost one has a bug, and writing the row
    without its fingerprint would leave the next assessment matching against
    nothing.

    A retired or merged id with no stored row is skipped, not fabricated: it
    has no fingerprint and no first_seen_run to carry, and inventing them
    would put a made-up row in the registry clients cite.
    """
    stored = {r.bc_id: r for r in registry}
    split_source = {
        a.local_key: a.related_bc_id
        for a in result.advisories
        if a.kind is AdvisoryKind.SPLIT and a.related_bc_id
    }
    rows: dict[str, CapabilityIdentity] = {}

    for attachment in result.attachments:
        fingerprint = fingerprints[attachment.local_key]
        prior = stored.get(attachment.bc_id)
        if prior is None or attachment.method is AttachMethod.FIRST_DISCOVERY:
            rows[attachment.bc_id] = CapabilityIdentity(
                bc_id=attachment.bc_id,
                project=project,
                first_seen_run=run_id,
                status=IdentityStatus.ACTIVE,
                derived_from=split_source.get(attachment.local_key),
                fingerprint=fingerprint,
            )
            continue
        # A MATCHED row keeps its first_seen_run and its provenance, and
        # refreshes what it looked like: next assessment matches against what
        # THIS one observed, which is what keeps an id attached across a slow
        # drift. A matched RETIRED row is revived -- E-47a's rule that a scan
        # matching a retired id is re-attachment, not reuse.
        rows[attachment.bc_id] = prior.model_copy(
            update={
                "status": IdentityStatus.ACTIVE,
                "retired_reason": None,
                "fingerprint": fingerprint,
            }
        )

    for bc_id in result.retired:
        prior = stored.get(bc_id)
        if prior is None:
            continue
        rows[bc_id] = prior.model_copy(
            update={
                "status": IdentityStatus.RETIRED,
                "retired_reason": RetiredReason.NOT_OBSERVED,
                "merged_into": None,
            }
        )

    for loser, winner in result.merged.items():
        prior = stored.get(loser)
        if prior is None:
            continue
        rows[loser] = prior.model_copy(
            update={"status": IdentityStatus.MERGED, "retired_reason": None, "merged_into": winner}
        )

    return [rows[bc_id] for bc_id in sorted(rows)]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_capability_rows.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/capability/rows.py tests/test_capability_rows.py
git commit -m "feat(capability): ResolutionResult -> the registry rows to persist (E-48 P2-D4)"
```

---

### Task 6: DD10's phase memo

Key: `(tree_hash, context_digest, identity_registry_version, prompt_sha, model)`, scoped by project. `discover_key` is a **sibling** of `signal_key` rather than a call into `content_key`, for the reason `signal_key`'s own docstring gives.

**Files:**
- Modify: `src/sdlc/memoization/cache.py` (append `discover_key`, `NO_PROPOSER`)
- Modify: `src/sdlc/assessment/discover/map.py` (append `context_digest`)
- Create: `src/sdlc/assessment/discover/memo.py`
- Modify: `src/sdlc/assessment/activities.py` (append two activities)
- Test: `tests/test_discover_memo.py`

**Interfaces:**
- Consumes: `CapabilityMap`, `DiscoverContext` from `sdlc.assessment.discover.map`; `cache.get`/`cache.put`
- Produces: `cache.discover_key(project, tree_hash, context_digest, identity_registry_version, prompt_sha, model_id) -> str`; `cache.NO_PROPOSER`; `map.context_digest(context) -> str`; `memo.load(...) -> CapabilityMap | None`; `memo.store(...) -> bool`; `DiscoverMemoInput`, `DiscoverMemoStoreInput`, `discover_memo_load`, `discover_memo_store`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_memo.py
"""FR-103 / FR-913 (E-48 DD10): the phase memo, and the terms it keys on."""

from __future__ import annotations

import pytest

from sdlc.assessment.discover import memo
from sdlc.assessment.discover.map import (
    CandidateContext,
    CapabilityMap,
    DiscoverContext,
    GraphSummary,
    context_digest,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import Measurement
from sdlc.memoization.cache import NO_PROPOSER, discover_key

GRAPH = GraphSummary(
    parsed=4, unparsed=0, edges=3, unresolved_relative_rate=Measurement.measured(0.0)
)
MAP = CapabilityMap(collected=Measurement.measured(0.0))
KEY = dict(
    project="acme",
    tree_hash="t" * 40,
    context_digest="d" * 64,
    prompt_sha=NO_PROPOSER,
    model=NO_PROPOSER,
)


@pytest.fixture(autouse=True)
def cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / "memo"))


def _ctx(candidate_id="C-01") -> DiscoverContext:
    member = CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="pay/api.py")
    return DiscoverContext(
        candidates=(
            CandidateContext(
                candidate_id=candidate_id,
                name="payments",
                confidence=Confidence.HIGH,
                sources=("S3-payments",),
                source_rules=("s3_http_route",),
                members=(member,),
                member_paths=("pay/api.py",),
                cohesion=Measurement.measured(1.0),
                coupling=Measurement.measured(0.0),
                guardrail_only=False,
            ),
        ),
        graph=GRAPH,
        collected=Measurement.measured(1.0),
    )


def test_every_term_moves_the_key():
    """DD10 lists five terms plus the project. A term that does not move the
    key is a term that is not in it."""
    base = discover_key("acme", "t", "d", 1, "p", "m")
    assert base != discover_key("other", "t", "d", 1, "p", "m")
    assert base != discover_key("acme", "u", "d", 1, "p", "m")
    assert base != discover_key("acme", "t", "e", 1, "p", "m")
    assert base != discover_key("acme", "t", "d", 2, "p", "m")
    assert base != discover_key("acme", "t", "d", 1, "q", "m")
    assert base != discover_key("acme", "t", "d", 1, "p", "n")


def test_an_unchanged_tree_hits():
    assert memo.store(**KEY, registry_version=1, out=MAP) is True
    assert memo.load(**KEY, registry_version=1) is not None


def test_an_identity_write_invalidates():
    """E-47a's amendment to FR-103, and what makes skipping the lock on a hit
    safe: if the registry moved, the key moved."""
    memo.store(**KEY, registry_version=1, out=MAP)
    assert memo.load(**KEY, registry_version=2) is None


def test_a_prompt_or_model_change_invalidates():
    memo.store(**KEY, registry_version=1, out=MAP)
    assert memo.load(**{**KEY, "prompt_sha": "abc"}, registry_version=1) is None
    assert memo.load(**{**KEY, "model": "claude-x"}, registry_version=1) is None


def test_a_not_collected_map_is_never_stored():
    """scan/memo.py's rule verbatim in intent: never serve a failure
    forever."""
    failed = CapabilityMap(collected=Measurement.not_collected("S5 did not collect"))
    assert memo.store(**KEY, registry_version=1, out=failed) is False
    assert memo.load(**KEY, registry_version=1) is None


def test_corrupt_content_is_a_miss_not_a_crash():
    """A truncated cache file must cost a recompute, not an assessment."""
    from sdlc.memoization import cache

    cache.put(discover_key("acme", "t" * 40, "d" * 64, 1, NO_PROPOSER, NO_PROPOSER), "{not json")
    assert memo.load(**KEY, registry_version=1) is None


def test_the_context_digest_is_order_independent():
    """The digest inherits build_context's guarantee: DiscoverContext's
    model_dump_json is already asserted byte-identical across input order
    (test_discover_context.py), and this hashes exactly those bytes."""
    assert context_digest(_ctx()) == context_digest(_ctx())
    assert context_digest(_ctx()) != context_digest(_ctx("C-02"))


def test_the_sentinel_is_never_empty():
    """signal_key's rule: '' would make 'no model was involved'
    indistinguishable from a bug that dropped the model id (P2-D6)."""
    assert NO_PROPOSER
    assert NO_PROPOSER != ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_memo.py -v`
Expected: FAIL — `ImportError: cannot import name 'NO_PROPOSER' from 'sdlc.memoization.cache'`

- [ ] **Step 3: Write the implementation**

Append to `src/sdlc/memoization/cache.py`:

```python
# E-48 P2-D6. With no proposer there is no prompt and no model, and "" is
# exactly what signal_key's docstring refuses: it would make "no model was
# involved" indistinguishable from a bug that dropped the model id, in the one
# place where a silently wrong value serves stale results indefinitely. A
# baseline-only map and a proposer map therefore never share a key.
NO_PROPOSER = "no-proposer"


def discover_key(
    project: str,
    tree_hash: str,
    context_digest: str,
    identity_registry_version: int,
    prompt_sha: str,
    model_id: str,
) -> str:
    """Memo key for the whole discover phase (E-48 DD10).

    A sibling of content_key and signal_key rather than a call into either,
    for signal_key's reason: content_key has no slot for a registry version,
    and reusing upstream_recall_ref for one would put a load-bearing term in a
    field named for something else.

    `identity_registry_version` is FR-103's amendment from E-47a and is what
    makes skipping the lock on a hit safe -- if the registry moved, the key
    moved, so a hit implies the stored map's ids are still the registry's. It
    is deliberately coarse: any identity write invalidates the whole map for
    that project, and the map is a single artifact with no per-capability
    memoization to preserve.
    """
    payload = "|".join(
        [
            "discover",
            project,
            tree_hash,
            context_digest,
            str(identity_registry_version),
            prompt_sha,
            model_id,
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()
```

Append to `src/sdlc/assessment/discover/map.py`, adding `import hashlib` at the top of the module:

```python
def context_digest(context: DiscoverContext) -> str:
    """A canonical digest over the packet the rest of the phase reads (DD10).

    Digesting the packet rather than hand-listing its parts follows
    brief_digest's reasoning: identical facts hit, new facts invalidate, and a
    field added to the context later cannot escape the key.

    Canonical because DiscoverContext is: build_context sorts every collection
    it emits and the model carries no dicts, which
    test_the_packet_is_order_independent already asserts as a byte-identical
    model_dump_json across input order. This hashes exactly those bytes.
    """
    return hashlib.sha256(context.model_dump_json().encode("utf-8")).hexdigest()
```

```python
# src/sdlc/assessment/discover/memo.py
"""The discover phase memo (FR-103, FR-913, E-48 DD10).

Filesystem I/O, so this is ACTIVITY-side code: a workflow must never call it.
Kept out of map.py and apply.py so those stay pure -- scan/memo.py's shape and
scan/memo.py's reason.

The memo is over the WHOLE phase: a hit returns the stored CapabilityMap and
steps 3-8 are skipped entirely, including the lock. That is safe precisely
because identity_registry_version is a key term.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from ...measurement import CollectionState
from ...memoization import cache
from .map import CapabilityMap

_log = logging.getLogger(__name__)


def load(
    *,
    project: str,
    tree_hash: str,
    context_digest: str,
    registry_version: int,
    prompt_sha: str,
    model: str,
) -> CapabilityMap | None:
    """A cached map, or None on miss or unparseable content.

    Corrupt content is a MISS, never a crash: a truncated cache file must cost
    a recompute, not an assessment (scan/memo.py's rule).
    """
    raw = cache.get(
        cache.discover_key(project, tree_hash, context_digest, registry_version, prompt_sha, model)
    )
    if raw is None:
        return None
    try:
        return CapabilityMap.model_validate_json(raw)
    except ValidationError:
        _log.warning("discover memo for %s did not validate; recomputing", project)
        return None


def store(
    *,
    project: str,
    tree_hash: str,
    context_digest: str,
    registry_version: int,
    prompt_sha: str,
    model: str,
    out: CapabilityMap,
) -> bool:
    """Cache `out` and report whether it was stored.

    ONLY a MEASURED map is stored -- scan/memo.py's rule verbatim in intent.
    Memoizing a phase that reported not_collected would serve that failure as
    a cache hit forever.
    """
    if out.collected.state is not CollectionState.MEASURED:
        return False
    cache.put(
        cache.discover_key(project, tree_hash, context_digest, registry_version, prompt_sha, model),
        out.model_dump_json(),
    )
    return True
```

Append to `src/sdlc/assessment/activities.py`, adding one new import and **extending** the existing `.discover.map` line (a second `from .discover.map import ...` would be a duplicate):

```python
from ..capability.store import BoardIdentityStore
from .discover import memo as discover_memo
from .discover.map import CapabilityMap, DiscoverContext, GraphSummary
```

```python
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
        project=inp.project,
        tree_hash=inp.tree_hash,
        context_digest=inp.context_digest,
        registry_version=version,
        prompt_sha=inp.prompt_sha,
        model=inp.model,
    )


@activity.defn
async def discover_memo_store(inp: DiscoverMemoStoreInput) -> bool:
    """DD10's write, keyed at the POST-lock registry version -- the version
    whose ids the map actually carries. Keying it at the pre-lock version
    would guarantee a miss on every subsequent run (P2-D3)."""
    return discover_memo.store(
        project=inp.key.project,
        tree_hash=inp.key.tree_hash,
        context_digest=inp.key.context_digest,
        registry_version=inp.registry_version,
        prompt_sha=inp.key.prompt_sha,
        model=inp.key.model,
        out=inp.out,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_memo.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/memoization/cache.py src/sdlc/assessment/discover/map.py src/sdlc/assessment/discover/memo.py src/sdlc/assessment/activities.py tests/test_discover_memo.py
git commit -m "feat(discover): the phase memo, keyed on the identity registry version (E-48 DD10)"
```

---

### Task 7: The `discover_lock` activity

Clause D4 and nothing more (DD5): locking the capability set and assigning identity to it are the same moment. This is the one activity in the phase that **must not** degrade — E-47a's fail-closed rule, because proceeding "produces a complete, plausible-looking map in which every id is wrong, and the next successful write commits that corruption."

**Files:**
- Modify: `src/sdlc/assessment/activities.py` (append)
- Test: `tests/test_discover_lock_activity.py`

**Interfaces:**
- Consumes: `resolve` from `sdlc.capability.matcher`; `identity_rows` from `sdlc.capability.rows`; `BoardIdentityStore`
- Produces: `DiscoverLockInput(project, run_id, proposed)`, `DiscoverLockOutcome(attachments, advisories, registry_version)`, `async discover_lock(inp) -> DiscoverLockOutcome`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_lock_activity.py
"""FR-913 (E-48 D4/DD5): the lock is identity resolution, and it fails
closed."""

from __future__ import annotations

import pytest

from sdlc.assessment.activities import DiscoverLockInput, discover_lock
from sdlc.capability.models import (
    AttachMethod,
    CapabilityFingerprint,
    ProposedCapability,
    SignalTier,
)
from sdlc.capability.store import BoardIdentityStore
from sdlc.measurement import Measurement

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def board(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    return tmp_path / "board.sqlite3"


def _fp(*routes) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier.CONTRACT: list(routes)},
        collected=Measurement.measured(float(len(routes))),
    )


def _proposed(local_key="C-01", *routes) -> ProposedCapability:
    return ProposedCapability(local_key=local_key, fingerprint=_fp(*(routes or ("POST /pay",))))


async def test_the_lock_mints_ids_and_persists_them():
    out = await discover_lock(
        DiscoverLockInput(
            project="acme",
            run_id="run-1",
            proposed=[_proposed("C-01"), _proposed("C-02", "GET /orders")],
        )
    )
    assert {a.local_key for a in out.attachments} == {"C-01", "C-02"}
    assert all(a.method is AttachMethod.FIRST_DISCOVERY for a in out.attachments)

    store = BoardIdentityStore()
    try:
        rows = store.load("acme")
    finally:
        store.close()
    assert {r.bc_id for r in rows} == {a.bc_id for a in out.attachments}
    assert all(r.first_seen_run == "run-1" for r in rows)


async def test_a_second_lock_on_the_same_fingerprints_reattaches():
    """E-47a's central guarantee: an id clients cite does not move because
    the assessment ran again."""
    first = await discover_lock(
        DiscoverLockInput(project="acme", run_id="run-1", proposed=[_proposed("C-01")])
    )
    second = await discover_lock(
        DiscoverLockInput(project="acme", run_id="run-2", proposed=[_proposed("C-01")])
    )
    assert second.attachments[0].bc_id == first.attachments[0].bc_id
    assert second.attachments[0].method is AttachMethod.MATCHED


async def test_the_lock_returns_the_new_registry_version():
    """The memo's store-side key term (P2-D3)."""
    out = await discover_lock(
        DiscoverLockInput(project="acme", run_id="run-1", proposed=[_proposed("C-01")])
    )
    assert out.registry_version == 1


async def test_an_empty_proposal_does_not_move_the_registry_version():
    """P2-D7: apply() bumps the version and writes one audit event per row.
    With no rows it would bump the version and record nothing, invalidating
    every project memo for a write that did not happen."""
    out = await discover_lock(DiscoverLockInput(project="acme", run_id="run-1", proposed=[]))
    assert out.attachments == []
    assert out.registry_version == 0


async def test_an_unreachable_store_raises_rather_than_degrading(monkeypatch):
    """DD9 and E-47a's fail-closed rule: proceeding produces a complete,
    plausible-looking map in which every id is wrong. The phase must report
    not_collected, which means this activity raises."""
    monkeypatch.setenv("SDLC_BOARD_DB", "\0invalid/board.sqlite3")
    with pytest.raises(Exception):
        await discover_lock(
            DiscoverLockInput(project="acme", run_id="run-1", proposed=[_proposed("C-01")])
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_lock_activity.py -v`
Expected: FAIL — `ImportError: cannot import name 'DiscoverLockInput'`

- [ ] **Step 3: Write the implementation**

Append to `src/sdlc/assessment/activities.py`, adding to its imports:

```python
from ..capability.matcher import resolve
from ..capability.models import (
    Advisory,
    IdentityAttachment,
    ProposedCapability,
)
from ..capability.rows import identity_rows
```

```python
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
        result = resolve(inp.proposed, registry, allocate=store.allocator(inp.project))
        rows = identity_rows(
            inp.project,
            inp.run_id,
            result,
            {p.local_key: p.fingerprint for p in inp.proposed},
            registry,
        )
        # P2-D7: a write with no rows bumps the version and records nothing,
        # invalidating every project memo for a change that did not happen.
        new_version = (
            store.apply(
                inp.project, rows, expected_version=version, actor="assessment", operation="resolve"
            )
            if rows
            else version
        )
    finally:
        store.close()
    return DiscoverLockOutcome(
        attachments=result.attachments, advisories=result.advisories, registry_version=new_version
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_lock_activity.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/activities.py tests/test_discover_lock_activity.py
git commit -m "feat(discover): the lock is identity resolution, failing closed on the store (E-48 D4/DD5)"
```

---

### Task 8: The `discover_finalize` activity

Step 7 of DD4: `attribute()` + `decompose()` + `assign()`, the three E-47b/c mechanisms that have waited unwired since they landed. It reads blobs at the pinned commit a second time — deliberate, per DD4: passing the reference graph between activities would push an entire tree's edge list through workflow history, which is the open FR-702 hazard.

**Files:**
- Modify: `src/sdlc/assessment/discover/context.py` (append two helpers)
- Modify: `src/sdlc/assessment/activities.py` (append)
- Test: `tests/test_discover_finalize_activity.py`

**Interfaces:**
- Consumes: `attribute`, `decompose`, `assign`, `EntityDeclaration`; `schema.declarations`, `schema.EXTRA_EXTENSIONS`
- Produces: `context.schema_collected(scan) -> Measurement`, `context.contract_collected(scan) -> Measurement`, `DiscoverFinalizeInput`, `DiscoverFinalizeOutcome`, `async discover_finalize(inp) -> DiscoverFinalizeOutcome`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_finalize_activity.py
"""FR-913 (E-48 DD4 step 7): attribute() + decompose() + assign(), wired."""

from __future__ import annotations

import subprocess

import pytest

from sdlc.assessment.activities import (
    DiscoverFinalizeInput,
    discover_finalize,
)
from sdlc.assessment.discover.apply import apply, stamp
from sdlc.assessment.discover.context import (
    build_context,
    contract_collected,
    schema_collected,
)
from sdlc.assessment.discover.models import OwnershipOutcome
from sdlc.assessment.scan.merge import merge
from sdlc.assessment.scan.models import (
    CATEGORIES,
    SCAN_ORDER,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanResult,
    ScanSignalResult,
    ScanSignalId,
    SignalSource,
    SourceCandidate,
    family_of,
)
from sdlc.measurement import CollectionState, Measurement

MEASURED = Measurement.measured(1.0)
NC = Measurement.not_collected("timed out")


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "pay").mkdir()
    (tmp_path / "pay" / "api.py").write_text(
        "from pay.models import Order\n@app.post('/api/payments')\ndef charge(): pass\n"
    )
    # s2_sqlalchemy_tablename is the pattern that fires here; the declaration
    # deliberately lives OUTSIDE BC-001's member paths, so ownership resolves
    # by write access rather than by declaration site.
    (tmp_path / "pay" / "models.py").write_text(
        "class Order(Base):\n    __tablename__ = 'payments'\n    id = Column(Integer)\n"
    )
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "t@t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", "init"], tmp_path)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    return str(tmp_path), sha


def _scan(candidates=(), sources=(), **states) -> ScanResult:
    """Thirteen rows, MEASURED unless a signal id is named not-collected.

    The payloads are constructed rather than model_copy'd in, so ScanResult's
    _unmeasured_carries_no_payload validator actually runs over the pairing.
    """
    return ScanResult(
        signals=[
            ScanSignalResult(
                signal=s,
                family=family_of(s),
                version=1,
                source=SignalSource.COMPUTED,
                collected=states.get(s.value, MEASURED),
                categories={k: states.get(s.value, MEASURED) for k in CATEGORIES[s]},
            )
            for s in SCAN_ORDER
        ],
        sources=list(sources),
        candidates=list(candidates),
    )


def _input(repo_dir, sha, **kw) -> DiscoverFinalizeInput:
    base = dict(
        repo_dir=repo_dir,
        commit_sha=sha,
        members={
            "BC-001": [
                CandidateMember(
                    kind=MemberKind.HTTP_ROUTE,
                    value="POST /api/payments",
                    path="pay/api.py",
                    line=2,
                )
            ]
        },
        entry_point_paths=["pay/api.py"],
        schema_collected=MEASURED,
        contract_collected=MEASURED,
    )
    return DiscoverFinalizeInput(**(base | kw))


def test_schema_collected_is_s2s_row():
    assert schema_collected(_scan()).state is CollectionState.MEASURED
    assert schema_collected(_scan(S2=NC)).state is CollectionState.NOT_COLLECTED


def test_contract_collected_needs_both_s3_and_s4():
    """P2-D5: CONTRACT_KINDS includes FRONTEND_ROUTE, which only S4 emits, so
    deriving this from S3 alone would let a dead S4 read as a capability that
    genuinely exposes no frontend route."""
    assert contract_collected(_scan()).state is CollectionState.MEASURED
    for degraded in ("S3", "S4"):
        got = contract_collected(_scan(**{degraded: NC}))
        assert got.state is CollectionState.NOT_COLLECTED
        assert degraded in got.reason


@pytest.mark.asyncio
async def test_finalize_attributes_decomposes_and_assigns(repo):
    repo_dir, sha = repo
    out = await discover_finalize(_input(repo_dir, sha))
    assert out.attribution.coverage.state is CollectionState.MEASURED
    assert out.decomposition.collected.state is CollectionState.MEASURED
    assert out.decomposition.by_capability["BC-001"] == 1
    assert out.ownership.collected.state is CollectionState.MEASURED
    payments = next(e for e in out.ownership.entities if e.entity == "payment")
    assert payments.outcome is OwnershipOutcome.OWNED
    assert payments.owner == "BC-001"


@pytest.mark.asyncio
async def test_the_seam_carries_real_producer_output_end_to_end(repo):
    """E-47c's review found a fabricated field every unit test missed, and
    the fix commit named the cause: "unit tests built inputs decompose() would
    never produce." So this pipes merge() -> build_context() -> stamp() ->
    apply() -> discover_finalize with no hand-built member anywhere.
    """
    repo_dir, sha = repo
    source = SourceCandidate(
        signal=ScanSignalId.S3,
        local_id="S3-payments",
        name="payments",
        rule="s3_http_route",
        detail="one POST route",
        confidence_contribution=Confidence.HIGH,
        members=[
            CandidateMember(
                kind=MemberKind.HTTP_ROUTE, value="POST /api/payments", path="pay/api.py", line=2
            )
        ],
    )
    merged = merge([source], {ScanSignalId.S3: MEASURED})
    scan = _scan(candidates=merged.candidates, sources=[source])
    inventory = {
        "pay/api.py": "from pay.models import Order\n",
        "pay/models.py": "class Order(Base):\n    __tablename__ = 'payments'\n",
    }
    context = build_context(scan, inventory, [])
    applied = apply(context, stamp(context, None))
    assert [c.local_key for c in applied.locked] == ["C-01"]

    out = await discover_finalize(
        DiscoverFinalizeInput(
            repo_dir=repo_dir,
            commit_sha=sha,
            # bc_id stands in for the lock's attachment; every member below came
            # from apply(), which got it from merge().
            members={"BC-001": list(applied.locked[0].members)},
            entry_point_paths=["pay/api.py"],
            schema_collected=MEASURED,
            contract_collected=MEASURED,
        )
    )
    assert out.decomposition.by_capability["BC-001"] == 1
    payments = next(e for e in out.ownership.entities if e.entity == "payment")
    assert payments.owner == "BC-001"


@pytest.mark.asyncio
async def test_an_unreadable_tree_degrades_to_three_not_collected_reports(repo):
    """DD9: everything except the capability set itself degrades per-report
    INSIDE the map. The map still ships, with the gap visible where it
    happened."""
    repo_dir, _ = repo
    out = await discover_finalize(_input(repo_dir, "0" * 40))
    assert out.attribution.coverage.state is CollectionState.NOT_COLLECTED
    assert out.attribution.meets_floor is False
    assert out.decomposition.collected.state is CollectionState.NOT_COLLECTED
    assert out.ownership.collected.state is CollectionState.NOT_COLLECTED
    assert "could not read the tree" in out.ownership.collected.reason


@pytest.mark.asyncio
async def test_a_degraded_contract_tier_fails_decompose_and_assign_closed(repo):
    """E-47c D9: a degraded contract tier must not read as a capability that
    genuinely exposes nothing. Attribution is unaffected -- it reads blobs,
    not S3."""
    repo_dir, sha = repo
    out = await discover_finalize(_input(repo_dir, sha, contract_collected=NC))
    assert out.attribution.coverage.state is CollectionState.MEASURED
    assert out.decomposition.collected.state is CollectionState.NOT_COLLECTED
    assert out.ownership.collected.state is CollectionState.NOT_COLLECTED
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_finalize_activity.py -v`
Expected: FAIL — `ImportError: cannot import name 'contract_collected'`

- [ ] **Step 3: Write the implementation**

Append to `src/sdlc/assessment/discover/context.py`:

```python
def _row(scan: ScanResult, signal_id: ScanSignalId) -> Measurement:
    row = next((r for r in scan.signals if r.signal is signal_id), None)
    if row is None:
        return Measurement.not_collected(f"{signal_id.value} has no row in this ScanResult")
    return row.collected


def schema_collected(scan: ScanResult) -> Measurement:
    """S2's row, which is assign()'s `schema_collected` argument."""
    return _row(scan, ScanSignalId.S2)


def contract_collected(scan: ScanResult) -> Measurement:
    """S3 AND S4, as one Measurement (P2-D5).

    decompose() documents its argument as "S3's (and S4's) collection state",
    and CONTRACT_KINDS includes FRONTEND_ROUTE, which only S4 emits. Deriving
    this from S3 alone would let a dead S4 read as a capability that genuinely
    exposes no frontend route -- the FR-915 conflation, one signal removed.
    """
    rows = {sid: _row(scan, sid) for sid in (ScanSignalId.S3, ScanSignalId.S4)}
    degraded = sorted(
        (sid.value, m) for sid, m in rows.items() if m.state is not CollectionState.MEASURED
    )
    if degraded:
        name, measurement = degraded[0]
        return Measurement.not_collected(f"{name} did not collect: {measurement.reason}")
    return Measurement.measured(sum(m.value or 0.0 for m in rows.values()))
```

Extend `context.py`'s imports to `from ...measurement import CollectionState, Measurement`.

Append to `src/sdlc/assessment/activities.py`, adding to its imports:

```python
from .discover.attribution import attribute
from .discover.models import (
    AttributionReport,
    DecompositionReport,
    EntityDeclaration,
    FileBucket,
    OwnershipOutcome,
    OwnershipReport,
    ReferenceGraph,
)
from .discover.operations import decompose
from .discover.ownership import assign
```

```python
class DiscoverFinalizeInput(BaseModel):
    """DD4 step 7's input: the LOCKED capability set, keyed by bc_id.

    attribute() takes `members: bc_id -> paths`, and no bc_id exists until the
    lock has run -- which is why attribution runs after disposition rather
    than before (E-47b D1).
    """

    repo_dir: str
    commit_sha: str
    members: dict[str, list[CandidateMember]] = Field(default_factory=dict)
    entry_point_paths: list[str] = Field(default_factory=list)
    schema_collected: Measurement
    contract_collected: Measurement


class DiscoverFinalizeOutcome(BaseModel):
    attribution: AttributionReport
    decomposition: DecompositionReport
    ownership: OwnershipReport


def no_finalize(reason: str) -> DiscoverFinalizeOutcome:
    """DD9: the capability set survived, so the map ships -- with the gap
    visible in each report that could not be computed. Never empty MEASURED
    reports: a tree we could not read is not a tree with no operations.

    Public, unlike _no_context: the workflow imports it as run_or_degrade's
    fallback, the way it imports unbuilt() and skipped().
    """
    nc = Measurement.not_collected(reason)
    return DiscoverFinalizeOutcome(
        attribution=AttributionReport(
            counts={b: 0 for b in FileBucket},
            coverage=nc,
            meets_floor=False,
            graph=ReferenceGraph(unresolved_relative_rate=nc),
        ),
        decomposition=DecompositionReport(collected=nc),
        ownership=OwnershipReport(counts={o: 0 for o in OwnershipOutcome}, collected=nc),
    )


@activity.defn
async def discover_finalize(inp: DiscoverFinalizeInput) -> DiscoverFinalizeOutcome:
    """Coverage, L2 operations and entity ownership over the locked set.

    Reads the tree a second time, deliberately (DD4): passing the reference
    graph from discover_context would push an entire tree's edge list through
    workflow history, which is the open FR-702 hazard. Blob reads are cheap
    beside a model call.

    Entity declarations are re-derived here rather than reconstructed from the
    ScanResult (P2-D8): EntityDeclaration needs (name, path, line), and S2's
    SourceCandidate carries names on `members` and lines on `evidence` with no
    join between them. schema.declarations() is pure over the same blobs at
    the same pinned commit, so what it sees is what S2 saw -- and the
    adaptation lives here, where both types are in scope, so discover/ still
    imports no signal (E-47c D2).
    """
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, skipped = _source_blobs(
            inp.repo_dir, inp.commit_sha, paths, SOURCE_EXTENSIONS + schema.EXTRA_EXTENSIONS
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("discover_finalize tree read failed: %s", exc)
        return no_finalize(f"could not read the tree: {type(exc).__name__}: {exc}"[:300])

    member_paths = {
        bc_id: sorted({m.path for m in members if m.path}) for bc_id, members in inp.members.items()
    }
    # attribute() filters the denominator to SOURCE_EXTENSIONS itself, so the
    # wider schema read above costs one pass, not a second git call.
    attribution = attribute(blobs, skipped, member_paths, inp.entry_point_paths)
    decomposition = decompose(inp.members, contract_collected=inp.contract_collected)
    declarations = [
        EntityDeclaration(name=d.name, path=d.path, line=d.line) for d in schema.declarations(blobs)
    ]
    ownership = assign(
        declarations,
        member_paths,
        decomposition.operations,
        schema_collected=inp.schema_collected,
        contract_collected=inp.contract_collected,
    )
    return DiscoverFinalizeOutcome(
        attribution=attribution, decomposition=decomposition, ownership=ownership
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_finalize_activity.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/context.py src/sdlc/assessment/activities.py tests/test_discover_finalize_activity.py
git commit -m "feat(discover): attribute + decompose + assign, wired at last (E-48 DD4)"
```

---

### Task 9: `_discover` wired

The phase body. Everything above exists to make this a short function whose failure paths are all named.

Four existing tests in `tests/test_assessment_workflow.py` break here, all for the same reason: `PHASE_OWNER` loses its `DISCOVER` entry (exactly as it lost `SCAN` in E-46), so `unbuilt(PhaseId.DISCOVER)` becomes a `KeyError`. Step 1 repairs them before the change lands.

**Files:**
- Modify: `src/sdlc/workflows/assessment.py`
- Modify: `src/sdlc/worker.py` (register four activities)
- Test: `tests/test_assessment_workflow.py` (repair + append)

**Interfaces:**
- Consumes: `apply`, `stamp`, `build_map`, `fingerprint_of` from `sdlc.assessment.discover.apply`; `context_digest` from `sdlc.assessment.discover.map`; `schema_collected`, `contract_collected` from `sdlc.assessment.discover.context`; `NO_PROPOSER` from `sdlc.memoization.cache`; the four activities from tasks 6–8
- Produces: `AssessmentInput.project_key`, `ScanOutcome.tree_hash`, `DiscoverOutcome`, `no_discover(reason)`, `AssessmentWorkflow._discover(inp, triage, scan_out) -> DiscoverOutcome`

- [ ] **Step 1: Repair the four tests the `PHASE_OWNER` change will break**

In `tests/test_assessment_workflow.py`, add this helper after `_scan_result()`:

```python
def _rest_after_discover(discover: PhaseResult | None = None) -> list[PhaseResult]:
    """SCAN (E-46) and DISCOVER (E-48) are built; the other four are stubs.

    DISCOVER defaults to not_collected so a caller that does not care about
    the discover pairing need not supply a CapabilityMap.
    """
    out = [
        PhaseResult(phase=PhaseId.SCAN, collected=Measurement.measured(0.0)),
        discover
        or PhaseResult(
            phase=PhaseId.DISCOVER, collected=Measurement.not_collected("discover not run")
        ),
    ]
    out += [
        unbuilt(p) for p in PHASE_ORDER if p not in (PhaseId.INIT, PhaseId.SCAN, PhaseId.DISCOVER)
    ]
    return out
```

Then replace the four bodies:

```python
def test_every_post_init_phase_has_an_owner():
    # SCAN is built in E-46 and DISCOVER in E-48, so neither is in
    # PHASE_OWNER; every other post-init phase still names the item that owes
    # its body.
    assert set(PHASE_OWNER) == set(PHASE_ORDER) - {PhaseId.INIT, PhaseId.SCAN, PhaseId.DISCOVER}


def test_assemble_on_an_admitted_run_reports_partial_once_scan_lands():
    a = assemble("/r", _init(), True, "verdict ready", _rest_after_discover(), scan=_scan_result())
    assert a.admitted is True
    assert a.terminal_status == PARTIAL
    assert [p.phase for p in a.phases] == list(PHASE_ORDER)


def test_assemble_orders_phases_canonically_regardless_of_arrival():
    a = assemble(
        "/r",
        _init(),
        True,
        "verdict ready",
        list(reversed(_rest_after_discover())),
        scan=_scan_result(),
    )
    assert [p.phase for p in a.phases] == list(PHASE_ORDER)


def test_assemble_rejects_a_partial_rest_on_an_admitted_run():
    """An admitted run has no 'unreached' phases -- run() always supplies all
    six. A missing one is a caller bug, and filling it with skipped() would
    stamp 'not admitted' onto an artifact whose admitted field is True -- a
    contradiction on the face of an FR-921 bundle (review finding 1). The
    not-admitted path still fills with skipped(), whose message is then
    truthful."""
    partial = [unbuilt(PhaseId.ASSESS)]  # one of the unbuilt phases
    with pytest.raises(ValueError, match="admitted"):
        assemble("/r", _init(), True, "verdict ready", partial)
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_assessment_workflow.py`:

```python
# --- E-48 plan 2: discover is a built phase ------------------------------
from sdlc.workflows.assessment import DiscoverOutcome, no_discover


def test_discover_is_no_longer_an_unbuilt_phase():
    """E-46 dropped SCAN from PHASE_OWNER when its body landed; this is the
    same move for DISCOVER, and terminal_status derives the change."""
    assert PhaseId.DISCOVER not in PHASE_OWNER


def test_the_input_carries_a_project_key():
    """Capability identity is per-project (E-47a), and a value derived from
    repo_dir would move every client-cited BC-NNN when a checkout moves.
    Named after PipelineConfig.project_key, which addresses the same SQLite."""
    assert AssessmentInput(repo_dir="/r").project_key == "default"


def test_no_discover_carries_its_reason_and_no_map():
    out = no_discover("S5 did not collect: nothing merged")
    assert out.map is None
    assert out.result.phase is PhaseId.DISCOVER
    assert out.result.collected.state is CollectionState.NOT_COLLECTED
    assert "S5" in out.result.collected.reason


def test_a_measured_discover_reaches_the_artifact():
    """The pairing Assessment._discover_agrees_with_its_phase enforces, from
    the workflow's side: assemble() must be handed the map whenever the phase
    row is measured."""
    cap_map = CapabilityMap(collected=Measurement.measured(0.0))
    rest = _rest_after_discover(PhaseResult(phase=PhaseId.DISCOVER, collected=cap_map.collected))
    a = assemble("/r", _init(), True, "verdict ready", rest, scan=_scan_result(), discover=cap_map)
    assert a.discover is not None
    assert a.terminal_status == PARTIAL


def test_the_run_body_passes_the_scan_and_triage_into_discover():
    """_discover needs the tree hash, the pinned commit and the candidate set;
    a body that still called self._discover(inp) would compile and silently
    rediscover nothing."""
    src = inspect.getsource(AssessmentWorkflow.run)
    assert "self._discover(inp, init.triage, scan_out)" in src
    assert "discover=discover_out.map" in src
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_assessment_workflow.py -v`
Expected: FAIL — `ImportError: cannot import name 'DiscoverOutcome'`

- [ ] **Step 4: Write the implementation**

In `src/sdlc/workflows/assessment.py`, extend the passed-through import block:

```python
from ..assessment.activities import (
    AssessmentTree,
    AssessmentTreeInput,
    DiscoverContextInput,
    DiscoverFinalizeInput,
    DiscoverLockInput,
    DiscoverMemoInput,
    DiscoverMemoStoreInput,
    ScanSignalInput,
    assessment_resolve_tree,
    discover_context,
    discover_finalize,
    discover_lock,
    discover_memo_load,
    discover_memo_store,
    no_finalize,
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
from ..assessment.discover.apply import (
    apply,
    build_map,
    fingerprint_of,
    stamp,
)
from ..assessment.discover.context import (
    contract_collected,
    schema_collected,
)
from ..assessment.discover.map import CapabilityMap, context_digest
from ..capability.models import ProposedCapability
from ..memoization.cache import NO_PROPOSER
```

(The existing `from ..assessment.discover.map import CapabilityMap` line is replaced by the one above.)

Add `project_key` to `AssessmentInput`:

```python
    # Capability identity is per-project (E-47a), and this is the scope every
    # BC-NNN is allocated within. Deliberately NOT derived from repo_dir: a
    # value computed from a filesystem path moves every client-cited id when
    # a checkout moves. Named after PipelineConfig.project_key, which
    # addresses the same SQLite file.
    project_key: str = "default"
```

Drop the `DISCOVER` entry from `PHASE_OWNER`, leaving the comment updated:

```python
# The E-item owing each unbuilt phase body, so an empty assessment says WHY
# it is empty rather than merely being empty. SCAN dropped here in E-46 and
# DISCOVER in E-48: their bodies are built, so nothing owes them.
PHASE_OWNER: dict[PhaseId, str] = {
    PhaseId.ASSESS: "E-49",
    PhaseId.REPORT: "E-52",
    PhaseId.GENERATE: "E-52",
    PhaseId.FINISH: "E-51",
}
```

Add `tree_hash` to `ScanOutcome`, and the discover activity options and outcome type:

```python
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


DISCOVER_ACT = dict(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=2)
)
# Three attempts, not two: an IdentityConflictError means a concurrent
# assessment wrote first, and a retry re-reads the registry and re-matches
# (E-47a's loser behaviour) rather than replaying computed attachments.
LOCK_ACT = dict(
    start_to_close_timeout=timedelta(minutes=2), retry_policy=RetryPolicy(maximum_attempts=3)
)


class DiscoverOutcome(BaseModel):
    """discover's two halves, mirroring ScanOutcome."""

    result: PhaseResult
    map: CapabilityMap | None = None


def no_discover(reason: str) -> DiscoverOutcome:
    """DD9's phase-level failure: the capability set itself could not be
    produced, so there is no map. Everything short of that degrades
    per-report INSIDE the map instead."""
    return DiscoverOutcome(
        result=PhaseResult(phase=PhaseId.DISCOVER, collected=Measurement.not_collected(reason))
    )
```

In `_scan`, return the tree hash on the success path:

```python
return ScanOutcome(
    result=PhaseResult(phase=PhaseId.SCAN, collected=Measurement.measured(float(measured))),
    scan=scan,
    tree_hash=tree.tree_hash,
)
```

Replace `_discover`:

```python
async def _discover(
    self, inp: AssessmentInput, triage: RepoTriage, scan_out: ScanOutcome
) -> DiscoverOutcome:
    """Phase 3 (E-48). DD4's pipeline, minus the proposer plan 3 inserts
    between `baseline_dispositions` and `stamp`.

    Nothing here executes the assessed repository's code -- both
    activities read blob bytes at the pinned commit (NFR-9).
    """
    if scan_out.scan is None:
        return no_discover(f"scan produced no result: {scan_out.result.collected.reason}")
    s5 = next((r for r in scan_out.scan.signals if r.signal is ScanSignalId.S5), None)
    if s5 is None or s5.collected.state is not CollectionState.MEASURED:
        # DD9's first row. Without a candidate set there is nothing to
        # dispose over, and an empty map would claim the repository has
        # no capabilities rather than that the scan could not see them.
        return no_discover(f"S5 did not collect: {s5.collected.reason if s5 else 'no S5 row'}")

    try:
        context = await workflow.execute_activity(
            discover_context,
            DiscoverContextInput(
                repo_dir=inp.repo_dir,
                commit_sha=triage.commit_sha,
                tree_hash=scan_out.tree_hash,
                scan=scan_out.scan,
            ),
            **DISCOVER_ACT,
        )
    except Exception as e:  # noqa: BLE001
        return no_discover(f"discover_context failed: {type(e).__name__}: {e}"[:300])
    if context.collected.state is not CollectionState.MEASURED:
        return no_discover(f"the context could not be built: {context.collected.reason}")

    # P2-D6: NO_PROPOSER, never "". Plan 3 passes the role's prompt_sha
    # and model here, and a baseline-only map must never share a key with
    # a proposer map.
    memo_key = DiscoverMemoInput(
        project=inp.project_key,
        tree_hash=scan_out.tree_hash,
        context_digest=context_digest(context),
        prompt_sha=NO_PROPOSER,
        model=NO_PROPOSER,
    )
    # A cache read that fails is a MISS, never a phase failure.
    hit = await run_or_degrade(discover_memo_load, memo_key, DISCOVER_ACT, fallback=lambda: None)
    if hit is not None:
        return DiscoverOutcome(
            result=PhaseResult(phase=PhaseId.DISCOVER, collected=hit.collected), map=hit
        )

    # Plan 3 replaces `None` with the proposer's DiscoverProposal; stamp()
    # already knows what to do with either (DD7).
    applied = apply(context, stamp(context, None))

    try:
        lock = await workflow.execute_activity(
            discover_lock,
            DiscoverLockInput(
                project=inp.project_key,
                run_id=workflow.info().run_id,
                proposed=[
                    ProposedCapability(local_key=c.local_key, fingerprint=fingerprint_of(c))
                    for c in applied.locked
                ],
            ),
            **LOCK_ACT,
        )
    except Exception as e:  # noqa: BLE001
        # E-47a's fail-closed rule (DD9): proceeding produces a complete,
        # plausible-looking map in which every id is wrong.
        return no_discover(f"identity lock failed: {type(e).__name__}: {e}"[:300])

    bc_of = {a.local_key: a.bc_id for a in lock.attachments}
    try:
        finalized = await run_or_degrade(
            discover_finalize,
            DiscoverFinalizeInput(
                repo_dir=inp.repo_dir,
                commit_sha=triage.commit_sha,
                members={bc_of[c.local_key]: list(c.members) for c in applied.locked},
                entry_point_paths=list(context.entry_point_paths),
                schema_collected=schema_collected(scan_out.scan),
                contract_collected=contract_collected(scan_out.scan),
            ),
            DISCOVER_ACT,
            fallback=lambda: no_finalize("discover_finalize did not run to completion"),
        )
        capability_map = build_map(
            applied,
            bc_of,
            advisories=lock.advisories,
            attribution=finalized.attribution,
            decomposition=finalized.decomposition,
            ownership=finalized.ownership,
        )
    except Exception as e:  # noqa: BLE001
        # build_map raises only on a lock defect (a boundary with no
        # bc_id). Reporting it as a phase failure keeps the reason on the
        # artifact instead of retrying a workflow task forever.
        return no_discover(f"the map could not be assembled: {type(e).__name__}: {e}"[:300])

    await run_or_degrade(
        discover_memo_store,
        DiscoverMemoStoreInput(
            key=memo_key, registry_version=lock.registry_version, out=capability_map
        ),
        DISCOVER_ACT,
        fallback=lambda: False,
    )
    return DiscoverOutcome(
        result=PhaseResult(phase=PhaseId.DISCOVER, collected=capability_map.collected),
        map=capability_map,
    )
```

Rewire `run`:

```python
self._status = "running"
scan_out = await self._scan(inp, init.triage)
discover_out = await self._discover(inp, init.triage, scan_out)
rest = [
    scan_out.result,
    discover_out.result,
    await self._assess(inp),
    await self._report(inp),  # AFTER assess -- FR-911 dev. (a)
    await self._generate(inp),
    await self._finish(inp),
]
return self._done(
    assemble(inp.repo_dir, init, True, why, rest, scan=scan_out.scan, discover=discover_out.map)
)
```

In `src/sdlc/worker.py`, add `discover_finalize, discover_lock, discover_memo_load, discover_memo_store` to the assessment import block (line 37) and to the `activities=[...]` list beside `discover_context` (line 134).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_assessment_workflow.py tests/test_assessment_models.py tests/test_assessment_scan_phase.py tests/test_assessment_cli_wiring.py -v`
Expected: all pass

- [ ] **Step 6: Run the whole non-temporal suite**

Run: `uv run pytest tests/ -q -m "not temporal"`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/workflows/assessment.py src/sdlc/worker.py tests/test_assessment_workflow.py
git commit -m "feat(discover): _discover wired -- DISCOVER measured with no model in it (E-48 DD4)"
```

---

### Task 10: The temporal end-to-end

The integration test E-47b deferred to this item ("E-48 brings the first integration test when it wires discover"). It adds **no new workflow fan-out**, which matters on a host that already struggles with the `TidyUpWorkflow` case (P5's deferred e2e).

It also carries the seam weight the spec assigns it: real `merge()` output flows into the real `discover_context`… `apply()`… `discover_lock` chain with no hand-built intermediate structs. E-47c's review found a fabricated field that every unit test missed, and the fix commit named the cause — *"unit tests built inputs `decompose()` would never produce."*

**Files:**
- Modify: `tests/test_assessment_workflow_e2e.py`
- Test: itself

**Interfaces:**
- Consumes: `AssessmentWorkflow`, `TriageWorkflow`, the real `discover_context` / `discover_lock` / `discover_finalize` / memo activities
- Produces: two tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_assessment_workflow_e2e.py`, extending its imports with:

```python
from sdlc.assessment.activities import (
    discover_context,
    discover_finalize,
    discover_lock,
    discover_memo_load,
    discover_memo_store,
)
from sdlc.assessment.discover.map import DiscoverAction
from sdlc.assessment.scan.models import (
    CATEGORIES,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanSignalResult,
    SignalOutput,
    SourceCandidate,
    family_of,
)
from sdlc.capability.store import BoardIdentityStore
```

```python
# --- E-48 plan 2: DISCOVER goes measured ---------------------------------
#
# S1 and S3 are faked to produce real SourceCandidates so merge() has
# something to merge and S5 measures; every other scan signal stays the real
# (degrading) activity. The two fakes are shaped exactly as their signals emit
# -- one domain-named candidate and one layer-named one, which exercises both
# baseline branches through the whole spine.


def _measured_row(signal_id):
    val = Measurement.measured(1.0)
    return ScanSignalResult(
        signal=signal_id,
        family=family_of(signal_id),
        version=1,
        source=SignalSource.COMPUTED,
        collected=val,
        categories={k: val for k in CATEGORIES[signal_id]},
    )


@activity.defn(name="scan_packages")
async def fake_s1(inp) -> SignalOutput:
    return SignalOutput(
        row=_measured_row(ScanSignalId.S1),
        sources=[
            SourceCandidate(
                signal=ScanSignalId.S1,
                local_id="S1-services",
                name="services",
                rule="s1_layer_name",
                detail="a layer, not a capability",
                confidence_contribution=Confidence.LOW,
                members=[
                    CandidateMember(
                        kind=MemberKind.PACKAGE_PATH, value="services", path="services/__init__.py"
                    )
                ],
            )
        ],
    )


@activity.defn(name="scan_entrypoints")
async def fake_s3(inp) -> SignalOutput:
    return SignalOutput(
        row=_measured_row(ScanSignalId.S3),
        sources=[
            SourceCandidate(
                signal=ScanSignalId.S3,
                local_id="S3-payments",
                name="payments",
                rule="s3_http_route",
                detail="one POST route",
                confidence_contribution=Confidence.HIGH,
                members=[
                    CandidateMember(
                        kind=MemberKind.HTTP_ROUTE,
                        value="POST /api/payments",
                        path="pay/api.py",
                        line=12,
                    )
                ],
            )
        ],
    )


DISCOVER_ACTS = [
    discover_context,
    discover_lock,
    discover_finalize,
    discover_memo_load,
    discover_memo_store,
]

# fake_s1/fake_s3 shadow the real scan_packages/scan_entrypoints by activity
# NAME, so the real ones must be dropped from the list rather than added to.
DISCOVER_WORKER_ACTIVITIES = [
    a for a in ACTIVITIES if a not in (scan_packages, scan_entrypoints)
] + [fake_s1, fake_s3, *DISCOVER_ACTS]


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """The identity registry and the memo cache, per test. Both are
    process-global by default, and the lock WRITES."""
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / "memo"))


async def test_discover_goes_measured_and_the_map_reaches_the_artifact(isolated_state):
    """The claim plan 2 exists to make true: DISCOVER is measured with no
    model in it, and terminal_status still derives assessed:partial because
    four phases remain stubs."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=WORKFLOWS,
            activities=DISCOVER_WORKER_ACTIVITIES,
        ):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(repo_dir="/r"),
                id=f"assess-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            result = await handle.result()

    assert result.terminal_status == PARTIAL
    discover_row = next(p for p in result.phases if p.phase is PhaseId.DISCOVER)
    assert discover_row.collected.state is CollectionState.MEASURED
    assert result.discover is not None

    # DD6 end to end: the domain-named candidate is confirmed and carries a
    # durable id; the layer-named one is de-scoped and carries none.
    assert [c.bc_id for c in result.discover.capabilities] == ["BC-001"]
    assert result.discover.capabilities[0].name == "payments"
    assert result.discover.by_action == {DiscoverAction.CONFIRM: 1}
    by_candidate = {d.candidate_id: d for d in result.discover.dispositions}
    assert len(by_candidate) == 2
    assert {d.action for d in by_candidate.values()} == {
        DiscoverAction.CONFIRM,
        DiscoverAction.DE_SCOPE,
    }
    assert all(d.source.value == "baseline" for d in by_candidate.values())

    # DD9 end to end: repo_dir="/r" does not exist, so finalize's three
    # reports degrade individually and the map still ships with the gap
    # visible where it happened.
    assert result.discover.attribution.coverage.state is CollectionState.NOT_COLLECTED
    assert result.discover.decomposition.collected.state is CollectionState.NOT_COLLECTED
    assert result.discover.ownership.collected.state is CollectionState.NOT_COLLECTED


async def test_a_second_assessment_of_the_same_tree_hits_the_memo(isolated_state):
    """DD10: an unchanged tree is a cache hit, and the ids clients cite do not
    move because the assessment ran again. The hit skips the lock, which is
    safe precisely because identity_registry_version is a key term."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=WORKFLOWS,
            activities=DISCOVER_WORKER_ACTIVITIES,
        ):
            first = await (
                await env.client.start_workflow(
                    AssessmentWorkflow.run,
                    AssessmentInput(repo_dir="/r"),
                    id=f"assess-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )
            ).result()
            second = await (
                await env.client.start_workflow(
                    AssessmentWorkflow.run,
                    AssessmentInput(repo_dir="/r"),
                    id=f"assess-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )
            ).result()

    assert first.discover.model_dump_json() == second.discover.model_dump_json()

    # The discriminating assertion. Identical maps alone would NOT prove a
    # hit: on a miss the lock would re-run, match the same fingerprints and
    # hand back the same ids. What only a hit explains is that the registry
    # never moved a second time -- steps 3-8 were skipped, lock included.
    store = BoardIdentityStore()
    try:
        assert store.registry_version("default") == 1
    finally:
        store.close()
```

- [ ] **Step 2: Run the two new tests**

Run: `uv run pytest tests/test_assessment_workflow_e2e.py -v -m temporal -k "discover or memo"`
Expected: 2 passed.

These are the only tests in this plan that exercise already-committed code rather than driving new code into existence — task 9 built the phase, and this task proves it end to end. A failure here is a defect in task 9, not a missing module: read the assertion that failed and fix the workflow, not the test.

- [ ] **Step 3: Run the whole temporal suite**

Run: `uv run pytest tests/test_assessment_workflow_e2e.py -v -m temporal`
Expected: 7 passed (the five E-45/E-46 tests plus these two)

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest tests/ -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_assessment_workflow_e2e.py
git commit -m "test(discover): the phase end to end -- DISCOVER measured, memo hit, reports degraded (E-48)"
```

---

## Plan 2 exit criteria

- `uv run pytest tests/ -q` green, including `-m temporal`.
- An admitted assessment reports **DISCOVER measured** and carries a `CapabilityMap`; `terminal_status` is `assessed:partial`.
- `PHASE_OWNER` names four phases (E-49, E-52, E-52, E-51). Nothing owes DISCOVER.
- `resolve()`, `attribute()`, `decompose()` and `assign()` all have a production caller for the first time.
- No proposer exists yet, and the map says so: every disposition reads `source=baseline`.
- No roadmap edits. The ticks land with plan 3 — plan 2 makes DISCOVER measured, but E-48's clauses D1–D8 are not satisfied until the judgment layer ships.

## What plan 3 picks up

`agents/discover/` (`agent.yaml`, `instructions.md`, `agent.py`) joining `OPTIONAL_ROLES`; `t_discover` called between `baseline_dispositions` and `stamp`; DD8 items 4 and 5 as `verify_discover_refs` (an `EvidenceRef` path resolving at the pinned commit, a quote byte-verifying under `Profile.VERBATIM_BYTES`) plus the fabrication-rate guard over `total_references` — **which must guard the zero denominator plan 2 always produces**; `blueprint.py` + `blueprints/apqc.yaml` (clause D8); D7's derived domain model; and `CapabilityMap.domain_model` / `.blueprint`, added in `build_map` where their producers will be.
