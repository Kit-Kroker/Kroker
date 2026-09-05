# E-47a Capability Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every discovered capability a `BC-NNN` identifier that survives refactoring, by assigning it once and re-attaching it on later scans through similarity matching.

**Architecture:** A pure matcher (fingerprints in, attachments out — no I/O, no `temporalio`) sits beside `triage/signals/` and `gate.py`. Persistence is an ABC with one implementation backed by the E-78 board's SQLite file. Ambiguity is decided deterministically and reversed by an audited correction issued through the CLI. Identity is never derived from the tree.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLite (`sqlite3` stdlib), pytest, argparse.

**Spec:** `docs/superpowers/specs/2026-08-08-oq6-capability-identity-design.md`

## Global Constraints

- **Purity boundary.** `capability/models.py`, `fingerprint.py`, `matcher.py` must never import `temporalio`, `sdlc.models`, or `sdlc.activities`. They may import `sdlc.measurement` only. This mirrors the rule stated in `triage/models.py:3-6` and `measurement.py:12-14`; a dependency here would appear as a reviewable import.
- **Never fabricate a measurement.** An uncomputable fingerprint is `Measurement.not_collected(reason)`, never a score of `0.0`. Zero asserts "definitely not the same"; that is the FR-915 conflation `measurement.py` exists to forbid.
- **Ids are never reused and never deleted.** A retired `BC-007` is never handed to a different capability; it is retired, not removed.
- **Determinism.** Same inputs must produce byte-identical output (NFR-10). Every sort key must be a total order — no reliance on dict or set iteration order.
- **Scope is per-project.** Every store call takes `project: str`.
- **Threshold defaults are provisional.** `T_MATCH = 0.55`, `EPSILON = 0.05`, and `DEFAULT_TIER_WEIGHTS` ship as defaults and are calibration targets, not constants. They must be parameters everywhere, never inlined literals.
- **Line width.** Match the codebase: soft-wrap comments and docstrings near 79 columns.
- **Commit style.** Conventional commits (`feat:`, `test:`, `docs:`). End every commit message with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## File Structure

| File | Responsibility |
|---|---|
| `src/sdlc/capability/__init__.py` | Empty package marker (matches `triage/__init__.py`) |
| `src/sdlc/capability/models.py` | All contracts. Pure Pydantic + `measurement`. |
| `src/sdlc/capability/fingerprint.py` | Per-tier Jaccard and the weighted, renormalized score. Pure. |
| `src/sdlc/capability/matcher.py` | Greedy assignment and `resolve()`. Pure. |
| `src/sdlc/capability/store.py` | `CapabilityIdentityStore` ABC + `BoardIdentityStore`. All identity SQL. |
| `src/sdlc/capability/corrections.py` | `merge` / `split` / `reattach` application. |
| `src/sdlc/capability/export.py` | Hash-only `.sdlc/capabilities.json` writer. |
| `src/sdlc/board/schema.py` | **Modify** — add three identity tables to the existing DDL. |
| `src/sdlc/cli.py` | **Modify** — add the `capability` subcommand group. |

**SQL boundary note for the implementer.** `board/store.py:4` says "All SQL lives here." That statement is scoped to *board state* — artifacts, tasks, events — and `BoardStore` is the single enforcement point for **status moves**. Identity is a different domain with its own enforcement point, so its SQL lives in `capability/store.py`. The DDL still goes in `board/schema.py`, which already owns every table in that database file. Task 5 updates the comment in `board/store.py` to record this boundary so the next reader is not confused.

**Deferred deliberately (YAGNI).** No `capability/activities.py` in this plan. The spec places store I/O in Temporal activities, but E-45's `AssessmentWorkflow` does not exist yet, so there is no workflow caller. The CLI calls the store directly and is not workflow code. Activities land with E-45.

**Also deferred.** The FR-103 memo-key amendment (`identity_registry_version`) is recorded in `ROADMAP.md:139` as pending. It cannot be implemented here because E-46's memo key does not exist yet. `BoardIdentityStore.apply()` returns the new `registry_version` so the term is available the moment E-46 lands.

---

### Task 1: Contracts

**Files:**
- Create: `src/sdlc/capability/__init__.py`
- Create: `src/sdlc/capability/models.py`
- Test: `tests/test_capability_models.py`

**Interfaces:**
- Consumes: `sdlc.measurement.Measurement`, `sdlc.measurement.CollectionState`
- Produces: `SignalTier`, `DEFAULT_TIER_WEIGHTS`, `CapabilityFingerprint`, `IdentityStatus`, `RetiredReason`, `CapabilityIdentity`, `AttachMethod`, `AdvisoryKind`, `Advisory`, `ProposedCapability`, `IdentityAttachment`, `ResolutionResult`

- [ ] **Step 1: Write the failing test**

Create `tests/test_capability_models.py`:

```python
"""FR-913 capability identity contracts (E-47a)."""

import pytest
from pydantic import ValidationError

from sdlc.capability.models import (
    Advisory,
    AdvisoryKind,
    AttachMethod,
    CapabilityFingerprint,
    CapabilityIdentity,
    DEFAULT_TIER_WEIGHTS,
    IdentityAttachment,
    IdentityStatus,
    ProposedCapability,
    ResolutionResult,
    RetiredReason,
    SignalTier,
)
from sdlc.measurement import Measurement


def _fp(**tiers) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier(k): v for k, v in tiers.items()}, collected=Measurement.measured(1.0)
    )


def test_fingerprint_sorts_and_dedupes_tier_members():
    fp = _fp(contract=["POST /b", "POST /a", "POST /b"])
    assert fp.tiers[SignalTier.CONTRACT] == ["POST /a", "POST /b"]


def test_fingerprint_absent_tiers_default_to_empty():
    fp = _fp(contract=["POST /a"])
    assert fp.tiers[SignalTier.BEHAVIORAL] == []
    assert fp.tiers[SignalTier.LOCATIONAL] == []


def test_default_weights_cover_every_tier_and_sum_to_one():
    assert set(DEFAULT_TIER_WEIGHTS) == set(SignalTier)
    assert sum(DEFAULT_TIER_WEIGHTS.values()) == pytest.approx(1.0)


def test_retired_identity_requires_a_reason():
    with pytest.raises(ValidationError, match="retired_reason"):
        CapabilityIdentity(
            bc_id="BC-001",
            project="p",
            first_seen_run="r",
            status=IdentityStatus.RETIRED,
            fingerprint=_fp(contract=["a"]),
        )


def test_active_identity_must_not_carry_a_retired_reason():
    with pytest.raises(ValidationError, match="retired_reason"):
        CapabilityIdentity(
            bc_id="BC-001",
            project="p",
            first_seen_run="r",
            status=IdentityStatus.ACTIVE,
            retired_reason=RetiredReason.NOT_OBSERVED,
            fingerprint=_fp(contract=["a"]),
        )


def test_merged_identity_requires_merged_into():
    with pytest.raises(ValidationError, match="merged_into"):
        CapabilityIdentity(
            bc_id="BC-001",
            project="p",
            first_seen_run="r",
            status=IdentityStatus.MERGED,
            fingerprint=_fp(contract=["a"]),
        )


def test_merged_into_must_not_be_self():
    with pytest.raises(ValidationError, match="itself"):
        CapabilityIdentity(
            bc_id="BC-001",
            project="p",
            first_seen_run="r",
            status=IdentityStatus.MERGED,
            merged_into="BC-001",
            fingerprint=_fp(contract=["a"]),
        )


def test_first_discovery_attachment_carries_no_score():
    with pytest.raises(ValidationError, match="match_score"):
        IdentityAttachment(
            local_key="c0", bc_id="BC-001", method=AttachMethod.FIRST_DISCOVERY, match_score=0.9
        )


def test_matched_attachment_requires_a_score():
    with pytest.raises(ValidationError, match="match_score"):
        IdentityAttachment(local_key="c0", bc_id="BC-001", method=AttachMethod.MATCHED)


def test_resolution_result_defaults_are_empty():
    r = ResolutionResult()
    assert r.attachments == [] and r.retired == [] and r.advisories == []


def test_advisory_carries_kind_and_detail():
    a = Advisory(
        kind=AdvisoryKind.POSSIBLE_RENAME, detail="near miss", related_bc_id="BC-002", score=0.51
    )
    assert a.kind is AdvisoryKind.POSSIBLE_RENAME


def test_proposed_capability_pairs_local_key_with_fingerprint():
    p = ProposedCapability(local_key="c0", fingerprint=_fp(contract=["a"]))
    assert p.local_key == "c0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capability_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.capability'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/capability/__init__.py` as an empty file.

Create `src/sdlc/capability/models.py`:

