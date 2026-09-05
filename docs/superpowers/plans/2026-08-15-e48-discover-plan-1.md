# E-48 discover proposers — plan 1 of 3: inputs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the contracts, the `MemberKind → SignalTier` map, and the deterministic context packet that the discover phase will hand its proposer — leaving `_discover` still reporting `unbuilt`.

**Architecture:** Four pure modules under `src/sdlc/assessment/discover/` plus one activity. Everything computable about a scan candidate — cohesion, coupling, the delivery-channel guardrail evidence, and the security/QA joins — is computed here by code, so that plan 3's model can only *judge* a packet rather than author a map (spec DD1 / ADR-22). Nothing in this plan calls a model, and nothing wires the phase.

**Tech Stack:** Python 3.14, Pydantic v2, Temporal (`temporalio`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-15-e48-discover-proposers-design.md`

## Global Constraints

- **Purity.** `discover/` modules import Pydantic, `measurement.py`, `capability/models.py`, and scan **rule** modules only. They must never import `sdlc/models.py`, `sdlc/assessment/activities.py`, or `temporalio`. A signal module (`scan/signals/*.py`) must never be imported — a signal is a producer with a memo key and a version, and importing one would make this package part of that signal's hashed surface (E-47c D2).
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
| `src/sdlc/assessment/discover/tiers.py` | `MemberKind → SignalTier`, member grouping | 1 |
| `src/sdlc/assessment/discover/map.py` | phase-level contracts (three tasks, one module) | 2, 3, 4 |
| `src/sdlc/assessment/discover/context.py` | cohesion/coupling arithmetic, then the packet builder | 5, 6 |
| `src/sdlc/assessment/models.py` | `Assessment.discover` + paired validator | 7 |
| `src/sdlc/assessment/activities.py` | `discover_context` activity | 8 |
| `src/sdlc/worker.py` | activity registration | 8 |

`map.py` is a new module rather than an addition to `discover/models.py`: that file holds E-47b/c's sub-mechanism reports and is already 387 lines, and the phase artifact is a different layer (spec DD2).

---

### Task 1: The `MemberKind → SignalTier` map

Two modules explicitly reserve this map for E-48 and forbid deriving it from its neighbour: `scan/models.py:95` requires it be **total**, and `discover/models.py:151` warns that it and `CONTRACT_KINDS` must never be derived from each other. The tests below are what make both real.

**Files:**
- Create: `src/sdlc/assessment/discover/tiers.py`
- Test: `tests/test_discover_tiers.py`

**Interfaces:**
- Consumes: `SignalTier` from `sdlc.capability.models`; `MemberKind`, `CandidateMember` from `sdlc.assessment.scan.models`
- Produces: `MEMBER_TIERS: dict[MemberKind, SignalTier]`, `group_by_tier(members: Iterable[CandidateMember]) -> dict[SignalTier, list[str]]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_tiers.py
"""FR-913 (E-48 DD3): MemberKind -> SignalTier, total, and deliberately not
CONTRACT_KINDS."""

from __future__ import annotations

import random

from sdlc.assessment.discover.models import CONTRACT_KINDS
from sdlc.assessment.discover.tiers import MEMBER_TIERS, group_by_tier
from sdlc.assessment.scan.models import CandidateMember, MemberKind
from sdlc.capability.models import SignalTier


def test_every_member_kind_has_a_tier():
    """D13: the mapping is TOTAL. Adding a kind to the enum must fail here
    rather than silently landing in no tier."""
    assert set(MEMBER_TIERS) == set(MemberKind)


def test_contract_tier_and_contract_kinds_differ_by_exactly_db_table():
    """E-47c D4's warning, made checkable in both directions.

    A table is contract-tier IDENTITY evidence (a table name survives a
    refactor that renames every symbol) but it is NOT an operation -- an
    operation is something the system DOES, and a table is something it HAS.
    Deriving either set from the other would be wrong.
    """
    tier_contract = {k for k, t in MEMBER_TIERS.items() if t is SignalTier.CONTRACT}
    assert tier_contract - CONTRACT_KINDS == {MemberKind.DB_TABLE}
    assert CONTRACT_KINDS - tier_contract == set()


def test_entity_name_belongs_to_neither_set():
    """The other half of the same point: ENTITY_NAME reads as contract-ish
    vocabulary, but it is behavioral identity evidence and not an operation.
    The two vocabularies classify on different axes."""
    assert MEMBER_TIERS[MemberKind.ENTITY_NAME] is SignalTier.BEHAVIORAL
    assert MemberKind.ENTITY_NAME not in CONTRACT_KINDS


def test_group_by_tier_carries_every_tier_including_empty_ones():
    """An absent key and an empty list are different claims, and only one of
    them is true -- AttributionReport._counts_agree_with_files' rule."""
    grouped = group_by_tier(
        [
            CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay"),
        ]
    )
    assert set(grouped) == set(SignalTier)
    assert grouped[SignalTier.CONTRACT] == ["POST /pay"]
    assert grouped[SignalTier.BEHAVIORAL] == []


def test_group_by_tier_is_sorted_and_deduped():
    grouped = group_by_tier(
        [
            CandidateMember(kind=MemberKind.DB_TABLE, value="orders"),
            CandidateMember(kind=MemberKind.DB_TABLE, value="accounts"),
            CandidateMember(kind=MemberKind.DB_TABLE, value="orders", path="other.py"),
        ]
    )
    assert grouped[SignalTier.CONTRACT] == ["accounts", "orders"]


def test_group_by_tier_is_order_independent():
    """NFR-10: discovery order must not reach the artifact."""
    members = [
        CandidateMember(kind=MemberKind.HTTP_ROUTE, value="GET /a"),
        CandidateMember(kind=MemberKind.TEST_NAME, value="test_b"),
        CandidateMember(kind=MemberKind.FILE_PATH, value="c.py"),
        CandidateMember(kind=MemberKind.EXPORTED_SYMBOL, value="d"),
    ]
    first = group_by_tier(members)
    for _ in range(5):
        shuffled = members[:]
        random.shuffle(shuffled)
        assert group_by_tier(shuffled) == first
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_tiers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.discover.tiers'`

- [ ] **Step 3: Write the implementation**

```python
# src/sdlc/assessment/discover/tiers.py
"""FR-913 (E-48 DD3): MemberKind -> SignalTier.

Pure by design -- Pydantic-free, in fact. This module must never import
models.py, activities.py, or temporalio, exactly as the rest of discover/
must not.

Two modules reserve this map for E-48 and forbid deriving it from its
neighbour. scan/models.py's MemberKind docstring (D13) requires it be TOTAL:
"the value set is chosen so every CapabilityFingerprint tier has members that
can populate it". discover/models.py's CONTRACT_KINDS comment (E-47c D4)
forbids deriving it from that set, because "two uses of the word 'contract'
that agree only by coincidence" is the defect PipelineConfig.roles' boot-time
mirror assertion exists to prevent.

The warning is correct on the merits. The CONTRACT tier and CONTRACT_KINDS
differ by exactly DB_TABLE: a table name is expensive to change and therefore
strong identity evidence, but a table is not an OPERATION -- an operation is
something the system does, reachable from outside the capability, and a table
is something the system has. ENTITY_NAME makes the point from outside both
sets. test_discover_tiers.py asserts the difference in both directions.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...capability.models import SignalTier
from ..scan.models import CandidateMember, MemberKind

MEMBER_TIERS: dict[MemberKind, SignalTier] = {
    MemberKind.HTTP_ROUTE: SignalTier.CONTRACT,
    MemberKind.CLI_COMMAND: SignalTier.CONTRACT,
    MemberKind.DB_TABLE: SignalTier.CONTRACT,
    MemberKind.QUEUE_TOPIC: SignalTier.CONTRACT,
    MemberKind.GRPC_METHOD: SignalTier.CONTRACT,
    MemberKind.SCHEDULED_JOB: SignalTier.CONTRACT,
    MemberKind.FRONTEND_ROUTE: SignalTier.CONTRACT,
    MemberKind.TEST_NAME: SignalTier.BEHAVIORAL,
    MemberKind.ENTITY_NAME: SignalTier.BEHAVIORAL,
    MemberKind.EXPORTED_SYMBOL: SignalTier.STRUCTURAL,
    MemberKind.PACKAGE_PATH: SignalTier.LOCATIONAL,
    MemberKind.FILE_PATH: SignalTier.LOCATIONAL,
}


def group_by_tier(members: Iterable[CandidateMember]) -> dict[SignalTier, list[str]]:
    """Member values grouped into the tiers CapabilityFingerprint takes.

    Every tier is present, including empty ones: an absent key and an empty
    list are different claims. Sorted and deduped so equal observations
    compare equal regardless of discovery order (NFR-10).
    """
    out: dict[SignalTier, set[str]] = {t: set() for t in SignalTier}
    for member in members:
        out[MEMBER_TIERS[member.kind]].add(member.value)
    return {tier: sorted(values) for tier, values in out.items()}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_tiers.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/tiers.py tests/test_discover_tiers.py
git commit -m "feat(discover): MemberKind -> SignalTier, total and not CONTRACT_KINDS (E-48 DD3)"
```

---

### Task 2: The proposer-facing contracts

The model returns `ProposedDisposition`; code stamps provenance and produces `CandidateDisposition`. Two types rather than one, because **a model cannot self-certify where its own verdict came from** — a `source` field the model could fill would let a hallucinated disposition claim to be a code-computed baseline.

**Files:**
- Create: `src/sdlc/assessment/discover/map.py`
- Test: `tests/test_discover_map_dispositions.py`

**Interfaces:**
- Consumes: `EvidenceRef` from `sdlc.assessment.scan.models`
- Produces: `DiscoverAction`, `DispositionSource`, `SplitPartition`, `ProposedDisposition`, `DiscoverProposal`, `CandidateDisposition`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_map_dispositions.py
"""FR-913 (E-48): the proposer's output type and its code-stamped form."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.map import (
    CandidateDisposition,
    DiscoverAction,
    DiscoverProposal,
    DispositionSource,
    ProposedDisposition,
    SplitPartition,
)


def _disp(**kw):
    base = dict(
        candidate_id="C-01",
        action=DiscoverAction.CONFIRM,
        source=DispositionSource.BASELINE,
        rule="baseline_confirm",
    )
    return CandidateDisposition(**(base | kw))


def test_proposed_disposition_cannot_declare_its_own_source():
    """DD1/DD7: provenance is code's to stamp. A model that could set
    `source` could claim a hallucinated verdict was a computed baseline."""
    assert "source" not in ProposedDisposition.model_fields


def test_merge_names_a_target_and_nothing_else_does():
    _disp(action=DiscoverAction.MERGE, merge_into="C-02", rule="r")
    with pytest.raises(ValidationError, match="merge_into"):
        _disp(action=DiscoverAction.MERGE)
    with pytest.raises(ValidationError, match="merge_into"):
        _disp(action=DiscoverAction.CONFIRM, merge_into="C-02")


def test_split_needs_two_partitions_and_nothing_else_carries_any():
    _disp(
        action=DiscoverAction.SPLIT,
        partitions=(
            SplitPartition(name="a", member_values=("x",)),
            SplitPartition(name="b", member_values=("y",)),
        ),
    )
    with pytest.raises(ValidationError, match="two partitions"):
        _disp(
            action=DiscoverAction.SPLIT,
            partitions=(SplitPartition(name="a", member_values=("x",)),),
        )
    with pytest.raises(ValidationError, match="partitions"):
        _disp(
            action=DiscoverAction.CONFIRM,
            partitions=(
                SplitPartition(name="a", member_values=("x",)),
                SplitPartition(name="b", member_values=("y",)),
            ),
        )


def test_a_proposer_disposition_must_carry_a_rationale():
    """A baseline needs none -- its rule IS its rationale. A model verdict
    with no reasoning is unreviewable."""
    _disp(source=DispositionSource.BASELINE, rule="baseline_confirm")
    with pytest.raises(ValidationError, match="rationale"):
        _disp(source=DispositionSource.PROPOSER, rule="proposer", rationale="")


def test_split_partition_member_values_are_sorted_and_deduped():
    SplitPartition(name="a", member_values=("x", "y"))
    with pytest.raises(ValidationError, match="not sorted"):
        SplitPartition(name="a", member_values=("y", "x"))
    with pytest.raises(ValidationError, match="not sorted"):
        SplitPartition(name="a", member_values=("x", "x"))


def test_proposal_holds_dispositions_and_nothing_else():
    """DD1: the model returns dispositions. It does not return a map, a
    capability, a metric, or a file."""
    assert set(DiscoverProposal.model_fields) == {"dispositions"}
    p = DiscoverProposal(
        dispositions=[
            ProposedDisposition(
                candidate_id="C-01",
                action=DiscoverAction.CONFIRM,
                rationale="four routes and a table, one owner",
            )
        ]
    )
    assert p.dispositions[0].candidate_id == "C-01"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_map_dispositions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.discover.map'`

- [ ] **Step 3: Write the implementation**

```python
# src/sdlc/assessment/discover/map.py
"""FR-913 (E-48): the discover phase's contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as discover/models.py
and capability/models.py must not.

Separate from discover/models.py deliberately (DD2): that module holds E-47b/c's
SUB-MECHANISM reports (attribution, decomposition, ownership) and is already
387 lines. This one holds the PHASE artifact and the proposer's interface.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from ..scan.models import EvidenceRef


class DiscoverAction(str, Enum):
    """Clause D2. One verdict per candidate."""

    CONFIRM = "confirm"
    SPLIT = "split"
    MERGE = "merge"
    DE_SCOPE = "de_scope"
    FLAG = "flag"


class DispositionSource(str, Enum):
    """Who decided, and it is never the model's to claim (DD7).

    DROPPED and BASELINE must not converge: "a model decided this and cited
    something that does not exist" is evidence about the candidate, while "no
    model ran" is not. This is unbuilt_signal vs failed_signal, whose docstring
    states the rule -- "the reason strings must not converge".
    """

    BASELINE = "baseline"  # code's rule; no proposer consulted
    PROPOSER = "proposer"  # the model decided and its refs resolved
    DROPPED = "dropped"  # the model decided; verification refused it


class SplitPartition(BaseModel):
    """One side of a SPLIT. `member_values` must be a subset of the
    candidate's own members -- enforced at apply time (plan 2), where the
    candidate is in scope."""

    model_config = {"frozen": True}
    name: str
    member_values: tuple[str, ...]

    @model_validator(mode="after")
    def _member_values_are_sorted(self) -> "SplitPartition":
        if list(self.member_values) != sorted(set(self.member_values)):
            raise ValueError(
                f"member_values {self.member_values} are not sorted and "
                f"deduped -- discovery order must not reach the artifact"
            )
        return self


class ProposedDisposition(BaseModel):
    """What the MODEL returns.

    Carries no `source` and no `rule`: provenance is code's to stamp (DD1).
    A model able to set `source` could label a hallucinated verdict as a
    code-computed baseline, which is exactly the laundering DD7 forbids.
    """

    candidate_id: str
    action: DiscoverAction
    rationale: str
    merge_into: str | None = None
    partitions: tuple[SplitPartition, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()


class DiscoverProposal(BaseModel):
    """The proposer's output_type. Dispositions and nothing else (DD1)."""

    dispositions: list[ProposedDisposition] = Field(default_factory=list)


class CandidateDisposition(BaseModel):
    """A disposition after code has stamped its provenance."""

    model_config = {"frozen": True}
    candidate_id: str
    action: DiscoverAction
    source: DispositionSource
    rule: str
    rationale: str = ""
    merge_into: str | None = None
    partitions: tuple[SplitPartition, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def _merge_names_a_target(self) -> "CandidateDisposition":
        if (self.action is DiscoverAction.MERGE) != (self.merge_into is not None):
            raise ValueError(
                f"merge_into is set IFF action is merge -- got "
                f"action={self.action.value} merge_into={self.merge_into}"
            )
        return self

    @model_validator(mode="after")
    def _split_partitions_the_candidate(self) -> "CandidateDisposition":
        if self.action is DiscoverAction.SPLIT:
            if len(self.partitions) < 2:
                raise ValueError(
                    f"action=split needs at least two partitions, got "
                    f"{len(self.partitions)} -- a split into one is a confirm"
                )
        elif self.partitions:
            raise ValueError(f"action={self.action.value} must not carry partitions")
        return self

    @model_validator(mode="after")
    def _a_proposer_verdict_carries_its_reasoning(self) -> "CandidateDisposition":
        if self.source is DispositionSource.PROPOSER and not self.rationale.strip():
            raise ValueError(
                "source=proposer requires a rationale -- a baseline's rule IS "
                "its rationale, but an unexplained model verdict is "
                "unreviewable"
            )
        return self
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_map_dispositions.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/map.py tests/test_discover_map_dispositions.py
git commit -m "feat(discover): the proposer returns dispositions, code stamps provenance (E-48 DD1)"
```

---

### Task 3: The context contracts

What the proposer sees. Note what is **absent**: the `ReferenceGraph` itself. `DiscoverContext` travels through workflow history to reach the proposer, and pushing an entire tree's edge list through history is the FR-702 hazard the roadmap carries as open (spec DD4). The context carries derived metrics and a graph *summary* instead.

**Files:**
- Modify: `src/sdlc/assessment/discover/map.py` (append)
- Test: `tests/test_discover_map_context.py`

**Interfaces:**
- Consumes: `CandidateMember`, `Confidence`, `SecurityObservation`, `TestabilityFinding`, `CoverageRecord`, `SensitivityRecord` from `sdlc.assessment.scan.models`; `Measurement` from `sdlc.measurement`
- Produces: `GUARDRAIL_RULES: frozenset[str]`, `GraphSummary`, `CandidateContext`, `DiscoverContext`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_map_context.py
"""FR-913 (E-48): the deterministic packet the proposer judges."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.map import (
    GUARDRAIL_RULES,
    CandidateContext,
    DiscoverContext,
    GraphSummary,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import Measurement

MEASURED = Measurement.measured(1.0)
NC = Measurement.not_collected("upstream degraded")
GRAPH = GraphSummary(
    parsed=10, unparsed=2, edges=14, unresolved_relative_rate=Measurement.measured(0.0)
)


def _ctx(**kw):
    base = dict(
        candidate_id="C-01",
        name="payments",
        confidence=Confidence.HIGH,
        sources=("S3-payments",),
        source_rules=("s3_http_route",),
        members=(
            CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="api/pay.py"),
        ),
        member_paths=("api/pay.py",),
        cohesion=MEASURED,
        coupling=MEASURED,
        guardrail_only=False,
    )
    return CandidateContext(**(base | kw))


def test_the_context_never_carries_the_reference_graph():
    """DD4: DiscoverContext travels through workflow history to reach the
    proposer. An edge list in history is the open FR-702 hazard."""
    assert "graph" not in DiscoverContext.model_fields
    assert "edges" not in CandidateContext.model_fields


def test_guardrail_only_is_derived_from_the_source_rules():
    """DD6's input. Derived and asserted, so a deserialized payload cannot
    disagree with its own arithmetic -- AttributionReport.meets_floor's rule."""
    _ctx(source_rules=("s1_layer_name",), guardrail_only=True)
    _ctx(source_rules=("s1_layer_name", "s1_generic_name"), guardrail_only=True)
    _ctx(source_rules=("s1_layer_name", "s3_http_route"), guardrail_only=False)
    with pytest.raises(ValidationError, match="derived"):
        _ctx(source_rules=("s1_layer_name",), guardrail_only=False)
    with pytest.raises(ValidationError, match="derived"):
        _ctx(source_rules=("s3_http_route",), guardrail_only=True)


def test_a_candidate_with_no_source_rules_is_not_guardrail_only():
    """Vacuous truth is the wrong answer here: 'every rule is a layer rule'
    is true of no rules, and DE-SCOPEing a candidate we know nothing about
    would delete it on an absence of evidence."""
    _ctx(source_rules=(), guardrail_only=False)
    with pytest.raises(ValidationError, match="derived"):
        _ctx(source_rules=(), guardrail_only=True)


def test_guardrail_rules_are_exactly_s1s_two_non_domain_rules():
    assert GUARDRAIL_RULES == {"s1_layer_name", "s1_generic_name"}


def test_member_paths_are_sorted_and_deduped():
    _ctx(member_paths=("a.py", "b.py"))
    with pytest.raises(ValidationError, match="not sorted"):
        _ctx(member_paths=("b.py", "a.py"))


def test_an_uncollected_context_carries_no_candidates():
    """FR-915: a packet that could not be built has no rows."""
    DiscoverContext(collected=NC, graph=GRAPH)
    with pytest.raises(ValidationError, match="no candidates"):
        DiscoverContext(collected=NC, graph=GRAPH, candidates=(_ctx(),))


def test_a_collected_context_may_legitimately_have_no_candidates():
    """A tree with no capabilities is a measured zero, not a failure."""
    ctx = DiscoverContext(collected=Measurement.measured(0.0), graph=GRAPH)
    assert ctx.candidates == ()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_map_context.py -v`
Expected: FAIL — `ImportError: cannot import name 'GUARDRAIL_RULES'`

- [ ] **Step 3: Write the implementation**

Append to `src/sdlc/assessment/discover/map.py`, and extend the existing scan-models import line to include the new names:

```python
from ..scan.models import (
    CandidateMember,
    Confidence,
    CoverageRecord,
    EvidenceRef,
    SecurityObservation,
    SensitivityRecord,
    TestabilityFinding,
)
from ...measurement import CollectionState, Measurement
```

```python
# S1's two non-domain classifications. A candidate supported ONLY by these is
# named like a layer or a container ("services", "utils", "api"), which is
# clause D2's guardrail: delivery channels and deployment boundaries are not
# capabilities. S1 records WHICH rule fired rather than a boolean precisely so
# this distinction is available here (scan spec, SourceCandidate docstring).
GUARDRAIL_RULES: frozenset[str] = frozenset({"s1_layer_name", "s1_generic_name"})


class GraphSummary(BaseModel):
    """The reference graph's shape WITHOUT its edges (DD4).

    The proposer needs to know how much of the tree the extractor could read
    -- a coupling number computed over two parsed files means something
    different from one over two hundred. It does not need the edge list, and
    an edge list in workflow history is the open FR-702 hazard.
    """

    model_config = {"frozen": True}
    parsed: int
    unparsed: int
    edges: int
    unresolved_relative_rate: Measurement


class CandidateContext(BaseModel):
    """One scan candidate as the proposer sees it: everything code could
    compute about it, and no room to invent anything else."""

    model_config = {"frozen": True}
    candidate_id: str
    name: str
    confidence: Confidence
    sources: tuple[str, ...]  # SourceCandidate.local_id
    source_rules: tuple[str, ...]  # the rules that produced them
    members: tuple[CandidateMember, ...]
    member_paths: tuple[str, ...]
    cohesion: Measurement  # clause D1
    coupling: Measurement  # clause D1
    guardrail_only: bool  # DD6's input, DERIVED
    possible_duplicate_of: tuple[str, ...] = ()
    security: tuple[SecurityObservation, ...] = ()  # clause D6
    sensitivity: tuple[SensitivityRecord, ...] = ()  # clause D6
    testability: tuple[TestabilityFinding, ...] = ()  # clause D6a
    coverage: tuple[CoverageRecord, ...] = ()  # clause D6a

    @model_validator(mode="after")
    def _guardrail_only_is_derived(self) -> "CandidateContext":
        """Derived, never assigned, so a deserialized payload cannot disagree
        with its own arithmetic (AttributionReport.meets_floor's rule).

        `and self.source_rules` is load-bearing: all() of an empty sequence is
        True, and a candidate whose rules we do not know must not be DE-SCOPEd
        on an absence of evidence.
        """
        expected = bool(self.source_rules) and all(r in GUARDRAIL_RULES for r in self.source_rules)
        if self.guardrail_only != expected:
            raise ValueError(
                f"guardrail_only={self.guardrail_only} does not match the "
                f"derived {expected} for source_rules={self.source_rules} -- "
                f"it is derived, never assigned"
            )
        return self

    @model_validator(mode="after")
    def _member_paths_are_sorted(self) -> "CandidateContext":
        if list(self.member_paths) != sorted(set(self.member_paths)):
            raise ValueError(
                f"member_paths {self.member_paths} are not sorted and "
                f"deduped -- discovery order must not reach the artifact"
            )
        return self


class DiscoverContext(BaseModel):
    """The packet handed to the proposer, and the thing DD10's memo digests."""

    candidates: tuple[CandidateContext, ...] = ()
    entry_point_paths: tuple[str, ...] = ()
    graph: GraphSummary
    file_count: int = 0
    skipped: tuple[str, ...] = ()
    collected: Measurement

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> "DiscoverContext":
        if self.collected.state is not CollectionState.MEASURED and self.candidates:
            raise ValueError(
                f"collected={self.collected.state.value} carries no payload, "
                f"but {len(self.candidates)} candidate(s) are present -- a "
                f"context that could not be built has no candidates (FR-915)"
            )
        return self
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_map_context.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/map.py tests/test_discover_map_context.py
git commit -m "feat(discover): the proposer's packet, without the edge list (E-48 DD4)"
```

---

### Task 4: The phase artifact

`CapabilityMap` as plans 1 and 2 need it. Plan 3 adds `domain_model` and `blueprint` when it builds their producers — a contract defined before its producer exists is how E-47c shipped a fabricated field.

**Files:**
- Modify: `src/sdlc/assessment/discover/map.py` (append)
- Test: `tests/test_discover_map_artifact.py`

**Interfaces:**
- Consumes: `AttributionReport`, `DecompositionReport`, `OwnershipReport` from `sdlc.assessment.discover.models`; `Advisory` from `sdlc.capability.models`
- Produces: `Capability`, `CapabilityMap`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_map_artifact.py
"""FR-913 (E-48): the phase artifact."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.map import (
    Capability,
    CapabilityMap,
    CandidateDisposition,
    DiscoverAction,
    DispositionSource,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import Measurement

MEASURED = Measurement.measured(1.0)
NC = Measurement.not_collected("discover did not run")


def _cap(bc_id="BC-001", **kw):
    base = dict(
        bc_id=bc_id,
        local_key="C-01",
        name="payments",
        confidence=Confidence.HIGH,
        members=(
            CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="api/pay.py"),
        ),
        member_paths=("api/pay.py",),
        cohesion=MEASURED,
        coupling=MEASURED,
        disposition=CandidateDisposition(
            candidate_id="C-01",
            action=DiscoverAction.CONFIRM,
            source=DispositionSource.BASELINE,
            rule="baseline_confirm",
        ),
    )
    return Capability(**(base | kw))


def test_capability_counts_are_derived_from_capabilities():
    m = CapabilityMap(
        capabilities=(_cap("BC-001"), _cap("BC-002")),
        collected=Measurement.measured(2.0),
        by_action={DiscoverAction.CONFIRM: 2},
    )
    assert m.by_action[DiscoverAction.CONFIRM] == 2
    with pytest.raises(ValidationError, match="derived"):
        CapabilityMap(
            capabilities=(_cap(),), collected=MEASURED, by_action={DiscoverAction.CONFIRM: 7}
        )


def test_by_action_must_carry_every_action_that_occurs():
    """An absent key and a zero count are different claims, and only one of
    them is true."""
    with pytest.raises(ValidationError, match="absent from by_action"):
        CapabilityMap(capabilities=(_cap(),), collected=MEASURED, by_action={})


def test_an_uncollected_map_carries_no_capabilities():
    """FR-915: a discover that did not happen has no rows."""
    CapabilityMap(collected=NC)
    with pytest.raises(ValidationError, match="no capabilities"):
        CapabilityMap(collected=NC, capabilities=(_cap(),), by_action={DiscoverAction.CONFIRM: 1})


def test_a_de_scoped_candidate_never_becomes_a_capability():
    """DE_SCOPE and FLAG are verdicts ABOUT a candidate; only a surviving
    boundary gets a bc_id. A de-scoped row holding one would mean the map
    both rejected and identified the same thing."""
    with pytest.raises(ValidationError, match="de_scope|flag"):
        _cap(
            disposition=CandidateDisposition(
                candidate_id="C-01",
                action=DiscoverAction.DE_SCOPE,
                source=DispositionSource.BASELINE,
                rule="baseline_guardrail",
            )
        )


def test_dropped_dispositions_are_recorded_not_discarded():
    """DD8: a dropped disposition is evidence about the candidate. The map
    keeps the count so the citation guard's input is auditable."""
    m = CapabilityMap(
        collected=MEASURED,
        capabilities=(_cap(),),
        by_action={DiscoverAction.CONFIRM: 1},
        dropped_dispositions=2,
        total_references=20,
    )
    assert m.dropped_dispositions == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_map_artifact.py -v`
Expected: FAIL — `ImportError: cannot import name 'Capability'`

- [ ] **Step 3: Write the implementation**

Append to `map.py`, adding the import line:

```python
from ...capability.models import Advisory
from .models import AttributionReport, DecompositionReport, OwnershipReport
```

```python
# A verdict ABOUT a candidate rather than a surviving boundary. Only the
# actions absent from this set produce a Capability with a bc_id.
REJECTING_ACTIONS: frozenset[DiscoverAction] = frozenset(
    {DiscoverAction.DE_SCOPE, DiscoverAction.FLAG}
)


class Capability(BaseModel):
    """One L1 capability: a candidate that survived disposition and was given
    a durable id by E-47a's resolve()."""

    model_config = {"frozen": True}
    bc_id: str
    local_key: str  # the candidate_id it came from
    name: str
    confidence: Confidence
    members: tuple[CandidateMember, ...]
    member_paths: tuple[str, ...]
    cohesion: Measurement
    coupling: Measurement
    disposition: CandidateDisposition

    @model_validator(mode="after")
    def _a_rejected_candidate_is_not_a_capability(self) -> "Capability":
        if self.disposition.action in REJECTING_ACTIONS:
            raise ValueError(
                f"disposition action={self.disposition.action.value} rejects "
                f"the candidate, so it must not hold bc_id={self.bc_id} -- a "
                f"map that both rejected and identified the same thing is "
                f"making two claims"
            )
        return self


class CapabilityMap(BaseModel):
    """The DISCOVER phase artifact (FR-913).

    Plan 3 adds `domain_model` (clause D7) and `blueprint` (clause D8) when it
    builds their producers. Declaring them now would be a field with no
    producer, which is what E-47c's review found and fixed.
    """

    capabilities: tuple[Capability, ...] = ()
    by_action: dict[DiscoverAction, int] = Field(default_factory=dict)
    dispositions: tuple[CandidateDisposition, ...] = ()
    attribution: AttributionReport | None = None
    decomposition: DecompositionReport | None = None
    ownership: OwnershipReport | None = None
    advisories: tuple[Advisory, ...] = ()
    dropped_dispositions: int = 0
    total_references: int = 0
    collected: Measurement

    @model_validator(mode="after")
    def _counts_are_derived(self) -> "CapabilityMap":
        for action, claimed in self.by_action.items():
            actual = sum(1 for c in self.capabilities if c.disposition.action is action)
            if claimed != actual:
                raise ValueError(
                    f"by_action[{action.value}]={claimed} but {actual} "
                    f"capabilit(ies) carry it -- counts are derived from "
                    f"capabilities, never assigned"
                )
        unlisted = sorted(
            {c.disposition.action.value for c in self.capabilities}
            - {a.value for a in self.by_action}
        )
        if unlisted:
            raise ValueError(
                f"capabilities carry actions absent from by_action "
                f"({unlisted}) -- an absent key and a zero count are "
                f"different claims and only one of them is true"
            )
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> "CapabilityMap":
        if self.collected.state is not CollectionState.MEASURED and self.capabilities:
            raise ValueError(
                f"collected={self.collected.state.value} carries no payload, "
                f"but {len(self.capabilities)} capabilit(ies) are present -- "
                f"a discover that did not happen has no capabilities "
                f"(FR-915)"
            )
        return self
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_map_artifact.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/map.py tests/test_discover_map_artifact.py
git commit -m "feat(discover): CapabilityMap, the DISCOVER phase artifact (FR-913)"
```

---

### Task 5: Cohesion and coupling

Clause D1 as arithmetic. Both fail closed when the extractor could not read the candidate's files — a coupling of `measured(0.0)` claims *this capability touches nothing else*, which is a very different statement from *we could not parse its files*.

**Files:**
- Create: `src/sdlc/assessment/discover/context.py`
- Test: `tests/test_discover_cohesion_coupling.py`

**Interfaces:**
- Consumes: `ReferenceGraph` from `sdlc.assessment.discover.models`
- Produces: `cohesion(member_paths, edges, parsed) -> Measurement`, `coupling(candidate_id, member_paths, edges, owner_of, parsed) -> Measurement`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_cohesion_coupling.py
"""FR-913 (E-48 DD1): clause D1 as arithmetic, not opinion."""

from __future__ import annotations

import random

from sdlc.assessment.discover.context import cohesion, coupling
from sdlc.measurement import CollectionState

PARSED = {"a.py", "b.py", "c.py", "d.py"}


def test_cohesion_is_the_share_of_touching_edges_that_stay_inside():
    edges = (("a.py", "b.py"), ("a.py", "c.py"))
    m = cohesion({"a.py", "b.py"}, edges, PARSED)
    assert m.state is CollectionState.MEASURED
    assert m.value == 0.5


def test_a_fully_internal_candidate_scores_one():
    edges = (("a.py", "b.py"),)
    assert cohesion({"a.py", "b.py"}, edges, PARSED).value == 1.0


def test_cohesion_is_not_collected_when_no_edge_touches_the_candidate():
    """measured(0.0) would claim the files are mutually unreferenced. They
    may simply be leaves."""
    m = cohesion({"a.py"}, (("b.py", "c.py"),), PARSED)
    assert m.state is CollectionState.NOT_COLLECTED
    assert "no reference-graph edge" in m.reason


def test_cohesion_is_not_collected_when_the_files_were_never_parsed():
    """FR-915: an unparsed file yields no edges, and an absence of edges from
    an absence of parsing is not evidence of anything."""
    m = cohesion({"x.rb"}, (("a.py", "b.py"),), PARSED)
    assert m.state is CollectionState.NOT_COLLECTED
    assert "not parsed" in m.reason


def test_coupling_counts_distinct_partner_capabilities():
    edges = (("a.py", "c.py"), ("a.py", "d.py"), ("b.py", "c.py"))
    owner_of = {"c.py": {"C-02"}, "d.py": {"C-03"}}
    m = coupling("C-01", {"a.py", "b.py"}, edges, owner_of, PARSED)
    assert m.value == 2.0


def test_coupling_never_counts_the_candidate_itself():
    edges = (("a.py", "b.py"),)
    owner_of = {"a.py": {"C-01"}, "b.py": {"C-01"}}
    assert coupling("C-01", {"a.py", "b.py"}, edges, owner_of, PARSED).value == 0.0


def test_zero_coupling_is_a_real_measurement_when_the_files_parsed():
    """The counterpart to the guard above: a parsed, edge-having tree in
    which this capability reaches nobody is a measured zero."""
    m = coupling("C-01", {"a.py"}, (("b.py", "c.py"),), {}, PARSED)
    assert m.state is CollectionState.MEASURED
    assert m.value == 0.0


def test_coupling_is_not_collected_when_the_files_were_never_parsed():
    m = coupling("C-01", {"x.rb"}, (("a.py", "b.py"),), {}, PARSED)
    assert m.state is CollectionState.NOT_COLLECTED


def test_both_are_order_independent():
    """NFR-10."""
    edges = [("a.py", "b.py"), ("a.py", "c.py"), ("b.py", "d.py")]
    owner_of = {"c.py": {"C-02"}, "d.py": {"C-03"}}
    first = (
        cohesion({"a.py", "b.py"}, tuple(edges), PARSED),
        coupling("C-01", {"a.py", "b.py"}, tuple(edges), owner_of, PARSED),
    )
    for _ in range(5):
        shuffled = edges[:]
        random.shuffle(shuffled)
        assert (
            cohesion({"a.py", "b.py"}, tuple(shuffled), PARSED),
            coupling("C-01", {"a.py", "b.py"}, tuple(shuffled), owner_of, PARSED),
        ) == first
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_cohesion_coupling.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.discover.context'`

- [ ] **Step 3: Write the implementation**

```python
# src/sdlc/assessment/discover/context.py
"""FR-913 (E-48 DD1): the deterministic packet the proposer judges.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio.

Clause D1 (cohesion, coupling, boundary clarity) is computed here rather than
asked of a model, which is ADR-22's whole point: the model disposes over
numbers code produced, and cannot invent a metric.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from ...measurement import Measurement

Edges = Sequence[tuple[str, str]]


def _unparsed_reason(member_paths: Collection[str]) -> str:
    return (
        f"none of this candidate's {len(member_paths)} file(s) were "
        f"parsed by the reference extractor, so an absence of edges is "
        f"not evidence"
    )


def cohesion(member_paths: Collection[str], edges: Edges, parsed: Collection[str]) -> Measurement:
    """The share of edges touching this candidate that stay inside it.

    Fails closed twice, for two different absences. Unparsed files yield no
    edges, so a score computed over them would report structure we never
    read. And a parsed candidate that no edge touches may be a set of leaves
    rather than an incoherent boundary -- measured(0.0) would assert the
    second (FR-915).
    """
    if not any(p in parsed for p in member_paths):
        return Measurement.not_collected(_unparsed_reason(member_paths))
    inside = set(member_paths)
    touching = [(a, b) for a, b in edges if a in inside or b in inside]
    if not touching:
        return Measurement.not_collected(
            "no reference-graph edge touches this candidate's files, so its "
            "internal coherence was not measured"
        )
    internal = sum(1 for a, b in touching if a in inside and b in inside)
    return Measurement.measured(internal / len(touching))


def coupling(
    candidate_id: str,
    member_paths: Collection[str],
    edges: Edges,
    owner_of: Mapping[str, Collection[str]],
    parsed: Collection[str],
) -> Measurement:
    """How many OTHER candidates this one reaches, or is reached by.

    A count, not a ratio: "payments touches three other capabilities" is the
    sentence clause D1 needs, and normalising it would hide the scale.

    Zero is a real answer once the files parsed -- unlike cohesion, an
    isolated capability is a meaningful finding rather than an absence of
    evidence. The unparsed guard still applies.
    """
    if not any(p in parsed for p in member_paths):
        return Measurement.not_collected(_unparsed_reason(member_paths))
    inside = set(member_paths)
    partners: set[str] = set()
    for a, b in edges:
        if a in inside:
            partners.update(owner_of.get(b, ()))
        if b in inside:
            partners.update(owner_of.get(a, ()))
    partners.discard(candidate_id)
    return Measurement.measured(float(len(partners)))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_cohesion_coupling.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/context.py tests/test_discover_cohesion_coupling.py
git commit -m "feat(discover): cohesion and coupling as arithmetic, failing closed on unparsed files (E-48 DD1)"
```

---

### Task 6: The packet builder

Assembles `DiscoverContext` from a `ScanResult` plus the tree's blobs. Joins security, sensitivity, testability and coverage onto candidates by path.

**Files:**
- Modify: `src/sdlc/assessment/discover/context.py` (append)
- Test: `tests/test_discover_context.py`

**Interfaces:**
- Consumes: `ScanResult` from `sdlc.assessment.scan.models`; `refgraph.build`; task 3's contracts
- Produces: `entry_point_paths(scan) -> tuple[str, ...]`, `build_context(scan, inventory, skipped) -> DiscoverContext`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discover_context.py
"""FR-913 (E-48): assembling the proposer's packet from a ScanResult."""

from __future__ import annotations

import random

from sdlc.assessment.discover.context import build_context, entry_point_paths
from sdlc.assessment.scan.models import (
    CATEGORIES,
    SCAN_ORDER,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanCandidate,
    ScanResult,
    ScanSignalResult,
    SecurityObservation,
    SignalSource,
    SourceCandidate,
    family_of,
)
from sdlc.measurement import CollectionState, Measurement

PAY = ScanCandidate(
    candidate_id="C-01",
    name="payments",
    sources=["S1-payments", "S3-payments"],
    confidence=Confidence.MEDIUM,
    members=[
        CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="pay/api.py", line=10),
        CandidateMember(kind=MemberKind.FILE_PATH, value="pay/core.py", path="pay/core.py"),
    ],
)
UTIL = ScanCandidate(
    candidate_id="C-02",
    name="services",
    sources=["S1-services"],
    confidence=Confidence.LOW,
    members=[
        CandidateMember(kind=MemberKind.PACKAGE_PATH, value="services", path="services/__init__.py")
    ],
)

SOURCES = [
    SourceCandidate(
        signal="S1",
        local_id="S1-payments",
        name="payments",
        rule="s1_domain_term",
        detail="",
        confidence_contribution=Confidence.HIGH,
        members=[CandidateMember(kind=MemberKind.PACKAGE_PATH, value="pay")],
    ),
    SourceCandidate(
        signal="S3",
        local_id="S3-payments",
        name="payments",
        rule="s3_http_route",
        detail="",
        confidence_contribution=Confidence.HIGH,
        members=[
            CandidateMember(
                kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="pay/api.py", line=10
            )
        ],
    ),
    SourceCandidate(
        signal="S1",
        local_id="S1-services",
        name="services",
        rule="s1_layer_name",
        detail="",
        confidence_contribution=Confidence.LOW,
        members=[CandidateMember(kind=MemberKind.PACKAGE_PATH, value="services")],
    ),
]

INVENTORY = {
    "pay/api.py": "from pay.core import charge\n",
    "pay/core.py": "def charge(): pass\n",
    "services/__init__.py": "from pay.core import charge\n",
}


def _signals() -> list[ScanSignalResult]:
    """All thirteen rows, MEASURED.

    ScanResult is stricter than it looks: `_signals_are_the_whole_set`
    requires every signal in SCAN_ORDER, and `_unmeasured_carries_no_payload`
    forbids a payload whose owning signal did not collect. `signals=[]` does
    not construct.
    """
    val = Measurement.measured(0.0)
    return [
        ScanSignalResult(
            signal=s,
            family=family_of(s),
            version=1,
            source=SignalSource.COMPUTED,
            collected=val,
            categories={k: val for k in CATEGORIES[s]},
        )
        for s in SCAN_ORDER
    ]


def _scan(**kw) -> ScanResult:
    base = dict(signals=_signals(), sources=SOURCES, candidates=[PAY, UTIL])
    return ScanResult(**(base | kw))


def test_the_packet_carries_one_context_per_candidate():
    ctx = build_context(_scan(), INVENTORY, [])
    assert [c.candidate_id for c in ctx.candidates] == ["C-01", "C-02"]


def test_source_rules_come_from_the_source_candidates():
    ctx = build_context(_scan(), INVENTORY, [])
    pay = ctx.candidates[0]
    assert set(pay.source_rules) == {"s1_domain_term", "s3_http_route"}


def test_a_layer_named_candidate_is_flagged_guardrail_only():
    """DD6's input: 'services' is supported only by s1_layer_name."""
    ctx = build_context(_scan(), INVENTORY, [])
    by_id = {c.candidate_id: c for c in ctx.candidates}
    assert by_id["C-02"].guardrail_only is True
    assert by_id["C-01"].guardrail_only is False


def test_security_observations_join_on_member_paths():
    obs = SecurityObservation(
        signal="SS1",
        category="tls_enforcement",
        rule="plaintext_http",
        detail="",
        severity_hint="medium",
        path="pay/api.py",
        confidence=Confidence.MEDIUM,
    )
    ctx = build_context(_scan(security=[obs]), INVENTORY, [])
    by_id = {c.candidate_id: c for c in ctx.candidates}
    assert len(by_id["C-01"].security) == 1
    assert by_id["C-02"].security == ()


def test_entry_point_paths_come_from_s3_and_s4_members():
    assert entry_point_paths(_scan()) == ("pay/api.py",)


def test_no_candidates_is_a_measured_zero_not_a_failure():
    ctx = build_context(_scan(candidates=[]), INVENTORY, [])
    assert ctx.collected.state is CollectionState.MEASURED
    assert ctx.collected.value == 0.0
    assert ctx.candidates == ()


def test_skipped_blobs_are_carried_not_dropped():
    """The E-46 review's rule: a gap reported as a zero is the defect."""
    ctx = build_context(_scan(), INVENTORY, ["big/generated.py"])
    assert ctx.skipped == ("big/generated.py",)


def test_the_packet_is_order_independent():
    """NFR-10: byte-identical regardless of input ordering."""
    first = build_context(_scan(), INVENTORY, []).model_dump_json()
    for _ in range(5):
        cands = [PAY, UTIL]
        srcs = SOURCES[:]
        random.shuffle(cands)
        random.shuffle(srcs)
        items = list(INVENTORY.items())
        random.shuffle(items)
        again = build_context(_scan(candidates=cands, sources=srcs), dict(items), [])
        assert again.model_dump_json() == first
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_discover_context.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_context'`

- [ ] **Step 3: Write the implementation**

Extend `context.py`'s import block to exactly this (one edit, not two — the
task-5 block imported only what task 5 needed):

```python
from collections.abc import Collection, Mapping, Sequence

from ...measurement import Measurement
from ..scan.models import CandidateMember, ScanResult
from . import refgraph
from .map import (
    GUARDRAIL_RULES,
    CandidateContext,
    DiscoverContext,
    GraphSummary,
)
```

Then append:

```python
# S3 and S4 are the entry-point signals; attribute() takes the paths that host
# one so a referenced-by-an-entry-point file is ATTACHED rather than orphaned.
_ENTRY_SIGNALS = ("S3", "S4")


def entry_point_paths(scan: ScanResult) -> tuple[str, ...]:
    """Paths hosting an S3/S4 entry point, for E-47b's attribute()."""
    return tuple(
        sorted(
            {
                m.path
                for s in scan.sources
                if s.signal.value in _ENTRY_SIGNALS
                for m in s.members
                if m.path
            }
        )
    )


def build_context(
    scan: ScanResult, inventory: Mapping[str, str], skipped: Sequence[str]
) -> DiscoverContext:
    """Everything code can compute about the candidate set (DD1).

    The reference graph is built here and DISCARDED: only its summary and the
    metrics derived from it reach the packet, because the packet travels
    through workflow history to the proposer and an edge list there is the
    open FR-702 hazard (DD4).
    """
    graph = refgraph.build(inventory)
    parsed = set(graph.parsed)
    rule_of = {s.local_id: s.rule for s in scan.sources}

    owner_of: dict[str, set[str]] = {}
    for cand in scan.candidates:
        for member in cand.members:
            if member.path:
                owner_of.setdefault(member.path, set()).add(cand.candidate_id)

    contexts: list[CandidateContext] = []
    for cand in sorted(scan.candidates, key=lambda c: c.candidate_id):
        paths = sorted({m.path for m in cand.members if m.path})
        rules = tuple(sorted({rule_of[s] for s in cand.sources if s in rule_of}))
        member_set = set(paths)
        contexts.append(
            CandidateContext(
                candidate_id=cand.candidate_id,
                name=cand.name,
                confidence=cand.confidence,
                sources=tuple(sorted(cand.sources)),
                source_rules=rules,
                members=tuple(sorted(cand.members, key=CandidateMember.sort_key)),
                member_paths=tuple(paths),
                cohesion=cohesion(member_set, graph.edges, parsed),
                coupling=coupling(cand.candidate_id, member_set, graph.edges, owner_of, parsed),
                guardrail_only=bool(rules) and all(r in GUARDRAIL_RULES for r in rules),
                possible_duplicate_of=tuple(sorted(cand.possible_duplicate_of)),
                security=tuple(o for o in scan.security if o.path in member_set),
                sensitivity=tuple(
                    r
                    for r in scan.data_sensitivity
                    if any(e.path in member_set for e in r.evidence)
                ),
                testability=tuple(f for f in scan.testability if f.path in member_set),
                coverage=tuple(c for c in scan.coverage if c.path in member_set),
            )
        )

    return DiscoverContext(
        candidates=tuple(contexts),
        entry_point_paths=entry_point_paths(scan),
        graph=GraphSummary(
            parsed=len(graph.parsed),
            unparsed=len(graph.unparsed),
            edges=len(graph.edges),
            unresolved_relative_rate=graph.unresolved_relative_rate,
        ),
        file_count=len(inventory),
        skipped=tuple(sorted(skipped)),
        collected=Measurement.measured(float(len(contexts))),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_context.py tests/test_discover_cohesion_coupling.py -v`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/context.py tests/test_discover_context.py
git commit -m "feat(discover): build the proposer's packet from a ScanResult (E-48 DD1)"
```

---

### Task 7: `Assessment.discover` and its paired validator

The field, plus the invariant that a phase row and its payload cannot contradict each other — `_scan_agrees_with_its_phase`, applied to DISCOVER.

**Files:**
- Modify: `src/sdlc/assessment/models.py:104` (add field), `:140-161` (add validator beside `_scan_agrees_with_its_phase`)
- Test: `tests/test_assessment_models.py` (append)

**Interfaces:**
- Consumes: `CapabilityMap` from `sdlc.assessment.discover.map`
- Produces: `Assessment.discover: CapabilityMap | None`

- [ ] **Step 1: Repair the one existing test the new validator will break**

`tests/test_assessment_models.py:183` `test_a_measured_scan_phase_with_a_payload_constructs` builds `_scan_dag(scan_measured=True)`, which marks **every** phase measured — including DISCOVER — and passes no `discover`. Once the validator lands, it raises. The test is about the *scan* pairing, so hold DISCOVER not-measured rather than giving it a map.

Replace that test's body with:

```python
def test_a_measured_scan_phase_with_a_payload_constructs():
    # DISCOVER is held not-measured: this test is about the SCAN pairing, and
    # a measured DISCOVER would now also require a CapabilityMap (E-48).
    phases = [
        p
        if p.phase is not PhaseId.DISCOVER
        else PhaseResult(
            phase=PhaseId.DISCOVER, collected=Measurement.not_collected("discover not run")
        )
        for p in _scan_dag(scan_measured=True)
    ]
    a = Assessment(
        repo_dir="/r",
        triage=_triage(),
        admitted=True,
        admission_reason="verdict ready",
        phases=phases,
        terminal_status=terminal_status(True, phases),
        scan=_scan_result(),
    )
    assert a.scan is not None
    assert len(a.scan.signals) == 13
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_assessment_models.py`, reusing the file's existing `_scan_dag`, `_triage` and `_scan_result` helpers:

```python
# --- E-48: the discover payload and its phase-agreement validator ---------
from sdlc.assessment.discover.map import CapabilityMap


def _discover_dag(discover_measured: bool) -> list[PhaseResult]:
    """The whole DAG with DISCOVER either measured or not, every other phase
    measured. _scan_dag's shape, for the other pairing."""
    out = []
    for phase in PHASE_ORDER:
        if phase is PhaseId.DISCOVER and not discover_measured:
            out.append(
                PhaseResult(phase=phase, collected=Measurement.not_collected("discover not run"))
            )
        else:
            out.append(PhaseResult(phase=phase, collected=Measurement.measured(1.0)))
    return out


def test_a_measured_discover_phase_requires_a_capability_map():
    """_scan_agrees_with_its_phase, applied to DISCOVER: a measured phase
    produced an artifact by definition."""
    phases = _discover_dag(discover_measured=True)
    with pytest.raises(ValidationError, match="no CapabilityMap"):
        Assessment(
            repo_dir="/r",
            triage=_triage(),
            admitted=True,
            admission_reason="verdict ready",
            phases=phases,
            terminal_status=terminal_status(True, phases),
            scan=_scan_result(),
            discover=None,
        )


def test_a_discover_payload_requires_a_measured_discover_phase():
    """An assessment cannot claim it did not discover while shipping a map."""
    phases = _discover_dag(discover_measured=False)
    with pytest.raises(ValidationError, match="did not discover"):
        Assessment(
            repo_dir="/r",
            triage=_triage(),
            admitted=True,
            admission_reason="verdict ready",
            phases=phases,
            terminal_status=terminal_status(True, phases),
            scan=_scan_result(),
            discover=CapabilityMap(collected=Measurement.measured(0.0)),
        )


def test_a_measured_discover_phase_with_a_payload_constructs():
    phases = _discover_dag(discover_measured=True)
    a = Assessment(
        repo_dir="/r",
        triage=_triage(),
        admitted=True,
        admission_reason="verdict ready",
        phases=phases,
        terminal_status=terminal_status(True, phases),
        scan=_scan_result(),
        discover=CapabilityMap(collected=Measurement.measured(0.0)),
    )
    assert a.discover is not None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_assessment_models.py -v -k discover`
Expected: FAIL — `ValidationError: Object has no attribute 'discover'` (Pydantic rejects the unknown keyword)

- [ ] **Step 4: Write the implementation**

In `src/sdlc/assessment/models.py`, add the import:

```python
from .discover.map import CapabilityMap
```

Add the field beside `scan`:

```python
    # E-48's typed field. As with `scan`, this is its OWN field rather than a
    # generic payload bag: an untyped bag would be a schema-less hole in the
    # one artifact handed to a customer (FR-921).
    discover: CapabilityMap | None = None
```

Add the validator beside `_scan_agrees_with_its_phase`:

```python
@model_validator(mode="after")
def _discover_agrees_with_its_phase(self) -> Assessment:
    """_scan_agrees_with_its_phase, for DISCOVER. Kept as a second
    explicit validator rather than a loop over (phase, field) pairs: the
    error messages are what a reader debugs against, and a generic one
    would name neither the phase nor the artifact.
    """
    row = next((p for p in self.phases if p.phase is PhaseId.DISCOVER), None)
    if row is None:  # unreachable: the DAG validator
        return self  # already required every phase
    measured = row.collected.state is CollectionState.MEASURED
    if measured and self.discover is None:
        raise ValueError(
            "discover phase is measured but no CapabilityMap is present "
            "-- a measured phase produced an artifact by definition"
        )
    if not measured and self.discover is not None:
        raise ValueError(
            f"discover phase is {row.collected.state.value} but a "
            f"CapabilityMap is present -- an assessment cannot claim it "
            f"did not discover while shipping a capability map"
        )
    return self
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_assessment_models.py tests/test_assessment_workflow.py tests/test_assessment_scan_phase.py -v`
Expected: all pass — the workflow tests must stay green, since `assemble()` does not yet pass `discover` and `None` is correct for an `unbuilt` DISCOVER row.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/assessment/models.py tests/test_assessment_models.py
git commit -m "feat(assessment): Assessment.discover, paired with its phase row (E-48)"
```

---

### Task 8: The `discover_context` activity

I/O side: read the tree at the pinned commit and hand `build_context` its inventory. Mirrors `scan_packages`' shape, including the degrade-not-raise rule.

**Files:**
- Modify: `src/sdlc/assessment/activities.py` (append; imports at top)
- Modify: `src/sdlc/worker.py:134` (register)
- Test: `tests/test_discover_context_activity.py`

**Interfaces:**
- Consumes: `tracked_paths`, `_source_blobs`, `SOURCE_EXTENSIONS`, `build_context`
- Produces: `DiscoverContextInput(repo_dir, commit_sha, tree_hash, scan)`, `async discover_context(inp) -> DiscoverContext`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_context_activity.py
"""FR-913 (E-48): the activity that reads the tree for discover."""

from __future__ import annotations

import subprocess

import pytest

from sdlc.assessment.activities import DiscoverContextInput, discover_context
from sdlc.assessment.scan.models import (
    CATEGORIES,
    SCAN_ORDER,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanCandidate,
    ScanResult,
    ScanSignalResult,
    SignalSource,
    SourceCandidate,
    family_of,
)
from sdlc.measurement import CollectionState, Measurement


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "pay").mkdir()
    (tmp_path / "pay" / "api.py").write_text("from pay.core import charge\n")
    (tmp_path / "pay" / "core.py").write_text("def charge(): pass\n")
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "t@t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", "init"], tmp_path)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    return str(tmp_path), sha


def _signals() -> list[ScanSignalResult]:
    """All thirteen rows, MEASURED -- ScanResult requires the whole set in
    order, and a payload may only be carried by a signal that collected."""
    val = Measurement.measured(0.0)
    return [
        ScanSignalResult(
            signal=s,
            family=family_of(s),
            version=1,
            source=SignalSource.COMPUTED,
            collected=val,
            categories={k: val for k in CATEGORIES[s]},
        )
        for s in SCAN_ORDER
    ]


SCAN = ScanResult(
    signals=_signals(),
    sources=[
        SourceCandidate(
            signal="S3",
            local_id="S3-payments",
            name="payments",
            rule="s3_http_route",
            detail="",
            confidence_contribution=Confidence.HIGH,
            members=[
                CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="pay/api.py")
            ],
        )
    ],
    candidates=[
        ScanCandidate(
            candidate_id="C-01",
            name="payments",
            sources=["S3-payments"],
            confidence=Confidence.LOW,
            members=[
                CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="pay/api.py"),
                CandidateMember(kind=MemberKind.FILE_PATH, value="pay/core.py", path="pay/core.py"),
            ],
        )
    ],
)


@pytest.mark.asyncio
async def test_the_activity_reads_the_tree_and_builds_the_packet(repo):
    repo_dir, sha = repo
    ctx = await discover_context(
        DiscoverContextInput(repo_dir=repo_dir, commit_sha=sha, tree_hash="t", scan=SCAN)
    )
    assert ctx.collected.state is CollectionState.MEASURED
    assert len(ctx.candidates) == 1
    assert ctx.candidates[0].cohesion.value == 1.0
    assert ctx.file_count == 2


@pytest.mark.asyncio
async def test_an_unreadable_tree_degrades_rather_than_raising(repo):
    """scan_packages' rule: one activity that cannot read the tree must
    report not_collected, not take the phase down with a traceback."""
    repo_dir, _ = repo
    ctx = await discover_context(
        DiscoverContextInput(repo_dir=repo_dir, commit_sha="0" * 40, tree_hash="t", scan=SCAN)
    )
    assert ctx.collected.state is CollectionState.NOT_COLLECTED
    assert ctx.candidates == ()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_discover_context_activity.py -v`
Expected: FAIL — `ImportError: cannot import name 'DiscoverContextInput'`

- [ ] **Step 3: Write the implementation**

Append to `src/sdlc/assessment/activities.py`, adding to its imports:

```python
from .discover.context import build_context
from .discover.map import DiscoverContext, GraphSummary
```

```python
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
            parsed=0,
            unparsed=0,
            edges=0,
            unresolved_relative_rate=Measurement.not_collected(reason),
        ),
    )


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
        blobs, skipped = _source_blobs(inp.repo_dir, inp.commit_sha, paths, SOURCE_EXTENSIONS)
        return build_context(inp.scan, blobs, skipped)
    except Exception as exc:  # noqa: BLE001
        _log.warning("discover_context failed: %s", exc)
        return _no_context(f"could not read the tree: {type(exc).__name__}: {exc}"[:300])
```

In `src/sdlc/worker.py`, add `discover_context` to the assessment import block (line 37) and to the `activities=[...]` list beside `assessment_resolve_tree` (line 134).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_discover_context_activity.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest tests/ -x -q`
Expected: all pass. Nothing in this plan changes a live path — `_discover` still returns `unbuilt(PhaseId.DISCOVER)`, and `Assessment.discover` defaults to `None`.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/assessment/activities.py src/sdlc/worker.py tests/test_discover_context_activity.py
git commit -m "feat(discover): discover_context activity, degrading on an unreadable tree (E-48)"
```

---

## Plan 1 exit criteria

- `uv run pytest tests/ -q` green.
- `_discover` still returns `unbuilt(PhaseId.DISCOVER)`; the DISCOVER phase row still names E-48; `terminal_status` unchanged.
- No roadmap edits. The ticks land with plan 3, when the item is complete — plan 2 makes DISCOVER *measured*, but E-48's clauses D1–D8 are not satisfied until the judgment layer ships.

## What plan 2 picks up

`apply.py` (DD6's baseline disposition and the SPLIT/MERGE application), fingerprint construction via `group_by_tier`, the `discover_lock` activity calling E-47a's `resolve()`, `discover_finalize` calling `attribute()`/`decompose()`/`assign()`, DD10's phase memo, `_discover` wired, and the temporal e2e E-47b deferred to this item.