```python
"""FR-913 (E-47a): capability identity contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as triage/models.py
and measurement.py must not: a dependency here would appear as a reviewable
import.

OQ-6 is resolved by the shape of CapabilityIdentity: `bc_id` is a surrogate
key carried alongside the fingerprint that produced it, not a value derived
from the fingerprint. Nothing here computes an id from content.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from ..measurement import Measurement


class SignalTier(str, Enum):
    """Ordered by cost-to-change. A signal a refactor can alter carelessly is
    weak evidence of identity, which is the entire weighting rationale."""

    CONTRACT = "contract"  # routes, CLI commands, tables, topics
    BEHAVIORAL = "behavioral"  # test names, owned entity names
    STRUCTURAL = "structural"  # exported symbol names
    LOCATIONAL = "locational"  # file paths, directory membership


# Provisional. Calibration targets (benchmarks/calibration.py), never
# inlined at a call site -- every consumer takes them as a parameter.
DEFAULT_TIER_WEIGHTS: dict[SignalTier, float] = {
    SignalTier.CONTRACT: 0.50,
    SignalTier.BEHAVIORAL: 0.25,
    SignalTier.STRUCTURAL: 0.15,
    SignalTier.LOCATIONAL: 0.10,
}

T_MATCH = 0.55  # at/above: attach the existing id
EPSILON = 0.05  # winner-runner_up below this: ambiguous_match advisory


class CapabilityFingerprint(BaseModel):
    """What one assessment observed for one capability.

    `collected` is a Measurement, not a bool: a fingerprint that could not be
    computed reports not_collected and is never scored, which is
    distinguishable from one that computed and found few members (FR-915).
    """

    tiers: dict[SignalTier, list[str]] = Field(default_factory=dict)
    collected: Measurement

    @model_validator(mode="after")
    def _canonicalize(self) -> "CapabilityFingerprint":
        # Sorted and deduped so equal observations hash and compare equal
        # regardless of discovery order (NFR-10 determinism).
        self.tiers = {t: sorted(set(self.tiers.get(t, []))) for t in SignalTier}
        return self


class IdentityStatus(str, Enum):
    ACTIVE = "active"
    RETIRED = "retired"
    MERGED = "merged"


class RetiredReason(str, Enum):
    NOT_OBSERVED = "not_observed"  # no eligible pair this assessment
    ABSORBED = "absorbed"  # lost a merge to another id


class CapabilityIdentity(BaseModel):
    """The registry row. Long-lived; one per capability per project, forever.

    The fingerprint is stored, not just the id: matching assessment N needs
    what assessment N-1 observed. Retired rows keep theirs or they can never
    be revived.
    """

    bc_id: str
    project: str
    first_seen_run: str
    status: IdentityStatus = IdentityStatus.ACTIVE
    retired_reason: RetiredReason | None = None
    merged_into: str | None = None
    derived_from: str | None = None  # set when minted by a split
    fingerprint: CapabilityFingerprint

    @model_validator(mode="after")
    def _status_fields_agree(self) -> "CapabilityIdentity":
        if self.status is IdentityStatus.RETIRED:
            if self.retired_reason is None:
                raise ValueError(
                    "status=retired requires retired_reason -- a retirement "
                    "without a reason cannot be distinguished from a bug"
                )
        elif self.retired_reason is not None:
            raise ValueError(f"retired_reason is set on status={self.status.value}")
        if self.status is IdentityStatus.MERGED:
            if self.merged_into is None:
                raise ValueError("status=merged requires merged_into")
        if self.merged_into == self.bc_id:
            raise ValueError(f"{self.bc_id} cannot be merged into itself")
        if self.derived_from == self.bc_id:
            raise ValueError(f"{self.bc_id} cannot be derived from itself")
        return self


class AttachMethod(str, Enum):
    FIRST_DISCOVERY = "first_discovery"
    MATCHED = "matched"
    FORCED_BY_CORRECTION = "forced_by_correction"


class AdvisoryKind(str, Enum):
    POSSIBLE_RENAME = "possible_rename"
    AMBIGUOUS_MATCH = "ambiguous_match"
    SPLIT = "split"
    IDENTITY_NOT_ASSESSED = "identity_not_assessed"


class Advisory(BaseModel):
    kind: AdvisoryKind
    detail: str
    local_key: str = ""
    related_bc_id: str | None = None
    score: float | None = None


class ProposedCapability(BaseModel):
    """One capability boundary proposed by discover (E-48), before it has an
    id. `local_key` is the caller's handle for this assessment only."""

    local_key: str
    fingerprint: CapabilityFingerprint


class IdentityAttachment(BaseModel):
    """The per-assessment join, carrying the evidence for why this id was
    used. `contributions` is the per-tier score breakdown -- it falls out of
    scoring rather than being assembled separately."""

    local_key: str
    bc_id: str
    method: AttachMethod
    match_score: float | None = None
    contributions: dict[SignalTier, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _score_matches_method(self) -> "IdentityAttachment":
        if self.method is AttachMethod.MATCHED:
            if self.match_score is None:
                raise ValueError("method=matched requires a match_score")
        elif self.match_score is not None:
            raise ValueError(
                f"match_score is set on method={self.method.value}; only a "
                f"matched attachment was scored"
            )
        return self


class ResolutionResult(BaseModel):
    attachments: list[IdentityAttachment] = Field(default_factory=list)
    retired: list[str] = Field(default_factory=list)
    merged: dict[str, str] = Field(default_factory=dict)  # loser -> winner
    advisories: list[Advisory] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capability_models.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/capability/ tests/test_capability_models.py
git commit -m "feat(capability): identity contracts (E-47a)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Similarity scoring

**Files:**
- Create: `src/sdlc/capability/fingerprint.py`
- Test: `tests/test_capability_fingerprint.py`

**Interfaces:**
- Consumes: `SignalTier`, `CapabilityFingerprint`, `DEFAULT_TIER_WEIGHTS` from Task 1
- Produces:
  - `jaccard(a: Sequence[str], b: Sequence[str]) -> float`
  - `score(a: CapabilityFingerprint, b: CapabilityFingerprint, weights: Mapping[SignalTier, float]) -> tuple[float, dict[SignalTier, float]] | None` — returns `None` when the pair is **not comparable** (either side uncollected, or no tier non-empty on both sides)

- [ ] **Step 1: Write the failing test**

Create `tests/test_capability_fingerprint.py`:

```python
"""FR-913 similarity scoring (E-47a)."""

import pytest

from sdlc.capability.fingerprint import jaccard, score
from sdlc.capability.models import (
    CapabilityFingerprint,
    DEFAULT_TIER_WEIGHTS,
    SignalTier,
)
from sdlc.measurement import Measurement


def _fp(collected=True, **tiers) -> CapabilityFingerprint:
    m = Measurement.measured(1.0) if collected else Measurement.not_collected("parse failure")
    return CapabilityFingerprint(tiers={SignalTier(k): v for k, v in tiers.items()}, collected=m)


def test_jaccard_identical_sets_is_one():
    assert jaccard(["a", "b"], ["b", "a"]) == 1.0


def test_jaccard_disjoint_sets_is_zero():
    assert jaccard(["a"], ["b"]) == 0.0


def test_jaccard_partial_overlap():
    assert jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)


def test_jaccard_two_empty_sets_is_zero_not_a_division_error():
    assert jaccard([], []) == 0.0


def test_identical_fingerprints_score_one():
    fp = _fp(contract=["POST /login"], structural=["Auth"])
    total, contrib = score(fp, fp, DEFAULT_TIER_WEIGHTS)
    assert total == pytest.approx(1.0)
    assert contrib[SignalTier.CONTRACT] == pytest.approx(1.0)


def test_absent_tier_is_renormalized_away_not_scored_zero():
    # Both sides have ONLY structural members. If the absent contract tier
    # counted as zero the score would be 0.15; renormalized it is 1.0.
    a = _fp(structural=["Auth", "Token"])
    b = _fp(structural=["Auth", "Token"])
    total, contrib = score(a, b, DEFAULT_TIER_WEIGHTS)
    assert total == pytest.approx(1.0)
    assert SignalTier.CONTRACT not in contrib


def test_contract_tier_dominates_a_full_structural_rename():
    # Every symbol and path renamed; routes and tables untouched.
    a = _fp(contract=["POST /login"], structural=["OldAuth"], locational=["old/auth.py"])
    b = _fp(contract=["POST /login"], structural=["NewIdentity"], locational=["new/identity.py"])
    total, _ = score(a, b, DEFAULT_TIER_WEIGHTS)
    assert total > 0.55


def test_changing_the_contract_costs_more_than_changing_symbols():
    base = _fp(contract=["POST /login"], structural=["Auth"])
    renamed_symbol = _fp(contract=["POST /login"], structural=["Identity"])
    changed_route = _fp(contract=["POST /signin"], structural=["Auth"])
    symbol_score, _ = score(base, renamed_symbol, DEFAULT_TIER_WEIGHTS)
    route_score, _ = score(base, changed_route, DEFAULT_TIER_WEIGHTS)
    assert symbol_score > route_score


def test_uncollected_fingerprint_is_not_comparable():
    assert (
        score(_fp(collected=False, contract=["a"]), _fp(contract=["a"]), DEFAULT_TIER_WEIGHTS)
        is None
    )
    assert (
        score(_fp(contract=["a"]), _fp(collected=False, contract=["a"]), DEFAULT_TIER_WEIGHTS)
        is None
    )


def test_no_mutually_present_tier_is_not_comparable_not_zero():
    a = _fp(contract=["POST /a"])
    b = _fp(structural=["Thing"])
    assert score(a, b, DEFAULT_TIER_WEIGHTS) is None


def test_score_is_symmetric():
    a = _fp(contract=["POST /a", "POST /b"], structural=["X"])
    b = _fp(contract=["POST /b"], structural=["X", "Y"])
    assert score(a, b, DEFAULT_TIER_WEIGHTS)[0] == pytest.approx(
        score(b, a, DEFAULT_TIER_WEIGHTS)[0]
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capability_fingerprint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.capability.fingerprint'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/capability/fingerprint.py`:

```python
"""FR-913 (E-47a): per-tier Jaccard and the weighted, renormalized score.

Pure. The per-tier contributions returned alongside the total ARE the
evidence trail an attachment records -- they fall out of scoring rather than
being assembled separately, so evidence cannot drift from the decision.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .models import CapabilityFingerprint, SignalTier

from ..measurement import CollectionState


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    """|A n B| / |A u B|. Two empty sets score 0.0 rather than raising: the
    caller never passes a pair of empty tiers, because score() drops tiers
    that are not non-empty on BOTH sides before calling this."""
    sa, sb = set(a), set(b)
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def score(
    a: CapabilityFingerprint, b: CapabilityFingerprint, weights: Mapping[SignalTier, float]
) -> tuple[float, dict[SignalTier, float]] | None:
    """Weighted Jaccard over tiers present on BOTH sides, or None when the
    pair is not comparable.

    None -- not 0.0 -- in two cases, and the distinction is FR-915's:

      * either fingerprint is not_collected. A fingerprint that could not be
        computed has not been shown to differ from anything.
      * no tier is non-empty on both sides. There is no evidence either way.

    Returning 0.0 for these would assert "definitely not the same", which is
    a claim neither case supports.

    Weights renormalize over the mutually-present tiers. Counting an absent
    Contract tier as zero would bias systematically against internal
    capabilities -- exactly those whose other signals are weakest too.
    """
    if a.collected.state is not CollectionState.MEASURED:
        return None
    if b.collected.state is not CollectionState.MEASURED:
        return None

    shared = [t for t in SignalTier if a.tiers.get(t) and b.tiers.get(t)]
    if not shared:
        return None

    denominator = sum(weights[t] for t in shared)
    if denominator <= 0.0:
        return None

    contributions: dict[SignalTier, float] = {t: jaccard(a.tiers[t], b.tiers[t]) for t in shared}
    total = sum(weights[t] * contributions[t] for t in shared) / denominator
    return total, contributions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capability_fingerprint.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/capability/fingerprint.py tests/test_capability_fingerprint.py
git commit -m "feat(capability): weighted-Jaccard similarity with tier renormalization (E-47a)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Greedy one-to-one assignment

**Files:**
- Create: `src/sdlc/capability/matcher.py`
- Test: `tests/test_capability_assignment.py`

**Interfaces:**
- Consumes: nothing from Task 2 at runtime (operates on already-scored pairs)
- Produces: `Pair` (NamedTuple: `score: float`, `bc_id: str`, `local_key: str`), `assign(pairs: Iterable[Pair]) -> dict[str, str]` returning `local_key -> bc_id`

- [ ] **Step 1: Write the failing test**

Create `tests/test_capability_assignment.py`:

```python
"""FR-913 greedy one-to-one assignment (E-47a)."""

from sdlc.capability.matcher import Pair, assign


def test_single_pair_attaches():
    assert assign([Pair(0.9, "BC-001", "c0")]) == {"c0": "BC-001"}


def test_two_locals_cannot_both_claim_one_id():
    # The naive per-capability argmax would give BC-001 to both.
    got = assign([Pair(0.9, "BC-001", "c0"), Pair(0.8, "BC-001", "c1")])
    assert got == {"c0": "BC-001"}


def test_one_local_cannot_claim_two_ids():
    got = assign([Pair(0.9, "BC-001", "c0"), Pair(0.8, "BC-002", "c0")])
    assert got == {"c0": "BC-001"}


def test_strong_pair_wins_regardless_of_other_candidates():
    # Local stability: c0/BC-001 is the best pair and must survive whatever
    # else is present. This is the property Hungarian does NOT guarantee.
    got = assign(
        [
            Pair(0.95, "BC-001", "c0"),
            Pair(0.94, "BC-001", "c1"),
            Pair(0.93, "BC-002", "c1"),
            Pair(0.10, "BC-002", "c0"),
        ]
    )
    assert got["c0"] == "BC-001"
    assert got["c1"] == "BC-002"


def test_ties_break_on_bc_id_ascending():
    got = assign([Pair(0.7, "BC-002", "c0"), Pair(0.7, "BC-001", "c0")])
    assert got == {"c0": "BC-001"}


def test_ties_on_score_and_bc_id_break_on_local_key_ascending():
    got = assign([Pair(0.7, "BC-001", "c1"), Pair(0.7, "BC-001", "c0")])
    assert got == {"c0": "BC-001"}


def test_assignment_is_order_independent():
    pairs = [Pair(0.9, "BC-001", "c0"), Pair(0.8, "BC-002", "c1"), Pair(0.7, "BC-001", "c1")]
    assert assign(pairs) == assign(list(reversed(pairs)))


def test_no_pairs_yields_no_assignments():
    assert assign([]) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capability_assignment.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.capability.matcher'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/capability/matcher.py`:

```python
"""FR-913 (E-47a): greedy one-to-one assignment.

The Hungarian algorithm is deliberately NOT used. Global optimality means an
unrelated third capability's score can move a pair that matched perfectly
well onto a different id -- indefensible for an identifier a client cites in
a delivered document, because there is no way to explain why BC-003 moved
because of a change somewhere else.

Greedy is locally stable: a strong pair matches regardless of what else is
in the set, and the rule states in one sentence. Capability counts are in
the tens, so O(n^2) scoring is not a constraint.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple


class Pair(NamedTuple):
    score: float
    bc_id: str
    local_key: str


def assign(pairs: Iterable[Pair]) -> dict[str, str]:
    """local_key -> bc_id, one-to-one.

    Sorting on (-score, bc_id, local_key) is a total order over distinct
    pairs, so the result is independent of input order (NFR-10). Both sides
    are consumed on a claim, which is what stops two capabilities taking one
    id -- the failure a per-capability argmax would produce.
    """
    claimed_ids: set[str] = set()
    claimed_locals: set[str] = set()
    out: dict[str, str] = {}
    for p in sorted(pairs, key=lambda p: (-p.score, p.bc_id, p.local_key)):
        if p.bc_id in claimed_ids or p.local_key in claimed_locals:
            continue
        claimed_ids.add(p.bc_id)
        claimed_locals.add(p.local_key)
        out[p.local_key] = p.bc_id
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capability_assignment.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/capability/matcher.py tests/test_capability_assignment.py
git commit -m "feat(capability): greedy one-to-one assignment (E-47a)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `resolve()` — the full matcher

**Files:**
- Modify: `src/sdlc/capability/matcher.py` (append; keep `Pair` and `assign` unchanged)
- Test: `tests/test_capability_resolve.py`

**Interfaces:**
- Consumes: `score` (Task 2), `Pair`/`assign` (Task 3), all contracts (Task 1)
- Produces:
  ```python
  def resolve(
      proposed: Sequence[ProposedCapability],
      registry: Sequence[CapabilityIdentity],
      *,
      allocate: Callable[[], str],
      weights: Mapping[SignalTier, float] = DEFAULT_TIER_WEIGHTS,
      t_match: float = T_MATCH,
      epsilon: float = EPSILON,
  ) -> ResolutionResult
  ```
  `allocate` is injected rather than derived so the matcher stays pure — id allocation is store state, and Task 5 supplies the real counter.

- [ ] **Step 1: Write the failing test**

Create `tests/test_capability_resolve.py`:

```python
"""FR-913 identity resolution (E-47a)."""

import itertools

from sdlc.capability.matcher import resolve
from sdlc.capability.models import (
    AdvisoryKind,
    AttachMethod,
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityStatus,
    ProposedCapability,
    RetiredReason,
    SignalTier,
)
from sdlc.measurement import Measurement


def _fp(collected=True, **tiers) -> CapabilityFingerprint:
    m = Measurement.measured(1.0) if collected else Measurement.not_collected("parse failure")
    return CapabilityFingerprint(tiers={SignalTier(k): v for k, v in tiers.items()}, collected=m)


def _identity(bc_id, fp, status=IdentityStatus.ACTIVE, reason=None):
    return CapabilityIdentity(
        bc_id=bc_id,
        project="p",
        first_seen_run="r0",
        status=status,
        retired_reason=reason,
        fingerprint=fp,
    )


def _allocator(start=900):
    counter = itertools.count(start)
    return lambda: f"BC-{next(counter):03d}"


def _kinds(result):
    return {a.kind for a in result.advisories}


def test_empty_registry_is_all_first_discovery_with_no_advisories():
    proposed = [
        ProposedCapability(local_key="c0", fingerprint=_fp(contract=["POST /a"])),
        ProposedCapability(local_key="c1", fingerprint=_fp(contract=["POST /b"])),
    ]
    r = resolve(proposed, [], allocate=_allocator())
    assert [a.method for a in r.attachments] == [
        AttachMethod.FIRST_DISCOVERY,
        AttachMethod.FIRST_DISCOVERY,
    ]
    assert all(a.match_score is None for a in r.attachments)
    assert r.advisories == []


def test_unchanged_capability_keeps_its_id():
    fp = _fp(contract=["POST /login"], structural=["Auth"])
    r = resolve(
        [ProposedCapability(local_key="c0", fingerprint=fp)],
        [_identity("BC-001", fp)],
        allocate=_allocator(),
    )
    assert r.attachments[0].bc_id == "BC-001"
    assert r.attachments[0].method is AttachMethod.MATCHED
    assert r.attachments[0].match_score == 1.0


def test_attachment_records_per_tier_contributions_as_evidence():
    fp = _fp(contract=["POST /login"], structural=["Auth"])
    r = resolve(
        [ProposedCapability(local_key="c0", fingerprint=fp)],
        [_identity("BC-001", fp)],
        allocate=_allocator(),
    )
    contrib = r.attachments[0].contributions
    assert contrib[SignalTier.CONTRACT] == 1.0
    assert contrib[SignalTier.STRUCTURAL] == 1.0


def test_heavy_internal_refactor_keeps_the_id():
    stored = _fp(contract=["POST /login"], structural=["OldAuth"], locational=["old/auth.py"])
    now = _fp(
        contract=["POST /login"], structural=["NewIdentity"], locational=["pkg/new/identity.py"]
    )
    r = resolve(
        [ProposedCapability(local_key="c0", fingerprint=now)],
        [_identity("BC-001", stored)],
        allocate=_allocator(),
    )
    assert r.attachments[0].bc_id == "BC-001"


def test_unrelated_capability_gets_a_new_id_and_a_rename_advisory():
    stored = _fp(contract=["POST /login"], structural=["Auth"])
    now = _fp(contract=["GET /reports"], structural=["Reporting"])
    r = resolve(
        [ProposedCapability(local_key="c0", fingerprint=now)],
        [_identity("BC-001", stored)],
        allocate=_allocator(),
    )
    assert r.attachments[0].bc_id == "BC-900"
    assert AdvisoryKind.POSSIBLE_RENAME in _kinds(r)
    near = next(a for a in r.advisories if a.kind is AdvisoryKind.POSSIBLE_RENAME)
    assert near.related_bc_id == "BC-001" and near.score is not None


def test_uncomputable_fingerprint_gets_new_id_and_is_not_scored():
    stored = _fp(contract=["POST /login"])
    now = _fp(collected=False, contract=["POST /login"])
    r = resolve(
        [ProposedCapability(local_key="c0", fingerprint=now)],
        [_identity("BC-001", stored)],
        allocate=_allocator(),
    )
    assert r.attachments[0].bc_id == "BC-900"
    assert r.attachments[0].match_score is None
    assert AdvisoryKind.IDENTITY_NOT_ASSESSED in _kinds(r)


def test_detected_split_keeps_the_id_on_the_stronger_half():
    stored = _fp(contract=["POST /login", "POST /logout"], structural=["Auth"])
    strong = _fp(contract=["POST /login", "POST /logout"], structural=["Auth"])
    weak = _fp(contract=["POST /login"], structural=["Auth"])
    r = resolve(
        [
            ProposedCapability(local_key="c0", fingerprint=strong),
            ProposedCapability(local_key="c1", fingerprint=weak),
        ],
        [_identity("BC-001", stored)],
        allocate=_allocator(),
    )
    bykey = {a.local_key: a for a in r.attachments}
    assert bykey["c0"].bc_id == "BC-001"
    assert bykey["c1"].bc_id == "BC-900"
    assert AdvisoryKind.SPLIT in _kinds(r)


def test_detected_merge_marks_the_loser_merged_into_the_winner():
    a = _fp(contract=["POST /login"], structural=["Auth"])
    b = _fp(contract=["POST /login"], structural=["Auth", "Session"])
    now = _fp(contract=["POST /login"], structural=["Auth", "Session"])
    r = resolve(
        [ProposedCapability(local_key="c0", fingerprint=now)],
        [_identity("BC-001", a), _identity("BC-002", b)],
        allocate=_allocator(),
    )
    winner = r.attachments[0].bc_id
    assert winner == "BC-002"
    assert r.merged == {"BC-001": "BC-002"}
    assert r.retired == []


def test_vanished_capability_is_retired_not_merged():
    stored = _fp(contract=["POST /legacy"], structural=["Legacy"])
    now = _fp(contract=["GET /reports"], structural=["Reporting"])
    r = resolve(
        [ProposedCapability(local_key="c0", fingerprint=now)],
        [_identity("BC-001", stored)],
        allocate=_allocator(),
    )
    assert r.retired == ["BC-001"]
    assert r.merged == {}


def test_retired_capability_revives_when_it_reappears():
    fp = _fp(contract=["POST /login"], structural=["Auth"])
    stored = _identity(
        "BC-001", fp, status=IdentityStatus.RETIRED, reason=RetiredReason.NOT_OBSERVED
    )
    r = resolve(
        [ProposedCapability(local_key="c0", fingerprint=fp)], [stored], allocate=_allocator()
    )
    assert r.attachments[0].bc_id == "BC-001"
    assert r.retired == []


def test_merged_rows_are_never_matched_against():
    fp = _fp(contract=["POST /login"], structural=["Auth"])
    dead = CapabilityIdentity(
        bc_id="BC-001",
        project="p",
        first_seen_run="r0",
        status=IdentityStatus.MERGED,
        merged_into="BC-002",
        fingerprint=fp,
    )
    r = resolve([ProposedCapability(local_key="c0", fingerprint=fp)], [dead], allocate=_allocator())
    assert r.attachments[0].bc_id == "BC-900"


def test_near_tie_emits_ambiguous_match():
    now = _fp(contract=["POST /a", "POST /b"], structural=["X"])
    one = _fp(contract=["POST /a", "POST /b"], structural=["X"])
    two = _fp(contract=["POST /a", "POST /b"], structural=["X", "Y"])
    r = resolve(
        [ProposedCapability(local_key="c0", fingerprint=now)],
        [_identity("BC-001", one), _identity("BC-002", two)],
        allocate=_allocator(),
        epsilon=0.9,
    )
    assert AdvisoryKind.AMBIGUOUS_MATCH in _kinds(r)


def test_resolution_is_deterministic_across_input_order():
    fps = {k: _fp(contract=[f"POST /{k}"], structural=[k.upper()]) for k in ("a", "b", "c")}
    registry = [_identity(f"BC-00{i}", fps[k]) for i, k in enumerate(("a", "b", "c"), start=1)]
    proposed = [ProposedCapability(local_key=k, fingerprint=fps[k]) for k in ("a", "b", "c")]
    first = resolve(proposed, registry, allocate=_allocator())
    second = resolve(list(reversed(proposed)), list(reversed(registry)), allocate=_allocator())
    assert {(a.local_key, a.bc_id) for a in first.attachments} == {
        (a.local_key, a.bc_id) for a in second.attachments
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capability_resolve.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve' from 'sdlc.capability.matcher'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/capability/matcher.py` (add the imports at the top of the file alongside the existing ones):

```python
from collections.abc import Callable, Mapping, Sequence

from .fingerprint import score as score_pair
from .models import (
    Advisory,
    AdvisoryKind,
    AttachMethod,
    CapabilityIdentity,
    DEFAULT_TIER_WEIGHTS,
    EPSILON,
    IdentityAttachment,
    IdentityStatus,
    ProposedCapability,
    ResolutionResult,
    SignalTier,
    T_MATCH,
)


def resolve(
    proposed: Sequence[ProposedCapability],
    registry: Sequence[CapabilityIdentity],
    *,
    allocate: Callable[[], str],
    weights: Mapping[SignalTier, float] = DEFAULT_TIER_WEIGHTS,
    t_match: float = T_MATCH,
    epsilon: float = EPSILON,
) -> ResolutionResult:
    """Attach an id to every proposed capability.

    `allocate` is injected, not derived: id allocation is store state and
    this function is pure. Task 5's BoardIdentityStore supplies the real
    counter; tests supply a deterministic one.

    MERGED rows are excluded from candidacy -- a merged id has been absorbed
    and must never be handed back out. RETIRED rows ARE candidates: a scan
    that matches one revives it, which is re-attachment to the same
    capability, not reuse by a different one.
    """
    candidates = [r for r in registry if r.status is not IdentityStatus.MERGED]

    scored: dict[tuple[str, str], tuple[float, dict[SignalTier, float]]] = {}
    uncomputable: list[str] = []
    for p in proposed:
        comparable = False
        for c in candidates:
            got = score_pair(p.fingerprint, c.fingerprint, weights)
            if got is None:
                continue
            comparable = True
            scored[(p.local_key, c.bc_id)] = got
        if not comparable and not _is_measured(p):
            uncomputable.append(p.local_key)

    eligible = [
        Pair(total, bc_id, local_key)
        for (local_key, bc_id), (total, _) in scored.items()
        if total >= t_match
    ]
    assigned = assign(eligible)

    result = ResolutionResult()
    claimed_ids = set(assigned.values())

    for p in proposed:
        bc_id = assigned.get(p.local_key)
        if bc_id is not None:
            total, contributions = scored[(p.local_key, bc_id)]
            result.attachments.append(
                IdentityAttachment(
                    local_key=p.local_key,
                    bc_id=bc_id,
                    method=AttachMethod.MATCHED,
                    match_score=total,
                    contributions=contributions,
                )
            )
            _maybe_ambiguous(result, p.local_key, bc_id, scored, eligible, epsilon)
            continue

        new_id = allocate()
        lost_to = _lost_above_threshold(p.local_key, scored, claimed_ids, t_match)
        result.attachments.append(
            IdentityAttachment(
                local_key=p.local_key, bc_id=new_id, method=AttachMethod.FIRST_DISCOVERY
            )
        )

        if p.local_key in uncomputable:
            result.advisories.append(
                Advisory(
                    kind=AdvisoryKind.IDENTITY_NOT_ASSESSED,
                    local_key=p.local_key,
                    detail=(
                        f"fingerprint not collected "
                        f"({p.fingerprint.collected.reason}); identity was "
                        f"not assessed and {new_id} was minted"
                    ),
                )
            )
        elif lost_to is not None:
            result.advisories.append(
                Advisory(
                    kind=AdvisoryKind.SPLIT,
                    local_key=p.local_key,
                    related_bc_id=lost_to,
                    score=scored[(p.local_key, lost_to)][0],
                    detail=(
                        f"{lost_to} also matched this capability above "
                        f"threshold but was claimed by a stronger match; "
                        f"{new_id} minted as a split of {lost_to}"
                    ),
                )
            )
        elif candidates:
            near = _best_near_miss(p.local_key, scored)
            if near is not None:
                near_id, near_score = near
                result.advisories.append(
                    Advisory(
                        kind=AdvisoryKind.POSSIBLE_RENAME,
                        local_key=p.local_key,
                        related_bc_id=near_id,
                        score=near_score,
                        detail=(
                            f"closest stored capability {near_id} scored "
                            f"{near_score:.3f}, below t_match={t_match}; "
                            f"{new_id} minted"
                        ),
                    )
                )

    for c in candidates:
        if c.bc_id in claimed_ids:
            continue
        absorbed_by = _absorbed_by(c.bc_id, scored, assigned, t_match)
        if absorbed_by is not None:
            result.merged[c.bc_id] = absorbed_by
        elif c.status is IdentityStatus.ACTIVE:
            result.retired.append(c.bc_id)

    result.retired.sort()
    return result


def _is_measured(p: ProposedCapability) -> bool:
    from ..measurement import CollectionState

    return p.fingerprint.collected.state is CollectionState.MEASURED


def _best_near_miss(local_key: str, scored) -> tuple[str, float] | None:
    """Highest sub-threshold candidate for this local_key, for the advisory.
    Ties break on bc_id so the reported near-miss is deterministic."""
    misses = [(bc_id, total) for (lk, bc_id), (total, _) in scored.items() if lk == local_key]
    if not misses:
        return None
    return sorted(misses, key=lambda m: (-m[1], m[0]))[0]


def _lost_above_threshold(
    local_key: str, scored, claimed_ids: set[str], t_match: float
) -> str | None:
    """An id this capability matched above threshold that another capability
    claimed -- i.e. a DETECTED split. Distinct from the `split` correction."""
    losses = [
        (bc_id, total)
        for (lk, bc_id), (total, _) in scored.items()
        if lk == local_key and total >= t_match and bc_id in claimed_ids
    ]
    if not losses:
        return None
    return sorted(losses, key=lambda m: (-m[1], m[0]))[0][0]


def _absorbed_by(bc_id: str, scored, assigned: dict[str, str], t_match: float) -> str | None:
    """The id that took the capability this one also matched above threshold
    -- a DETECTED merge. None means it simply was not observed."""
    rivals = [
        (lk, total)
        for (lk, cid), (total, _) in scored.items()
        if cid == bc_id and total >= t_match and lk in assigned
    ]
    if not rivals:
        return None
    winner_local = sorted(rivals, key=lambda m: (-m[1], m[0]))[0][0]
    return assigned[winner_local]


def _maybe_ambiguous(
    result: ResolutionResult, local_key: str, bc_id: str, scored, eligible, epsilon: float
) -> None:
    winner = scored[(local_key, bc_id)][0]
    runners = sorted(
        (p.score for p in eligible if p.local_key == local_key and p.bc_id != bc_id), reverse=True
    )
    if runners and (winner - runners[0]) < epsilon:
        result.advisories.append(
            Advisory(
                kind=AdvisoryKind.AMBIGUOUS_MATCH,
                local_key=local_key,
                related_bc_id=bc_id,
                score=winner,
                detail=(
                    f"runner-up scored {runners[0]:.3f} against winner "
                    f"{winner:.3f}, within epsilon={epsilon}; decided "
                    f"deterministically and reversible by correction"
                ),
            )
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capability_resolve.py tests/test_capability_assignment.py -v`
Expected: PASS (21 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/capability/matcher.py tests/test_capability_resolve.py
git commit -m "feat(capability): resolve() with split/merge/retire/revive detection (E-47a)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Board-backed identity store

**Files:**
- Create: `src/sdlc/capability/store.py`
- Modify: `src/sdlc/board/schema.py` (append three tables to `DDL`)
- Modify: `src/sdlc/board/store.py:4` (scope the "All SQL lives here" comment)
- Test: `tests/test_capability_store.py`

**Interfaces:**
- Consumes: `CapabilityIdentity`, `IdentityStatus`, `RetiredReason`, `CapabilityFingerprint` (Task 1); `sdlc.board.schema.connect`, `sdlc.board.schema.apply_schema`, `sdlc.board.schema.db_path`
- Produces:
  - `IdentityStoreError`, `IdentityConflictError`, `IdentityNotFoundError`
  - `CapabilityIdentityStore` (ABC) with `load(project)`, `apply(project, rows, expected_version)`, `allocator(project)`, `registry_version(project)`
  - `BoardIdentityStore(db=None)` implementing it

- [ ] **Step 1: Write the failing test**

Create `tests/test_capability_store.py`:

```python
"""FR-913 identity persistence (E-47a)."""

import pytest

from sdlc.capability.models import (
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityStatus,
    RetiredReason,
    SignalTier,
)
from sdlc.capability.store import (
    BoardIdentityStore,
    IdentityConflictError,
)
from sdlc.measurement import Measurement


@pytest.fixture()
def store(tmp_path):
    s = BoardIdentityStore(db=tmp_path / "board.sqlite3")
    yield s
    s.close()


def _fp(**tiers) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier(k): v for k, v in tiers.items()}, collected=Measurement.measured(1.0)
    )


def _identity(bc_id, **kw) -> CapabilityIdentity:
    kw.setdefault("fingerprint", _fp(contract=[f"POST /{bc_id}"]))
    return CapabilityIdentity(bc_id=bc_id, project="p", first_seen_run="r0", **kw)


def test_empty_project_loads_empty_at_version_zero(store):
    assert store.load("p") == []
    assert store.registry_version("p") == 0


def test_apply_round_trips_an_identity(store):
    store.apply("p", [_identity("BC-001")], expected_version=0)
    (got,) = store.load("p")
    assert got.bc_id == "BC-001"
    assert got.fingerprint.tiers[SignalTier.CONTRACT] == ["POST /BC-001"]


def test_apply_bumps_registry_version(store):
    assert store.apply("p", [_identity("BC-001")], expected_version=0) == 1
    assert store.apply("p", [_identity("BC-002")], expected_version=1) == 2


def test_stale_expected_version_conflicts(store):
    store.apply("p", [_identity("BC-001")], expected_version=0)
    with pytest.raises(IdentityConflictError):
        store.apply("p", [_identity("BC-002")], expected_version=0)


def test_apply_upserts_an_existing_row(store):
    store.apply("p", [_identity("BC-001")], expected_version=0)
    store.apply(
        "p",
        [
            _identity(
                "BC-001", status=IdentityStatus.RETIRED, retired_reason=RetiredReason.NOT_OBSERVED
            )
        ],
        expected_version=1,
    )
    (got,) = store.load("p")
    assert got.status is IdentityStatus.RETIRED
    assert got.retired_reason is RetiredReason.NOT_OBSERVED


def test_projects_are_isolated(store):
    store.apply("p", [_identity("BC-001")], expected_version=0)
    assert store.load("other") == []
    assert store.registry_version("other") == 0


def test_allocator_is_monotonic_and_never_reuses(store):
    alloc = store.allocator("p")
    assert [alloc(), alloc()] == ["BC-001", "BC-002"]
    store.apply("p", [_identity("BC-001"), _identity("BC-002")], expected_version=0)
    assert store.allocator("p")() == "BC-003"


def test_allocator_skips_retired_ids(store):
    store.apply(
        "p",
        [
            _identity(
                "BC-001", status=IdentityStatus.RETIRED, retired_reason=RetiredReason.NOT_OBSERVED
            )
        ],
        expected_version=0,
    )
    # Never reuse: BC-001 is retired, not free.
    assert store.allocator("p")() == "BC-002"


def test_load_returns_rows_sorted_by_bc_id(store):
    store.apply(
        "p", [_identity("BC-003"), _identity("BC-001"), _identity("BC-002")], expected_version=0
    )
    assert [r.bc_id for r in store.load("p")] == ["BC-001", "BC-002", "BC-003"]


def test_reopening_the_same_db_sees_prior_state(tmp_path):
    db = tmp_path / "board.sqlite3"
    first = BoardIdentityStore(db=db)
    first.apply("p", [_identity("BC-001")], expected_version=0)
    first.close()
    second = BoardIdentityStore(db=db)
    assert [r.bc_id for r in second.load("p")] == ["BC-001"]
    assert second.registry_version("p") == 1
    second.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capability_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.capability.store'`

- [ ] **Step 3: Write minimal implementation**

First, append to the `DDL` string in `src/sdlc/board/schema.py`, immediately before its closing `"""`:

```sql
CREATE TABLE IF NOT EXISTS capability_registry (
    project          TEXT PRIMARY KEY,
    registry_version INTEGER NOT NULL DEFAULT 0,
    next_ordinal     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS capability_identity (
    project        TEXT NOT NULL,
    bc_id          TEXT NOT NULL,
    first_seen_run TEXT NOT NULL,
    status         TEXT NOT NULL,
    retired_reason TEXT,
    merged_into    TEXT,
    derived_from   TEXT,
    fingerprint    TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (project, bc_id)
);

CREATE TABLE IF NOT EXISTS capability_event (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project    TEXT NOT NULL,
    bc_id      TEXT NOT NULL,
    actor      TEXT NOT NULL,
    operation  TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
```

Next, replace the comment on `src/sdlc/board/store.py:4` so the boundary is recorded:

```python
"""BoardStore: the single enforcement point for board state.

All board-state SQL lives here — artifacts, tasks, events. Both writers reach
the board through this class — the workflow via board/activities.py
(in-process), agents via board/api.py — so there is exactly one place that can
move a status.

Capability identity (E-47a) is a different domain with its own enforcement
point, capability/store.py; its DDL still lives in schema.py, which owns every
table in this database file.
"""
```

Create `src/sdlc/capability/store.py`:

```python
"""FR-913 (E-47a): identity persistence.

ADR-19 — adapters, not substrate. The ABC is the seam; BoardIdentityStore is
the one reference implementation, backed by the E-78 board's SQLite file and
reusing its optimistic-concurrency discipline rather than inventing a second
scheme in the same database.

All identity SQL lives here. See board/store.py's docstring for why this is
a second SQL owner over one file rather than a violation of its rule.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from ..board.schema import apply_schema, connect, db_path
from .models import CapabilityFingerprint, CapabilityIdentity


class IdentityStoreError(Exception):
    """Base for identity write rejections."""


class IdentityConflictError(IdentityStoreError):
    """Optimistic-concurrency failure: caller's registry_version is stale.

    The caller must reload and RE-MATCH, not replay its computed
    attachments — the registry it matched against has moved.
    """


class IdentityNotFoundError(IdentityStoreError):
    """No such project or bc_id."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CapabilityIdentityStore(ABC):
    @abstractmethod
    def load(self, project: str) -> list[CapabilityIdentity]:
        """Every row for the project, sorted by bc_id. Includes retired rows
        (they are match candidates) and merged rows (callers exclude them)."""

    @abstractmethod
    def registry_version(self, project: str) -> int:
        """0 for a project that has never been written."""

    @abstractmethod
    def apply(
        self,
        project: str,
        rows: Sequence[CapabilityIdentity],
        *,
        expected_version: int,
        actor: str = "system",
        operation: str = "resolve",
    ) -> int:
        """Upsert rows in one transaction. Returns the new registry_version."""

    @abstractmethod
    def allocator(self, project: str) -> Callable[[], str]:
        """A fresh `BC-NNN` minter. Never returns an id that has ever been
        allocated for this project, retired or not — invariant 1."""


class BoardIdentityStore(CapabilityIdentityStore):
    def __init__(self, db: str | os.PathLike | None = None) -> None:
        self._conn = connect(db if db is not None else db_path())
        apply_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    def load(self, project: str) -> list[CapabilityIdentity]:
        rows = self._conn.execute(
            "SELECT bc_id, first_seen_run, status, retired_reason, "
            "merged_into, derived_from, fingerprint "
            "FROM capability_identity WHERE project = ? ORDER BY bc_id",
            (project,),
        ).fetchall()
        return [
            CapabilityIdentity(
                bc_id=r[0],
                project=project,
                first_seen_run=r[1],
                status=r[2],
                retired_reason=r[3],
                merged_into=r[4],
                derived_from=r[5],
                fingerprint=CapabilityFingerprint.model_validate_json(r[6]),
            )
            for r in rows
        ]

    def registry_version(self, project: str) -> int:
        row = self._conn.execute(
            "SELECT registry_version FROM capability_registry WHERE project = ?", (project,)
        ).fetchone()
        return row[0] if row else 0

    def apply(
        self,
        project: str,
        rows: Sequence[CapabilityIdentity],
        *,
        expected_version: int,
        actor: str = "system",
        operation: str = "resolve",
    ) -> int:
        with self._conn:  # one transaction
            current = self.registry_version(project)
            if current != expected_version:
                raise IdentityConflictError(
                    f"registry_version for '{project}' is {current}, caller "
                    f"expected {expected_version}; reload and re-match "
                    f"(do not replay computed attachments)"
                )
            self._conn.execute(
                "INSERT INTO capability_registry (project, registry_version, "
                "next_ordinal) VALUES (?, 0, 1) "
                "ON CONFLICT(project) DO NOTHING",
                (project,),
            )
            for row in rows:
                self._conn.execute(
                    "INSERT INTO capability_identity (project, bc_id, "
                    "first_seen_run, status, retired_reason, merged_into, "
                    "derived_from, fingerprint, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(project, bc_id) DO UPDATE SET "
                    "status=excluded.status, "
                    "retired_reason=excluded.retired_reason, "
                    "merged_into=excluded.merged_into, "
                    "derived_from=excluded.derived_from, "
                    "fingerprint=excluded.fingerprint, "
                    "updated_at=excluded.updated_at",
                    (
                        project,
                        row.bc_id,
                        row.first_seen_run,
                        row.status.value,
                        row.retired_reason.value if row.retired_reason else None,
                        row.merged_into,
                        row.derived_from,
                        row.fingerprint.model_dump_json(),
                        _now(),
                    ),
                )
                self._conn.execute(
                    "INSERT INTO capability_event (project, bc_id, actor, "
                    "operation, detail, created_at) VALUES (?,?,?,?,?,?)",
                    (project, row.bc_id, actor, operation, row.status.value, _now()),
                )
            self._conn.execute(
                "UPDATE capability_registry SET registry_version = ?, "
                "next_ordinal = MAX(next_ordinal, ?) WHERE project = ?",
                (expected_version + 1, _max_ordinal(rows) + 1, project),
            )
        return expected_version + 1

    def allocator(self, project: str) -> Callable[[], str]:
        row = self._conn.execute(
            "SELECT next_ordinal FROM capability_registry WHERE project = ?", (project,)
        ).fetchone()
        counter = (row[0] if row else 1) - 1

        def _allocate() -> str:
            nonlocal counter
            counter += 1
            return f"BC-{counter:03d}"

        return _allocate


def _max_ordinal(rows: Sequence[CapabilityIdentity]) -> int:
    """Highest numeric suffix in this batch. next_ordinal only ever moves
    forward (MAX in the UPDATE), so a retired id is never handed out again."""
    best = 0
    for r in rows:
        _, _, suffix = r.bc_id.partition("-")
        if suffix.isdigit():
            best = max(best, int(suffix))
    return best
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capability_store.py tests/test_board_schema.py tests/test_board_artifacts.py tests/test_board_tasks.py -v`
Expected: PASS — the new tests pass and the existing board suite is unaffected by the DDL addition. `test_board_schema.py` is the one that would catch a malformed table; run it deliberately, not incidentally.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/capability/store.py src/sdlc/board/schema.py src/sdlc/board/store.py tests/test_capability_store.py
git commit -m "feat(capability): board-backed identity store with optimistic concurrency (E-47a)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Corrections

**Files:**
- Create: `src/sdlc/capability/corrections.py`
- Test: `tests/test_capability_corrections.py`

**Interfaces:**
- Consumes: Task 1 contracts, `BoardIdentityStore` (Task 5)
- Produces:
  - `CorrectionOp` (Enum: `MERGE`, `SPLIT`, `REATTACH`)
  - `IdentityCorrection` (BaseModel: `operation`, `approved_by`, `reason`, `source_bc_id`, `target_bc_id`, `partition: list[str]`)
  - `apply_correction(store, project, correction) -> int` returning the new `registry_version`

- [ ] **Step 1: Write the failing test**

Create `tests/test_capability_corrections.py`:

```python
"""FR-913 audited identity corrections (E-47a)."""

import pytest

from sdlc.capability.corrections import (
    CorrectionOp,
    IdentityCorrection,
    apply_correction,
)
from sdlc.capability.models import (
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityStatus,
    RetiredReason,
    SignalTier,
)
from sdlc.capability.store import BoardIdentityStore
from sdlc.measurement import Measurement


@pytest.fixture()
def store(tmp_path):
    s = BoardIdentityStore(db=tmp_path / "board.sqlite3")
    yield s
    s.close()


def _fp(*contract) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier.CONTRACT: list(contract)}, collected=Measurement.measured(1.0)
    )


def _seed(store, *rows):
    store.apply("p", rows, expected_version=store.registry_version("p"))


def _identity(bc_id, fp, **kw):
    return CapabilityIdentity(bc_id=bc_id, project="p", first_seen_run="r0", fingerprint=fp, **kw)


def _by_id(store):
    return {r.bc_id: r for r in store.load("p")}


def _correction(op, source, target=None, partition=None):
    return IdentityCorrection(
        operation=op,
        approved_by="maks",
        reason="reviewed by hand",
        source_bc_id=source,
        target_bc_id=target,
        partition=partition or [],
    )


def test_merge_retires_the_source_into_the_target(store):
    _seed(
        store, _identity("BC-001", _fp("POST /a")), _identity("BC-002", _fp("POST /a", "POST /b"))
    )
    apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001", "BC-002"))
    rows = _by_id(store)
    assert rows["BC-001"].status is IdentityStatus.MERGED
    assert rows["BC-001"].merged_into == "BC-002"
    assert rows["BC-002"].status is IdentityStatus.ACTIVE


def test_merge_overwrites_the_survivors_fingerprint(store):
    # Without this the next assessment scores against stale data, misses
    # threshold again, and the human corrects the same thing every run.
    _seed(store, _identity("BC-001", _fp("POST /new")), _identity("BC-002", _fp("POST /old")))
    apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001", "BC-002"))
    assert _by_id(store)["BC-002"].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /new"]


def test_reattach_moves_the_fingerprint_onto_the_existing_id(store):
    _seed(
        store,
        _identity("BC-003", _fp("POST /login")),
        _identity("BC-012", _fp("POST /login", "POST /session")),
    )
    apply_correction(store, "p", _correction(CorrectionOp.REATTACH, "BC-012", "BC-003"))
    rows = _by_id(store)
    assert rows["BC-012"].status is IdentityStatus.MERGED
    assert rows["BC-012"].merged_into == "BC-003"
    assert rows["BC-003"].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /login", "POST /session"]


def test_split_mints_a_new_id_carrying_the_supplied_partition(store):
    _seed(store, _identity("BC-001", _fp("POST /a", "POST /b")))
    apply_correction(store, "p", _correction(CorrectionOp.SPLIT, "BC-001", partition=["POST /b"]))
    rows = _by_id(store)
    assert rows["BC-002"].derived_from == "BC-001"
    assert rows["BC-002"].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /b"]
    # The source keeps everything not moved out.
    assert rows["BC-001"].fingerprint.tiers[SignalTier.CONTRACT] == ["POST /a"]


def test_split_requires_a_partition(store):
    _seed(store, _identity("BC-001", _fp("POST /a")))
    with pytest.raises(ValueError, match="partition"):
        apply_correction(store, "p", _correction(CorrectionOp.SPLIT, "BC-001"))


def test_merge_requires_a_target(store):
    _seed(store, _identity("BC-001", _fp("POST /a")))
    with pytest.raises(ValueError, match="target_bc_id"):
        apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001"))


def test_correction_requires_an_approver_and_a_reason():
    with pytest.raises(ValueError, match="approved_by"):
        IdentityCorrection(
            operation=CorrectionOp.MERGE,
            approved_by="  ",
            reason="r",
            source_bc_id="BC-001",
            target_bc_id="BC-002",
        )
    with pytest.raises(ValueError, match="reason"):
        IdentityCorrection(
            operation=CorrectionOp.MERGE,
            approved_by="maks",
            reason=" ",
            source_bc_id="BC-001",
            target_bc_id="BC-002",
        )


def test_merge_is_idempotent_by_target_state(store):
    _seed(store, _identity("BC-001", _fp("POST /a")), _identity("BC-002", _fp("POST /a")))
    c = _correction(CorrectionOp.MERGE, "BC-001", "BC-002")
    first = apply_correction(store, "p", c)
    second = apply_correction(store, "p", c)
    assert second == first  # no-op: version does not move
    assert _by_id(store)["BC-001"].merged_into == "BC-002"


def test_unknown_source_raises(store):
    with pytest.raises(ValueError, match="BC-404"):
        apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-404", "BC-001"))


def test_correction_bumps_the_registry_version(store):
    _seed(store, _identity("BC-001", _fp("POST /a")), _identity("BC-002", _fp("POST /a")))
    before = store.registry_version("p")
    apply_correction(store, "p", _correction(CorrectionOp.MERGE, "BC-001", "BC-002"))
    assert store.registry_version("p") == before + 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capability_corrections.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.capability.corrections'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/capability/corrections.py`:

```python
"""FR-913 (E-47a): audited identity corrections.

Modelled field-for-field on gate.py's GateOverride -- approved_by, reason,
and the operation. `approved_by` is retained as a calibration signal, the
same role it plays for a gate override: every correction is labelled ground
truth saying the matcher scored a pair at X and a human disagreed.

Application follows E-78's pattern (FR-1302): mutate the row, append one
event with actor and operation. A purely event-sourced fold would be more
elegant; a second persistence model inside one SQLite file would be worse.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .models import (
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityStatus,
    SignalTier,
)
from .store import CapabilityIdentityStore


class CorrectionOp(str, Enum):
    MERGE = "merge"  # two ids are one capability
    SPLIT = "split"  # one id should have been two
    REATTACH = "reattach"  # a new id is really an existing capability


class IdentityCorrection(BaseModel):
    operation: CorrectionOp
    approved_by: str
    reason: str
    source_bc_id: str
    target_bc_id: str | None = None
    # SPLIT only: the members moving to the new id. Richer input than the
    # other two operations need, because no scored evidence exists for a
    # partition the matcher did not make.
    partition: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _audited(self) -> "IdentityCorrection":
        if not self.approved_by.strip():
            raise ValueError(
                "approved_by is required -- an unattributed override is not an audited one"
            )
        if not self.reason.strip():
            raise ValueError("reason is required")
        return self


def apply_correction(
    store: CapabilityIdentityStore, project: str, correction: IdentityCorrection
) -> int:
    """Apply one correction. Returns the resulting registry_version.

    Idempotent by TARGET-STATE check, not by dedupe key: humans retry CLI
    invocations in ways Temporal activities do not, so re-issuing a
    correction that already holds is a no-op returning the current version.
    """
    version = store.registry_version(project)
    rows = {r.bc_id: r for r in store.load(project)}

    source = rows.get(correction.source_bc_id)
    if source is None:
        raise ValueError(f"unknown capability '{correction.source_bc_id}' in project '{project}'")

    if correction.operation is CorrectionOp.SPLIT:
        changed = _split(source, correction, store.allocator(project))
    else:
        changed = _absorb(source, correction, rows)

    if changed is None:  # already in the target state
        return version

    return store.apply(
        project,
        changed,
        expected_version=version,
        actor=correction.approved_by,
        operation=correction.operation.value,
    )


def _absorb(
    source: CapabilityIdentity, correction: IdentityCorrection, rows: dict[str, CapabilityIdentity]
) -> list[CapabilityIdentity] | None:
    """MERGE and REATTACH are the same write: the source is absorbed into the
    target, and the target inherits the source's fingerprint.

    Inheriting the fingerprint is what makes the correction stick. Point the
    ids at each other without it and the next assessment scores the
    refactored capability against the target's stale fingerprint, misses
    threshold again, and mints another new id.
    """
    if correction.target_bc_id is None:
        raise ValueError(f"operation={correction.operation.value} requires target_bc_id")
    target = rows.get(correction.target_bc_id)
    if target is None:
        raise ValueError(f"unknown capability '{correction.target_bc_id}'")

    if source.status is IdentityStatus.MERGED and source.merged_into == target.bc_id:
        return None

    absorbed = source.model_copy(
        update={
            "status": IdentityStatus.MERGED,
            "retired_reason": None,
            "merged_into": target.bc_id,
        }
    )
    survivor = target.model_copy(update={"fingerprint": source.fingerprint})
    return [absorbed, survivor]


def _split(
    source: CapabilityIdentity, correction: IdentityCorrection, allocate
) -> list[CapabilityIdentity]:
    """Move the named members onto a freshly minted id. Members are matched
    across every tier, so a caller need not say which tier each belongs to."""
    if not correction.partition:
        raise ValueError("operation=split requires a non-empty partition")

    moving = set(correction.partition)
    kept: dict[SignalTier, list[str]] = {}
    taken: dict[SignalTier, list[str]] = {}
    for tier in SignalTier:
        members = source.fingerprint.tiers.get(tier, [])
        kept[tier] = [m for m in members if m not in moving]
        taken[tier] = [m for m in members if m in moving]

    if not any(taken.values()):
        raise ValueError(
            f"partition {sorted(moving)} matched no member of {source.bc_id}; nothing to split out"
        )

    new_id = allocate()
    minted = CapabilityIdentity(
        bc_id=new_id,
        project=source.project,
        first_seen_run=source.first_seen_run,
        status=IdentityStatus.ACTIVE,
        derived_from=source.bc_id,
        fingerprint=CapabilityFingerprint(tiers=taken, collected=source.fingerprint.collected),
    )
    remaining = source.model_copy(
        update={
            "fingerprint": CapabilityFingerprint(tiers=kept, collected=source.fingerprint.collected)
        }
    )
    return [remaining, minted]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capability_corrections.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/capability/corrections.py tests/test_capability_corrections.py
git commit -m "feat(capability): audited merge/split/reattach corrections (E-47a)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Hash-only export

**Files:**
- Create: `src/sdlc/capability/export.py`
- Test: `tests/test_capability_export.py`

**Interfaces:**
- Consumes: `CapabilityIdentity` (Task 1)
- Produces: `fingerprint_sha256(fp) -> str`, `build_export(project, rows) -> dict`, `write_export(path, project, rows) -> str` (returns the written path)

- [ ] **Step 1: Write the failing test**

Create `tests/test_capability_export.py`:

```python
"""FR-913 client-facing identity export (E-47a)."""

import json

from sdlc.capability.export import (
    build_export,
    fingerprint_sha256,
    write_export,
)
from sdlc.capability.models import (
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityStatus,
    RetiredReason,
    SignalTier,
)
from sdlc.measurement import Measurement


def _fp(*contract) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier.CONTRACT: list(contract)}, collected=Measurement.measured(1.0)
    )


def _identity(bc_id, fp, **kw):
    return CapabilityIdentity(bc_id=bc_id, project="p", first_seen_run="r0", fingerprint=fp, **kw)


def test_hash_is_stable_across_member_order():
    assert fingerprint_sha256(_fp("POST /a", "POST /b")) == fingerprint_sha256(
        _fp("POST /b", "POST /a")
    )


def test_hash_changes_when_a_member_changes():
    assert fingerprint_sha256(_fp("POST /a")) != fingerprint_sha256(_fp("POST /b"))


def test_export_carries_no_raw_fingerprint_members():
    payload = build_export("p", [_identity("BC-001", _fp("POST /secret"))])
    assert "POST /secret" not in json.dumps(payload)


def test_export_entries_are_sorted_by_bc_id():
    payload = build_export(
        "p", [_identity("BC-002", _fp("POST /b")), _identity("BC-001", _fp("POST /a"))]
    )
    assert [e["bc_id"] for e in payload["capabilities"]] == ["BC-001", "BC-002"]


def test_export_records_status_and_merge_target():
    payload = build_export(
        "p",
        [_identity("BC-001", _fp("POST /a"), status=IdentityStatus.MERGED, merged_into="BC-002")],
    )
    entry = payload["capabilities"][0]
    assert entry["status"] == "merged" and entry["merged_into"] == "BC-002"


def test_retired_entries_are_exported_so_delivered_refs_resolve():
    payload = build_export(
        "p",
        [
            _identity(
                "BC-001",
                _fp("POST /a"),
                status=IdentityStatus.RETIRED,
                retired_reason=RetiredReason.NOT_OBSERVED,
            )
        ],
    )
    assert payload["capabilities"][0]["status"] == "retired"


def test_write_export_is_deterministic(tmp_path):
    rows = [_identity("BC-001", _fp("POST /a"))]
    first = tmp_path / "one.json"
    second = tmp_path / "two.json"
    write_export(first, "p", rows)
    write_export(second, "p", rows)
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_write_export_creates_parent_directories(tmp_path):
    target = tmp_path / ".sdlc" / "capabilities.json"
    write_export(target, "p", [_identity("BC-001", _fp("POST /a"))])
    assert json.loads(target.read_text(encoding="utf-8"))["project"] == "p"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capability_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.capability.export'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/capability/export.py`:

```python
"""FR-913 (E-47a): the client-facing identity export.

NOT a store. A hash cannot drive matching -- Jaccard needs the sets, and a
digest yields equality and nothing else -- so this file has no read path and
the board stays authoritative. It has three jobs:

  1. durable resolution of a delivered BC-NNN without our infrastructure;
  2. tamper-evidence -- the hash lets a client verify across engagements
     that the stored fingerprint is the one present at delivery;
  3. cheap change detection -- a differing hash means the shape moved.

Opt-in and off by default: writing into a client repository is a
trust-boundary decision, the same framing triage/advisories.py uses for an
outbound lookup.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from pathlib import Path

from .models import CapabilityFingerprint, CapabilityIdentity, SignalTier

EXPORT_VERSION = 1


def fingerprint_sha256(fp: CapabilityFingerprint) -> str:
    """Stable digest over the canonical tier members. The model validator
    already sorted and deduped them, so equal observations hash equal
    regardless of discovery order."""
    canonical = json.dumps(
        {t.value: fp.tiers.get(t, []) for t in SignalTier}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_export(project: str, rows: Sequence[CapabilityIdentity]) -> dict:
    """The payload. Retired and merged rows are included deliberately: a
    delivered document citing them must still resolve."""
    return {
        "version": EXPORT_VERSION,
        "project": project,
        "capabilities": [
            {
                "bc_id": r.bc_id,
                "status": r.status.value,
                "retired_reason": (r.retired_reason.value if r.retired_reason else None),
                "merged_into": r.merged_into,
                "derived_from": r.derived_from,
                "fingerprint_sha256": fingerprint_sha256(r.fingerprint),
            }
            for r in sorted(rows, key=lambda r: r.bc_id)
        ],
    }


def write_export(path: str | os.PathLike, project: str, rows: Sequence[CapabilityIdentity]) -> str:
    """Write the export, creating parents. Deterministic bytes: identical
    input yields an identical file, so a no-change assessment produces no
    diff in the client's repository."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(build_export(project, rows), indent=2, sort_keys=False, ensure_ascii=False)
    target.write_text(body + "\n", encoding="utf-8")
    return str(target)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capability_export.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/capability/export.py tests/test_capability_export.py
git commit -m "feat(capability): hash-only client-facing identity export (E-47a)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: CLI correction verbs

**Files:**
- Modify: `src/sdlc/cli.py` (add parser at the subcommand block near line 165; add dispatch near line 285; add `"capability"` to the local-only predicate at line 52-55)
- Test: `tests/test_capability_cli.py`

**Interfaces:**
- Consumes: `CorrectionOp`, `IdentityCorrection`, `apply_correction` (Task 6); `BoardIdentityStore` (Task 5); `write_export` (Task 7)
- Produces: `add_capability_parser(sub)` and `run_capability(args) -> int`, both importable for test

- [ ] **Step 1: Write the failing test**

Create `tests/test_capability_cli.py`:

```python
"""FR-913 identity correction CLI (E-47a)."""

import argparse
import json

import pytest

from sdlc.capability.cli import add_capability_parser, run_capability
from sdlc.capability.models import (
    CapabilityFingerprint,
    CapabilityIdentity,
    IdentityStatus,
    SignalTier,
)
from sdlc.capability.store import BoardIdentityStore
from sdlc.measurement import Measurement


def _fp(*contract) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier.CONTRACT: list(contract)}, collected=Measurement.measured(1.0)
    )


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "board.sqlite3"
    s = BoardIdentityStore(db=path)
    s.apply(
        "p",
        [
            CapabilityIdentity(
                bc_id="BC-001", project="p", first_seen_run="r0", fingerprint=_fp("POST /a")
            ),
            CapabilityIdentity(
                bc_id="BC-002", project="p", first_seen_run="r0", fingerprint=_fp("POST /b")
            ),
        ],
        expected_version=0,
    )
    s.close()
    return path


def _parse(argv):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    add_capability_parser(sub)
    return p.parse_args(argv)


def test_merge_applies_and_reports_success(db, capsys):
    args = _parse(
        [
            "capability",
            "merge",
            "--project",
            "p",
            "--from",
            "BC-001",
            "--into",
            "BC-002",
            "--reason",
            "same thing",
            "--by",
            "maks",
            "--db",
            str(db),
        ]
    )
    assert run_capability(args) == 0
    assert "BC-001" in capsys.readouterr().out
    store = BoardIdentityStore(db=db)
    rows = {r.bc_id: r for r in store.load("p")}
    store.close()
    assert rows["BC-001"].status is IdentityStatus.MERGED


def test_reattach_applies(db):
    args = _parse(
        [
            "capability",
            "reattach",
            "--project",
            "p",
            "--from",
            "BC-002",
            "--into",
            "BC-001",
            "--reason",
            "refactor",
            "--by",
            "maks",
            "--db",
            str(db),
        ]
    )
    assert run_capability(args) == 0


def test_split_requires_members(db):
    args = _parse(
        [
            "capability",
            "split",
            "--project",
            "p",
            "--from",
            "BC-001",
            "--reason",
            "two things",
            "--by",
            "maks",
            "--db",
            str(db),
        ]
    )
    assert run_capability(args) == 2


def test_split_with_members_applies(db):
    seeded = BoardIdentityStore(db=db)
    seeded.apply(
        "p",
        [
            CapabilityIdentity(
                bc_id="BC-001",
                project="p",
                first_seen_run="r0",
                fingerprint=_fp("POST /a", "POST /a2"),
            )
        ],
        expected_version=seeded.registry_version("p"),
    )
    seeded.close()
    args = _parse(
        [
            "capability",
            "split",
            "--project",
            "p",
            "--from",
            "BC-001",
            "--member",
            "POST /a2",
            "--reason",
            "two things",
            "--by",
            "maks",
            "--db",
            str(db),
        ]
    )
    assert run_capability(args) == 0


def test_unknown_capability_exits_nonzero_with_a_message(db, capsys):
    args = _parse(
        [
            "capability",
            "merge",
            "--project",
            "p",
            "--from",
            "BC-404",
            "--into",
            "BC-001",
            "--reason",
            "x",
            "--by",
            "maks",
            "--db",
            str(db),
        ]
    )
    assert run_capability(args) == 2
    assert "BC-404" in capsys.readouterr().err


def test_list_prints_every_id_including_retired(db, capsys):
    args = _parse(["capability", "list", "--project", "p", "--db", str(db)])
    assert run_capability(args) == 0
    out = capsys.readouterr().out
    assert "BC-001" in out and "BC-002" in out


def test_export_writes_a_hash_only_file(db, tmp_path, capsys):
    target = tmp_path / ".sdlc" / "capabilities.json"
    args = _parse(["capability", "export", "--project", "p", "--out", str(target), "--db", str(db)])
    assert run_capability(args) == 0
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["capabilities"][0]["fingerprint_sha256"]
    assert "POST /a" not in target.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_capability_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.capability.cli'`

- [ ] **Step 3: Write minimal implementation**

Create `src/sdlc/capability/cli.py`:

```python
"""FR-913 (E-47a): the human entry point for identity corrections.

CLI, not HTTP, and that is a constraint rather than a convenience. A
correction rewrites identity that delivered client documents cite -- the
highest-trust write in this design -- and the board API serves
unauthenticated with a self-asserted X-Actor header (OQ-11). An
unauthenticated header cannot provide provenance for approved_by on an
audited override. Exposing these verbs over HTTP becomes reasonable when
OQ-11 closes, not before.

Lives beside cli approve/reject/revise in vocabulary: --by is the approver,
--reason is retained as calibration signal.
"""

from __future__ import annotations

import sys

from .corrections import CorrectionOp, IdentityCorrection, apply_correction
from .export import write_export
from .store import BoardIdentityStore, IdentityStoreError

_ABSORB = ("merge", "reattach")


def add_capability_parser(sub) -> None:
    cap = sub.add_parser("capability")
    capsub = cap.add_subparsers(dest="cap_cmd", required=True)

    for name in _ABSORB:
        c = capsub.add_parser(name)
        c.add_argument("--project", required=True)
        c.add_argument("--from", dest="source", required=True)
        c.add_argument("--into", dest="target", required=True)
        c.add_argument("--reason", required=True)
        c.add_argument("--by", required=True, help="approver identity")
        c.add_argument("--db", default=None)

    s = capsub.add_parser("split")
    s.add_argument("--project", required=True)
    s.add_argument("--from", dest="source", required=True)
    s.add_argument(
        "--member",
        action="append",
        default=[],
        help="fingerprint member moving to the new id; repeatable",
    )
    s.add_argument("--reason", required=True)
    s.add_argument("--by", required=True, help="approver identity")
    s.add_argument("--db", default=None)

    ls = capsub.add_parser("list")
    ls.add_argument("--project", required=True)
    ls.add_argument("--db", default=None)

    ex = capsub.add_parser("export")
    ex.add_argument("--project", required=True)
    ex.add_argument("--out", required=True)
    ex.add_argument("--db", default=None)


def run_capability(args) -> int:
    store = BoardIdentityStore(db=args.db)
    try:
        if args.cap_cmd == "list":
            for row in store.load(args.project):
                suffix = f" -> {row.merged_into}" if row.merged_into else ""
                print(f"{row.bc_id}  {row.status.value}{suffix}")
            return 0

        if args.cap_cmd == "export":
            path = write_export(args.out, args.project, store.load(args.project))
            print(f"wrote {path}")
            return 0

        correction = IdentityCorrection(
            operation=CorrectionOp(args.cap_cmd),
            approved_by=args.by,
            reason=args.reason,
            source_bc_id=args.source,
            target_bc_id=getattr(args, "target", None),
            partition=list(getattr(args, "member", [])),
        )
        version = apply_correction(store, args.project, correction)
        print(f"{args.cap_cmd}: {args.source} -> registry_version {version}")
        return 0
    except (ValueError, IdentityStoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()
```

Then wire it into `src/sdlc/cli.py`. Add the import near the other local imports inside `main()`, register the parser beside the `calibrate` parser (around line 165):

```python
from .capability.cli import add_capability_parser

add_capability_parser(sub)
```

Add the dispatch beside the other `args.cmd ==` blocks (around line 285), before the Temporal client is needed:

```python
if args.cmd == "capability":
    from .capability.cli import run_capability

    raise SystemExit(run_capability(args))
```

And add `"capability"` to the local-only predicate so the CLI does not try to reach Temporal (line 52-55):

```python
        args.cmd == "benchmark"
        or (args.cmd == "schedules" and args.sched_cmd == "list")
        or (args.cmd == "eval" and args.target != "capture")
        or args.cmd == "calibrate"
        or args.cmd == "capability")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_capability_cli.py -v`
Expected: PASS (7 tests)

Then confirm the CLI parses end to end:

Run: `python -m sdlc.cli capability list --project p --db /tmp/nonexistent.sqlite3`
Expected: exit 0, no output (empty registry), no Temporal connection attempted.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/capability/cli.py src/sdlc/cli.py tests/test_capability_cli.py
git commit -m "feat(capability): CLI correction verbs, gated off HTTP by OQ-11 (E-47a)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Mechanical refactor corpus

**Files:**
- Create: `tests/test_capability_refactor_corpus.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4
- Produces: nothing importable — this is the calibration harness for `T_MATCH` and `DEFAULT_TIER_WEIGHTS`

This task has no implementation step. It is the test that decides whether the weighting from Task 2 is defensible, and it generates ground truth mechanically because SC-8's corpus of real audited repositories does not exist yet.

- [ ] **Step 1: Write the corpus test**

Create `tests/test_capability_refactor_corpus.py`:

```python
"""FR-913 mechanical refactor corpus (E-47a).

Ground truth generated rather than hand-labelled: apply a KNOWN refactor to a
fingerprint and assert identity survives (or does not). This is what
calibrates T_MATCH and DEFAULT_TIER_WEIGHTS before the first client
repository, and it directly falsifies the Contract-tier weighting claim -- if
renaming every symbol broke identity while changing one route did not, the
weighting would be wrong.
"""

import itertools

import pytest

from sdlc.capability.matcher import resolve
from sdlc.capability.models import (
    CapabilityFingerprint,
    CapabilityIdentity,
    ProposedCapability,
    SignalTier,
)
from sdlc.measurement import Measurement

BASE = {
    SignalTier.CONTRACT: ["POST /auth/login", "POST /auth/logout", "table:users", "table:sessions"],
    SignalTier.BEHAVIORAL: [
        "test_login_succeeds",
        "test_logout_clears",
        "entity:User",
        "entity:Session",
    ],
    SignalTier.STRUCTURAL: ["AuthService", "SessionStore", "TokenCodec"],
    SignalTier.LOCATIONAL: ["src/auth/service.py", "src/auth/session.py"],
}


def _fp(tiers) -> CapabilityFingerprint:
    return CapabilityFingerprint(tiers=dict(tiers), collected=Measurement.measured(1.0))


def _mutate(**overrides):
    tiers = dict(BASE)
    tiers.update(overrides)
    return _fp(tiers)


def _resolves_to_same_id(after: CapabilityFingerprint) -> bool:
    stored = CapabilityIdentity(
        bc_id="BC-001", project="p", first_seen_run="r0", fingerprint=_fp(BASE)
    )
    counter = itertools.count(900)
    result = resolve(
        [ProposedCapability(local_key="c0", fingerprint=after)],
        [stored],
        allocate=lambda: f"BC-{next(counter)}",
    )
    return result.attachments[0].bc_id == "BC-001"


# --- refactors identity MUST survive ------------------------------------

SURVIVES = {
    "move_every_file": {
        SignalTier.LOCATIONAL: ["pkg/identity/svc.py", "pkg/identity/sess.py"],
    },
    "rename_every_symbol": {
        SignalTier.STRUCTURAL: ["IdentityService", "SessionRepository", "JwtCodec"],
    },
    "move_and_rename_together": {
        SignalTier.STRUCTURAL: ["IdentityService", "SessionRepository", "JwtCodec"],
        SignalTier.LOCATIONAL: ["pkg/identity/svc.py", "pkg/identity/sess.py"],
    },
    "extract_a_module": {
        SignalTier.STRUCTURAL: [
            "AuthService",
            "SessionStore",
            "TokenCodec",
            "TokenRotation",
            "ClockSkew",
        ],
        SignalTier.LOCATIONAL: [
            "src/auth/service.py",
            "src/auth/session.py",
            "src/auth/rotation.py",
        ],
    },
    "add_one_endpoint": {
        SignalTier.CONTRACT: [
            "POST /auth/login",
            "POST /auth/logout",
            "POST /auth/refresh",
            "table:users",
            "table:sessions",
        ],
    },
    "rename_a_test": {
        SignalTier.BEHAVIORAL: [
            "test_login_returns_token",
            "test_logout_clears",
            "entity:User",
            "entity:Session",
        ],
    },
}


@pytest.mark.parametrize("name", sorted(SURVIVES))
def test_identity_survives_internal_refactor(name):
    assert _resolves_to_same_id(_mutate(**SURVIVES[name])), (
        f"{name} broke identity; the tier weighting is not doing its job"
    )


# --- changes identity MUST NOT survive ----------------------------------

BREAKS = {
    "different_capability_entirely": {
        SignalTier.CONTRACT: ["GET /reports/monthly", "table:invoices"],
        SignalTier.BEHAVIORAL: ["test_monthly_totals", "entity:Invoice"],
        SignalTier.STRUCTURAL: ["ReportBuilder", "InvoiceQuery"],
        SignalTier.LOCATIONAL: ["src/reports/monthly.py"],
    },
    "whole_contract_replaced_and_internals_too": {
        SignalTier.CONTRACT: ["POST /v2/identity", "table:principals"],
        SignalTier.BEHAVIORAL: ["test_principal_created", "entity:Principal"],
        SignalTier.STRUCTURAL: ["PrincipalService"],
        SignalTier.LOCATIONAL: ["src/principal/service.py"],
    },
}


@pytest.mark.parametrize("name", sorted(BREAKS))
def test_unrelated_capability_does_not_inherit_the_id(name):
    assert not _resolves_to_same_id(_mutate(**BREAKS[name])), (
        f"{name} wrongly inherited BC-001; T_MATCH is too permissive"
    )


def test_contract_tier_outweighs_all_internal_tiers_combined():
    """The Section 2 claim, stated as an executable assertion: preserving the
    contract while changing every internal signal must beat changing the
    contract while preserving every internal signal."""
    internals_changed = _mutate(
        **{
            SignalTier.STRUCTURAL: ["Xx", "Yy", "Zz"],
            SignalTier.LOCATIONAL: ["a/b.py", "c/d.py"],
            SignalTier.BEHAVIORAL: ["test_q", "test_r", "entity:Q", "entity:R"],
        }
    )
    contract_changed = _mutate(
        **{
            SignalTier.CONTRACT: ["GET /other", "table:other"],
        }
    )
    assert _resolves_to_same_id(internals_changed)
    assert not _resolves_to_same_id(contract_changed)
```

- [ ] **Step 2: Run the corpus**

Run: `python -m pytest tests/test_capability_refactor_corpus.py -v`
Expected: PASS (9 tests).

If any `SURVIVES` case fails, `T_MATCH` is too strict or `DEFAULT_TIER_WEIGHTS` under-weights Contract. If any `BREAKS` case passes, `T_MATCH` is too permissive. **Tune the constants in `capability/models.py`, never the assertions** — the corpus is the specification of acceptable behavior, and editing it to match the implementation defeats its purpose. Record any constant change in the commit message with the case that forced it.

- [ ] **Step 3: Run the whole suite**

Run: `python -m pytest tests/ -q`
Expected: PASS — the fast unit suite, with no regressions in the ten `tests/test_board_*.py` files from Task 5's DDL addition.

Note the default `addopts` in `pyproject.toml` excludes `slow`, `temporal`, and `docker` markers. Nothing in E-47a carries those markers, so the default run covers all of it.

- [ ] **Step 4: Commit**

```bash
git add tests/test_capability_refactor_corpus.py
git commit -m "test(capability): mechanical refactor corpus calibrating T_MATCH (E-47a)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** Every section of the design maps to a task:

| Spec section | Task |
|---|---|
| Decision, invariants, data model | 1 |
| Signal tiers, scoring, renormalization | 2 |
| Assignment (greedy, not Hungarian), tie-breaking | 3 |
| Thresholds, ε band, split/merge/retire/revive, `not_collected` discipline | 4 |
| Storage ABC, `BoardIdentityStore`, DDL, concurrency | 5 |
| Corrections, fingerprint overwrite, idempotency, calibration | 6 |
| Hash-only export, three jobs, determinism | 7 |
| CLI entry, OQ-11 dependency, `AUTHORITATIVE`-only | 8 |
| Testing: matcher tables, refactor corpus, properties | 1-4, 9 |
| Failure modes | 4 (uncomputable, empty registry), 5 (unreachable store, concurrency), 7 (export has no read path) |

**Two spec items deliberately not implemented,** both recorded above with reasons: `capability/activities.py` (no workflow caller until E-45) and the FR-103 memo-key term (no E-46 memo key to amend yet; `apply()` returns the version so it is ready).

**Type consistency checked.** `CapabilityFingerprint.tiers` is `dict[SignalTier, list[str]]` in every task. `score()` returns `tuple[float, dict[SignalTier, float]] | None` in Tasks 2 and 4. `Pair(score, bc_id, local_key)` field order is identical in Tasks 3 and 4. `allocate: Callable[[], str]` matches `BoardIdentityStore.allocator()`'s return type. `apply(..., expected_version=...)` is keyword-only in Tasks 5, 6, and the fixtures of 8.

**One risk to watch during execution.** Task 4's `resolve()` is the largest single implementation step in the plan. If it does not come together in one pass, split it: land matching plus first-discovery first, then the split/merge/retire/revive detection helpers as a second commit. The tests are already grouped to allow that cut.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-08-e47a-capability-identity.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
