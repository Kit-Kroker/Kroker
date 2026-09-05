# E-48 Plan 3 — The Discover Judgment Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the DISCOVER phase its judgment layer — a `discover` proposer that disposes over code-computed candidates, byte-grounded reference verification with a citation-rate guard, clause D8's blueprint comparison, and clause D7's derived domain model — completing E-48's clauses D1–D8.

**Architecture:** Plan 2 shipped the deterministic spine as four separate functions (`baseline_dispositions` → `stamp` → `apply` → `build_map`) precisely so this plan could insert judgment without rewriting it. Three things go in: an optional `agents/discover/` role whose `t_discover` runs between context and `stamp`; a pure `discover/verify.py` plus a `verify_discover_refs` activity that resolves every `EvidenceRef` at the pinned commit and byte-verifies every quote before any disposition is applied; and two new derived map fields (`blueprint`, `domain_model`). The spine's signatures change only additively — every new parameter has a default, so plan 2's tests pass untouched.

**Tech Stack:** Python 3.14, Pydantic v2, pydantic-ai (`Agent` + `TemporalAgent`), Temporal (`temporalio`), pytest (`pytest -m temporal` for workflow e2e), PyYAML.

**Spec:** `docs/superpowers/specs/2026-08-15-e48-discover-proposers-design.md` — decisions DD1, DD7, DD8, DD11, DD12, DD13 and the Failure-modes and Testing tables. Read it alongside this plan; every task below argues from a numbered decision in it.

## Global Constraints

- **ADR-22 binds every line here.** The proposer receives a deterministically computed packet and returns a **disposition over items code already produced**. It never authors the artifact, mints an identifier, or names a file, id, or metric that was not in its input.
- **Package purity (DD2).** `src/sdlc/assessment/discover/` modules import Pydantic, `measurement.py`, `capability/models.py`, `assessment/scan/models.py` and each other — **never** `sdlc/models.py`, `sdlc/activities.py`, or `temporalio`. A dependency there would appear as a reviewable import.
- **`discover/` imports scan *rule* modules, never a signal** (E-47c D2). A signal is a producer with a memo key and a version; importing one makes this package part of that signal's hashed surface.
- **Counts are derived from rows, never assigned.** Every new contract with a count field validates it against the rows, following `CapabilityMap._counts_are_derived`.
- **Sorted-and-deduped is asserted, never repaired.** A producer emitting discovery order is an NFR-10 determinism bug; repairing it hides the bug.
- **`_unmeasured_carries_no_payload`.** A report that did not collect has no rows (FR-915).
- **Reason strings must not converge** (`activities.py:136`). "Nobody has written this yet", "we tried and could not", and "the model cited garbage" are three distinct claims and must read as three.
- **NFR-9: no execution of the assessed repository's code.** Every read in this plan is `git show sha:path` at the pinned commit.
- **Citation guard threshold:** `CITATION_GUARD_MAX_UNRESOLVED = 0.10`, mirroring `DEAD_GUARD_MAX_UNRESOLVED` in `discover/models.py:18`.
- **Quote profile:** `Profile.VERBATIM_BYTES` — never `EXTRACTED_TEXT`. In source code a quote glyph is content, not noise.
- Run the full unit suite with `pytest -q -m "not temporal"`; the workflow e2e with `pytest -q -m temporal`.

## Plan decisions

These are this plan's own calls, in the spec's numbering style. Where one reconciles two places in the codebase that disagree, that is said outright.

**P3-D1 — verification is its own pure module, and `stamp` gains one optional keyword.** DD8 items 4–5 need the tree, so they cannot live in `stamp`. But if `verify_refs` simply *deleted* a refused row, `stamp` would see a candidate with no disposition and stamp `dropped_missing` — collapsing "the model omitted this candidate" into "the model cited a file that does not exist". DD7 forbids exactly that convergence. So `verify_refs` returns the surviving proposal **plus** a refusal map, and `stamp` takes `refusals: Mapping[str, tuple[str, str]] = {}` and consults it first. The parameter defaults to empty, so plan 2's call sites and tests are unaffected.

**P3-D2 — the guard divides unresolved *references* by total *references*.** DD8 says "a fabrication rate of 0.10 over all references"; `build_map`'s plan-2 comment says "Plan 3 divides this [`dropped_dispositions`] by `total_references`". Those are different ratios and only one matches the decision text and E-47b's precedent (`unresolved / total`). This plan implements DD8's: `unresolved_references / total_references`. `dropped_dispositions` remains on the map as the audit record of refused verdicts, which is what it is good for. A zero denominator never trips the guard — no references emitted means nothing was fabricated.

**P3-D3 — `discover` joins `STAGE_ROLES`.** `test_research_is_a_stage_but_optional` establishes the pattern for an optional stage-gated role, and it is what supplies `PROMPT_SHAS["discover"]` and `STAGE_MODELS["discover"]` — the two terms DD10's memo key needs. Deriving them any other way would be a second registry.

**P3-D4 — the blueprint degrades inside the map.** A missing or unparseable `blueprints/apqc.yaml` sets `BlueprintComparison.collected` to `not_collected` naming the file; the rest of the map ships. This is the spec's Failure-modes row, and it is why the blueprint is a field on the map rather than a precondition of the phase.

**P3-D5 — `DomainModel` is derived from `assign()` and never re-judged (DD12).** When `OwnershipReport.collected` is not MEASURED, the domain model reports `not_collected` naming ownership rather than shipping an empty entity table — an empty table would claim the repository has no entities.

**P3-D6 — `blueprint.py` does its own name normalization and does not import `naming.py`.** Importing it would be legal under DD2 (it is a rule module, and E-47c already imports it), but `test_scan_rules_sha` pins the coupling between `naming.py` and the six `_NAMING` signals' memo keys — so curating a blueprint would move six scan signal keys. Blueprint matching is not a scan rule, and it must not be hashed as one.

---

## File Structure

| File | Responsibility | New? |
|---|---|---|
| `agents/discover/agent.yaml` | role kind + model | create |
| `agents/discover/instructions.md` | the proposer's prompt, hashed into `PROMPT_SHAS` | create |
| `agents/discover/agent.py` | `build()` returning an `Agent` with `output_type=DiscoverProposal` | create |
| `src/sdlc/agents/loader.py` | `OPTIONAL_ROLES` gains `"discover"` | modify |
| `src/sdlc/agents/roles.py` | `STAGE_ROLES` entry, `discover_agent`, `t_discover`, `ALL_TEMPORAL_AGENTS` | modify |
| `src/sdlc/assessment/discover/verify.py` | DD8 items 4–5, pure: refs → refusals + counts | create |
| `src/sdlc/assessment/discover/apply.py` | `stamp(refusals=…)`; `build_map(total_references=, blueprint=, domain_model=)` | modify |
| `src/sdlc/assessment/discover/map.py` | `BlueprintGap`, `BlueprintComparison`, `DomainModel`, `DomainEntity`, `CapabilityMap` fields, `CITATION_GUARD_MAX_UNRESOLVED` | modify |
| `src/sdlc/assessment/discover/blueprint.py` | DD11 loader + comparison | create |
| `src/sdlc/assessment/discover/domain.py` | DD12 derivation from `OwnershipReport` | create |
| `blueprints/apqc.yaml` | the one reference blueprint, APQC PCF levels 1–2 | create |
| `src/sdlc/assessment/activities.py` | `verify_discover_refs`, `load_blueprint` activities | modify |
| `src/sdlc/worker.py` | register the two new activities | modify |
| `src/sdlc/workflows/assessment.py` | call the proposer, verify, guard, blueprint, domain model | modify |
| `tests/test_discover_verify.py` | Task 2 | create |
| `tests/test_discover_verify_activity.py` | Task 3 | create |
| `tests/test_discover_guard.py` | Task 4 | create |
| `tests/test_discover_blueprint.py` | Task 5 | create |
| `tests/test_discover_domain.py` | Task 6 | create |
| `tests/test_discover_role.py` | Task 1 | create |
| `tests/test_assessment_workflow_e2e.py` | Task 7 — extend | modify |

---

## Task 1: The `discover` role folder

**Files:**
- Create: `agents/discover/agent.yaml`, `agents/discover/instructions.md`, `agents/discover/agent.py`
- Modify: `src/sdlc/agents/loader.py:59` (`OPTIONAL_ROLES`)
- Modify: `src/sdlc/agents/roles.py` (`STAGE_ROLES`, agent construction, `t_discover`, `ALL_TEMPORAL_AGENTS`)
- Test: `tests/test_discover_role.py`

**Interfaces:**
- Consumes: `DiscoverProposal` from `sdlc.assessment.discover.map` (exists, plan 1).
- Produces: `roles.t_discover: TemporalAgent | None`; `roles.PROMPT_SHAS["discover"]`; `roles.STAGE_MODELS["discover"]`. Task 7 reads all three.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_role.py
"""E-48 DD7/P3-D3: the discover proposer is an OPTIONAL, KNOWN role."""

from sdlc.agents import loader, roles


def test_discover_is_optional_not_required():
    """An assessment-only agent must not fail boot on a feature-only
    deployment -- DD7's reason for OPTIONAL_ROLES over PROPOSER_ROLES."""
    assert "discover" in loader.OPTIONAL_ROLES
    assert "discover" not in loader.PROPOSER_ROLES
    assert "discover" not in loader.REQUIRED_ROLES


def test_discover_is_a_known_directory():
    """KNOWN_ROLES gates RECOGNITION: the unknown-directory check must keep
    biting on agents/discover/."""
    assert "discover" in loader.KNOWN_ROLES


def test_discover_is_a_stage_with_a_model_and_a_prompt_sha():
    """P3-D3: DD10's memo key reads both from here rather than from a second
    registry."""
    assert roles.STAGE_ROLES["discover"] == "discover"
    assert roles.STAGE_MODELS["discover"] == roles.REGISTRY["discover"].model
    assert len(roles.PROMPT_SHAS["discover"]) == 64


def test_t_discover_is_built_and_registered():
    assert roles.t_discover is not None
    assert roles.t_discover in roles.ALL_TEMPORAL_AGENTS


def test_the_proposer_can_only_return_dispositions():
    """ADR-22 at the type: the output_type has one field and it is
    dispositions. A proposer that could return capabilities would author."""
    from sdlc.assessment.discover.map import DiscoverProposal

    assert set(DiscoverProposal.model_fields) == {"dispositions"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_role.py -v`
Expected: FAIL — `AssertionError` on `"discover" in loader.OPTIONAL_ROLES` (and a `KeyError`/`AttributeError` on the later cases).

- [ ] **Step 3: Create `agents/discover/agent.yaml`**

The model must not be the same family as `reviewer`'s only where ADR-6 applies (dev/reviewer); it does not apply here. Follow `agents/analyst/agent.yaml`'s shape.

```yaml
kind: discover
model: anthropic:claude-sonnet-4-5
```

- [ ] **Step 4: Create `agents/discover/instructions.md`**

```markdown
You are the discover proposer for a brownfield capability assessment.

You are given a packet of **candidate capabilities that code has already
computed** from a deterministic scan of a repository at a pinned commit. Each
candidate carries its name, the scan signals that produced it, its members
(routes, tables, entities, modules), its cohesion and coupling metrics, and any
security, sensitivity, testability and coverage records that join to it.

Your job is to return exactly one **disposition** per candidate. You judge; you
do not author.

## What you may return

For each candidate, one action:

- `confirm` — this is a real business capability as scoped.
- `split` — this candidate is two or more capabilities. Supply `partitions`,
  each naming a subset of **this candidate's own member values**.
- `merge` — this candidate is the same capability as another one in the packet.
  Supply `merge_into` with that candidate's id.
- `de_scope` — this is not a business capability. Delivery channels and
  deployment boundaries are not capabilities: an "api" or "services" or "utils"
  grouping is a layer, not a thing the business does.
- `flag` — you cannot decide, and a human should look.

Every disposition needs a `rationale`. An unexplained verdict is unreviewable.

## What you may not do

- You may not invent a candidate. Only candidate ids present in the packet.
- You may not invent a member. A `split` partitions the members you were given.
- You may not invent a metric, a file path, or a line number.
- You may not cite a file that is not in the packet. Every `EvidenceRef` you
  emit is resolved against the repository at the pinned commit before anything
  you said is applied, and any quote you supply is compared byte-for-byte
  against that file. A reference that does not resolve causes your verdict for
  that candidate to be discarded and replaced with `flag`. If too many of your
  references do not resolve, the entire phase is discarded.

Cite sparingly and exactly. One reference you are certain of is worth more than
five you are guessing at.

## How to judge

Cohesion is intra-capability reference density; coupling is the count of
references crossing the candidate's boundary. High cohesion with low coupling
is a well-formed capability. Low cohesion with high coupling suggests a split.
Two candidates with near-identical members suggest a merge.

A candidate supported only by naming rules (`s1_layer_name`, `s1_generic_name`)
is a layer until something else says otherwise.
```

- [ ] **Step 5: Create `agents/discover/agent.py`**

```python
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.assessment.discover.map import DiscoverProposal


def build(model: str, instructions: str, model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="discover_agent",  # Temporal activity name -- NEVER rename
        output_type=DiscoverProposal,
        model_settings=model_settings,
        system_prompt=instructions,
    )
```

- [ ] **Step 6: Add `"discover"` to `OPTIONAL_ROLES`**

In `src/sdlc/agents/loader.py:59`, extend the frozenset and its comment:

```python
# Roles the pipeline can run WITHOUT, but which are still known directories.
# 'research' is the first entry: research_enabled defaults False so the
# pipeline boots without running the stage, but agents/research/ is still a
# KNOWN directory so the unknown-directory check keeps biting. This EXTENDS
# the fail-closed check; it does not weaken it. 'discover' joins for the same
# reason at a different tier (E-48 DD7): it is an ASSESSMENT-only role, and
# making it required would fail boot on a feature-only deployment.
OPTIONAL_ROLES: frozenset[str] = frozenset(
    {"research", "deep_review", "handoff", "adversary", "discover"}
)
```

- [ ] **Step 7: Wire the role in `roles.py`**

Add the `STAGE_ROLES` entry beside the other optional ones:

```python
    "discover": "discover",             # optional; present iff the folder ships
```

Then build the agent and its `TemporalAgent` following `t_research`'s exact
pattern (the `discover_agent` name comes from `build_agents`, which the loader
already drives from the directory — check how `research_agent` is bound in this
module and mirror it):

```python
# Optional: the discover TemporalAgent exists iff agents/discover/ shipped and
# built cleanly. workflows/assessment.py guards the phase with
# `t_discover is not None`, feature.py's t_research pattern (DD7).
t_discover = (
    TemporalAgent(discover_agent, activity_config=AGENT_ACTIVITY_CONFIG)
    if discover_agent is not None
    else None
)
```

and append it to `ALL_TEMPORAL_AGENTS`:

```python
if t_discover is not None:
    ALL_TEMPORAL_AGENTS.append(t_discover)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_discover_role.py tests/test_stage_models.py tests/test_prompt_migration.py -v`
Expected: PASS. If `test_prompt_migration.py` pins an exact set of stages, add `discover` to its expected set — a new optional stage is the same event `research` was.

- [ ] **Step 9: Run the boot-level registry tests**

Run: `pytest -q -m "not temporal" -k "registry or roles or agents"`
Expected: PASS. The unknown-directory check must now recognise `agents/discover/` rather than fail boot on it.

- [ ] **Step 10: Commit**

```bash
git add agents/discover src/sdlc/agents/loader.py src/sdlc/agents/roles.py tests/test_discover_role.py
git commit -m "feat(discover): the proposer role, optional and known (E-48 DD7)"
```

---

## Task 2: DD8 items 4–5 — reference verification, pure

**Files:**
- Create: `src/sdlc/assessment/discover/verify.py`
- Modify: `src/sdlc/assessment/discover/apply.py` (`stamp` gains `refusals`)
- Modify: `src/sdlc/assessment/discover/map.py` (`CITATION_GUARD_MAX_UNRESOLVED`)
- Test: `tests/test_discover_verify.py`

**Interfaces:**
- Consumes: `DiscoverProposal`, `ProposedDisposition`, `EvidenceRef`, `DiscoverContext` (all exist).
- Produces:
  - `CITATION_GUARD_MAX_UNRESOLVED: float = 0.10` in `map.py`
  - `verify.RefVerification` — `proposal: DiscoverProposal`, `refusals: dict[str, tuple[str, str]]`, `total_references: int`, `unresolved_references: int`, and a derived `fabrication_rate` property
  - `verify.verify_refs(proposal: DiscoverProposal, blobs: Mapping[str, str | None]) -> RefVerification`
  - `apply.stamp(context, proposal, *, refusals: Mapping[str, tuple[str, str]] = {}) -> StampedProposal`

Task 3 calls `verify_refs` from an activity; Task 4 reads `total_references` and `unresolved_references`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_verify.py
"""E-48 DD8 items 4-5: every reference resolves, every quote byte-verifies,
and a violation drops the ITEM -- it does not fail the phase."""

from sdlc.assessment.discover.map import (
    DiscoverAction,
    DiscoverProposal,
    DispositionSource,
    EvidenceRef,
    ProposedDisposition,
)
from sdlc.assessment.discover.verify import verify_refs

SRC = "def charge(order_id):\n    return gateway.charge(order_id)\n"


def _proposal(*rows: ProposedDisposition) -> DiscoverProposal:
    return DiscoverProposal(dispositions=list(rows))


def _row(cid: str, **kw) -> ProposedDisposition:
    return ProposedDisposition(
        candidate_id=cid, action=DiscoverAction.CONFIRM, rationale="it is a capability", **kw
    )


def test_a_resolving_reference_survives():
    p = _proposal(_row("C1", evidence=(EvidenceRef(path="pay.py", lines="1-2"),)))
    out = verify_refs(p, {"pay.py": SRC})
    assert out.refusals == {}
    assert out.total_references == 1
    assert out.unresolved_references == 0
    assert len(out.proposal.dispositions) == 1


def test_a_fabricated_path_refuses_its_disposition():
    p = _proposal(_row("C1", evidence=(EvidenceRef(path="nope.py"),)))
    out = verify_refs(p, {"nope.py": None})
    rule, detail = out.refusals["C1"]
    assert rule == "dropped_ref_unresolved"
    assert "nope.py" in detail
    assert out.unresolved_references == 1
    # the refused row is gone from the surviving proposal
    assert out.proposal.dispositions == []


def test_a_line_range_outside_the_file_refuses_its_disposition():
    """DD8 item 4: the range must lie INSIDE the file. SRC has two lines."""
    p = _proposal(_row("C1", evidence=(EvidenceRef(path="pay.py", lines="1-9"),)))
    out = verify_refs(p, {"pay.py": SRC})
    assert out.refusals["C1"][0] == "dropped_ref_line_range"
    assert out.unresolved_references == 1


def test_an_empty_file_resolves_and_is_not_confused_with_a_missing_one():
    """read_committed_bytes returns "" for an empty file and None for an
    unresolved one -- truthiness must not collapse them."""
    p = _proposal(_row("C1", evidence=(EvidenceRef(path="empty.py"),)))
    out = verify_refs(p, {"empty.py": ""})
    assert out.refusals == {}
    assert out.unresolved_references == 0


def test_counts_are_over_references_not_dispositions():
    """P3-D2: the guard's denominator is references."""
    p = _proposal(
        _row(
            "C1",
            evidence=(
                EvidenceRef(path="pay.py", lines="1-2"),
                EvidenceRef(path="ghost.py"),
            ),
        )
    )
    out = verify_refs(p, {"pay.py": SRC, "ghost.py": None})
    assert out.total_references == 2
    assert out.unresolved_references == 1
    assert out.fabrication_rate == 0.5


def test_a_proposal_with_no_references_has_a_zero_rate_not_a_zero_division():
    out = verify_refs(_proposal(_row("C1")), {})
    assert out.total_references == 0
    assert out.fabrication_rate == 0.0


def test_one_bad_reference_does_not_refuse_a_different_candidate():
    """A violation drops the ITEM. Discover is a lens over many candidates."""
    p = _proposal(
        _row("C1", evidence=(EvidenceRef(path="ghost.py"),)),
        _row("C2", evidence=(EvidenceRef(path="pay.py", lines="1-2"),)),
    )
    out = verify_refs(p, {"ghost.py": None, "pay.py": SRC})
    assert set(out.refusals) == {"C1"}
    assert [d.candidate_id for d in out.proposal.dispositions] == ["C2"]


def test_verification_is_order_independent():
    """NFR-10: byte-identical across input order."""
    rows = [
        _row("C1", evidence=(EvidenceRef(path="pay.py", lines="1-2"),)),
        _row("C2", evidence=(EvidenceRef(path="ghost.py"),)),
        _row("C3"),
    ]
    blobs = {"pay.py": SRC, "ghost.py": None}
    a = verify_refs(_proposal(*rows), blobs)
    b = verify_refs(_proposal(*reversed(rows)), blobs)
    assert a.refusals == b.refusals
    assert a.total_references == b.total_references
    assert a.unresolved_references == b.unresolved_references
```

Add the quote half in the same file:

```python
def test_a_quote_that_byte_verifies_survives():
    p = _proposal(
        _row("C1", evidence=(EvidenceRef(path="pay.py", lines="1-2"),), quote="gateway.charge")
    )
    out = verify_refs(p, {"pay.py": SRC})
    assert out.refusals == {}


def test_a_quote_that_does_not_byte_verify_refuses_its_disposition():
    p = _proposal(
        _row("C1", evidence=(EvidenceRef(path="pay.py", lines="1-2"),), quote="gateway.refund")
    )
    out = verify_refs(p, {"pay.py": SRC})
    assert out.refusals["C1"][0] == "dropped_quote_unverified"
    assert out.unresolved_references == 1


def test_an_empty_quote_does_not_ground_trivially():
    """E-43 closed exactly this hole: "" in haystack is True."""
    p = _proposal(_row("C1", evidence=(EvidenceRef(path="pay.py", lines="1-2"),), quote="   "))
    out = verify_refs(p, {"pay.py": SRC})
    assert out.refusals["C1"][0] == "dropped_quote_empty"
```

The `quote` field does not exist on `ProposedDisposition` yet — Step 3 adds it.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_verify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.discover.verify'`.

- [ ] **Step 3: Add `quote` to `ProposedDisposition` and the guard constant**

In `src/sdlc/assessment/discover/map.py`, add one field to `ProposedDisposition`:

```python
    # DD8 item 5. Optional: a disposition may cite a location without quoting
    # it. When present it is byte-verified under VERBATIM_BYTES against the
    # FIRST evidence ref's file -- a quote with no reference has nothing to
    # verify against and is refused.
    quote: str = ""
```

Mirror it on `CandidateDisposition` (same field, same default) so a surviving
proposer verdict carries its quote onto the artifact, and extend
`_stamp_one`'s `CandidateDisposition(...)` construction in `apply.py` to pass
`quote=proposed.quote`.

Add the constant beside `GUARDRAIL_RULES` in `map.py`:

```python
# DD8's phase-level citation guard, mirroring E-47b's DEAD_GUARD_MAX_UNRESOLVED
# (discover/models.py:18) and set to the same value for the same reason: past
# this fabrication rate, too many references failed to resolve for the
# surviving ones to be evidence.
CITATION_GUARD_MAX_UNRESOLVED: float = 0.10
```

- [ ] **Step 4: Write `src/sdlc/assessment/discover/verify.py`**

```python
# src/sdlc/assessment/discover/verify.py
"""FR-913/FR-914 (E-48 DD8 items 4-5): references resolved, quotes verified.

Pure by design -- Pydantic, grounding.py and this package only. The blobs are
read by the `verify_discover_refs` ACTIVITY and passed in, exactly as
discover/context.py receives its inputs rather than reading the tree.

A violation drops the ITEM, never the phase (DD8). The phase-level guard lives
in the workflow, which is the only place that can turn a rate into a
not_collected PhaseResult.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from ...grounding import Profile, verify_quote
from .map import DiscoverProposal, EvidenceRef, ProposedDisposition


class RefVerification(BaseModel):
    """What survived, what was refused, and the guard's two terms.

    `refusals` is candidate_id -> (rule, detail) rather than a rewritten
    disposition: stamp() owns the disposition shape, and building one here
    would be a second producer of the same row (P3-D1).
    """

    proposal: DiscoverProposal
    refusals: dict[str, tuple[str, str]] = {}
    total_references: int = 0
    unresolved_references: int = 0

    @property
    def fabrication_rate(self) -> float:
        """Zero references is a zero rate, never a division. A proposer that
        cited nothing fabricated nothing -- it is unevidenced, which is a
        different complaint and not this guard's."""
        if self.total_references == 0:
            return 0.0
        return self.unresolved_references / self.total_references


def _line_span(text: str) -> int:
    """Lines in the file. A file with no trailing newline still has its last
    line, and "" is one empty line -- both match how a reader counts."""
    return len(text.splitlines()) or 1


def _range_refusal(ref: EvidenceRef, body: str) -> str:
    """ "" when the range lies inside the file. `lines` is "" for a whole-file
    reference, "42" for one line, "42-78" for a span."""
    if not ref.lines:
        return ""
    raw = ref.lines.split("-")
    try:
        start = int(raw[0])
        end = int(raw[-1])
    except ValueError:
        return "dropped_ref_line_range"
    if start < 1 or end < start or end > _line_span(body):
        return "dropped_ref_line_range"
    return ""


def _refuse(row: ProposedDisposition, blobs: Mapping[str, str | None]) -> tuple[str, str, int]:
    """(rule, detail, unresolved_count) for one disposition.

    ("", "", 0) means every reference resolved. The unresolved count is over
    REFERENCES (P3-D2), so a row citing three fabricated paths contributes
    three -- the guard measures citation quality, not row count.
    """
    unresolved = 0
    first_rule = ""
    first_detail = ""

    for ref in row.evidence:
        body = blobs.get(ref.path)
        # None is unresolved; "" is a resolved EMPTY file. Truthiness would
        # collapse them (read_committed_bytes' docstring states the rule).
        if body is None:
            unresolved += 1
            if not first_rule:
                first_rule = "dropped_ref_unresolved"
                first_detail = f"evidence path {ref.path!r} does not resolve at the pinned commit"
            continue
        refusal = _range_refusal(ref, body)
        if refusal:
            unresolved += 1
            if not first_rule:
                first_rule = refusal
                first_detail = (
                    f"evidence lines {ref.lines!r} lie outside {ref.path!r}, "
                    f"which has {_line_span(body)} line(s)"
                )

    if row.quote:
        if not row.quote.strip():
            unresolved += 1
            if not first_rule:
                first_rule = "dropped_quote_empty"
                first_detail = (
                    "the quote is blank, and an empty quote grounds trivially "
                    "against any file (E-43)"
                )
        elif not row.evidence:
            unresolved += 1
            if not first_rule:
                first_rule = "dropped_quote_unanchored"
                first_detail = (
                    "the quote names no evidence path, so there is nothing to verify it against"
                )
        else:
            body = blobs.get(row.evidence[0].path)
            if body is None or not verify_quote(row.quote, body, Profile.VERBATIM_BYTES):
                unresolved += 1
                if not first_rule:
                    first_rule = "dropped_quote_unverified"
                    first_detail = (
                        f"the quote does not byte-verify against "
                        f"{row.evidence[0].path!r} under VERBATIM_BYTES"
                    )

    return first_rule, first_detail, unresolved


def verify_refs(proposal: DiscoverProposal, blobs: Mapping[str, str | None]) -> RefVerification:
    """DD8 items 4-5 over every disposition.

    `blobs` maps every path the proposal cited to its bytes at the pinned
    commit, or None when it did not resolve. The caller reads them; this
    function decides.
    """
    survivors: list[ProposedDisposition] = []
    refusals: dict[str, tuple[str, str]] = {}
    total = 0
    unresolved_total = 0

    for row in proposal.dispositions:
        total += len(row.evidence)
        rule, detail, unresolved = _refuse(row, blobs)
        unresolved_total += unresolved
        if rule:
            # Last writer wins is fine: stamp() refuses a duplicated
            # candidate_id anyway, so two refusals for one id cannot both
            # reach the artifact.
            refusals[row.candidate_id] = (rule, detail)
        else:
            survivors.append(row)

    return RefVerification(
        proposal=DiscoverProposal(dispositions=survivors),
        refusals=refusals,
        total_references=total,
        unresolved_references=unresolved_total,
    )


def cited_paths(proposal: DiscoverProposal) -> tuple[str, ...]:
    """Every path the proposal cites, sorted and deduped -- the activity's
    read list. Sorted because the activity's git reads must not depend on
    disposition order (NFR-10)."""
    return tuple(sorted({ref.path for row in proposal.dispositions for ref in row.evidence}))
```

- [ ] **Step 5: Teach `stamp` about refusals**

In `src/sdlc/assessment/discover/apply.py`, change `_stamp_one` and `stamp`.
`_stamp_one` gains one parameter and one branch **at the top**, before the
missing-row check — a refused row was removed from the proposal, so without
this it would read as an omission (P3-D1):

```python
def _stamp_one(
    context: CandidateContext,
    rows: Sequence[ProposedDisposition],
    known: Mapping[str, CandidateContext],
    refusal: tuple[str, str] | None = None,
) -> CandidateDisposition:
    cid = context.candidate_id
    if refusal is not None:
        # DD8 items 4-5 already refused this verdict. Checked BEFORE the
        # empty-rows branch: verify_refs removed the row, so `rows` is empty
        # here, and dropped_missing would report an omission the proposer did
        # not commit (P3-D1).
        return _dropped(cid, refusal[0], refusal[1])
    if not rows:
        ...
```

and `stamp` gains the keyword and threads it through:

```python
def stamp(
    context: DiscoverContext,
    proposal: DiscoverProposal | None,
    *,
    refusals: Mapping[str, tuple[str, str]] = {},
) -> StampedProposal:
    """DD8 items 1-3 and DD7's two fallbacks.

    `refusals` carries DD8 items 4-5's verdicts from verify_refs, which runs
    in front of this function because it needs the tree. Defaulting to empty
    keeps plan 2's callers and tests unchanged (P3-D1).
    ...
    """
    if proposal is None:
        return StampedProposal(dispositions=baseline_dispositions(context))
    ...
    first = [
        _stamp_one(c, by_candidate.get(c.candidate_id, ()), known, refusals.get(c.candidate_id))
        for c in context.candidates
    ]
```

Delete the now-stale sentence in `stamp`'s docstring that says items 4 and 5
"land in plan 3's verify_discover_refs, in front of this function" and replace
it with the paragraph above — the seam it forward-declared now exists.

- [ ] **Step 6: Add the refusal-vs-omission test**

Append to `tests/test_discover_verify.py`:

```python
def test_a_refused_verdict_is_not_reported_as_an_omission():
    """P3-D1/DD7: "the model cited garbage" and "the model said nothing"
    must not converge on dropped_missing."""
    from sdlc.assessment.discover.apply import stamp

    context = _context_with(["C1"])  # see helper below
    p = _proposal(_row("C1", evidence=(EvidenceRef(path="ghost.py"),)))
    out = verify_refs(p, {"ghost.py": None})
    stamped = stamp(context, out.proposal, refusals=out.refusals)

    row = stamped.dispositions[0]
    assert row.action is DiscoverAction.FLAG
    assert row.source is DispositionSource.DROPPED
    assert row.rule == "dropped_ref_unresolved"
    assert row.rule != "dropped_missing"
```

Write `_context_with` using the real `build_context` output shape rather than a
hand-built struct wherever practical; if a minimal `DiscoverContext` is needed,
construct it through `CandidateContext` so its `guardrail_only` validator runs.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_discover_verify.py tests/test_discover_apply.py tests/test_discover_baseline.py -v`
Expected: PASS, including plan 2's untouched apply/baseline tests — the new keyword defaults to empty.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/assessment/discover/verify.py src/sdlc/assessment/discover/apply.py src/sdlc/assessment/discover/map.py tests/test_discover_verify.py
git commit -m "feat(discover): references resolved and quotes byte-verified (E-48 DD8)"
```

---

## Task 3: The `verify_discover_refs` activity

**Files:**
- Modify: `src/sdlc/assessment/activities.py`
- Modify: `src/sdlc/worker.py:38,138`
- Test: `tests/test_discover_verify_activity.py`

**Interfaces:**
- Consumes: `verify_refs`, `cited_paths` (Task 2); `read_committed_bytes`'s git-read approach in `src/sdlc/activities.py:917`.
- Produces: `VerifyRefsInput(repo_dir, commit_sha, proposal)` and `@activity.defn verify_discover_refs(inp) -> RefVerification`. Task 7 calls it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_verify_activity.py
"""E-48 DD8: the activity reads blobs at the pinned commit; the pure function
decides. NFR-9: git show only -- no checkout, no execution."""

import subprocess

import pytest

from sdlc.assessment.activities import VerifyRefsInput, verify_discover_refs
from sdlc.assessment.discover.map import (
    DiscoverAction,
    DiscoverProposal,
    EvidenceRef,
    ProposedDisposition,
)


@pytest.fixture
def repo(tmp_path):
    def run(*args):
        subprocess.run(args, cwd=tmp_path, check=True, capture_output=True)

    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "t")
    (tmp_path / "pay.py").write_text(
        "def charge(order_id):\n    return gateway.charge(order_id)\n", encoding="utf-8"
    )
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "seed")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    return str(tmp_path), sha


def _proposal(**kw):
    return DiscoverProposal(
        dispositions=[
            ProposedDisposition(
                candidate_id="C1", action=DiscoverAction.CONFIRM, rationale="r", **kw
            )
        ]
    )


@pytest.mark.asyncio
async def test_a_real_path_resolves_against_the_pinned_commit(repo):
    repo_dir, sha = repo
    out = await verify_discover_refs(
        VerifyRefsInput(
            repo_dir=repo_dir,
            commit_sha=sha,
            proposal=_proposal(evidence=(EvidenceRef(path="pay.py", lines="1-2"),)),
        )
    )
    assert out.refusals == {}
    assert out.total_references == 1


@pytest.mark.asyncio
async def test_a_fabricated_path_is_refused_by_the_activity(repo):
    repo_dir, sha = repo
    out = await verify_discover_refs(
        VerifyRefsInput(
            repo_dir=repo_dir,
            commit_sha=sha,
            proposal=_proposal(evidence=(EvidenceRef(path="ghost.py"),)),
        )
    )
    assert out.refusals["C1"][0] == "dropped_ref_unresolved"
    assert out.unresolved_references == 1


@pytest.mark.asyncio
async def test_a_directory_path_does_not_resolve_as_a_file(repo):
    """git show sha:dir returns a TREE LISTING with exit 0 -- which is not
    the file's bytes (read_committed_bytes code review #4)."""
    repo_dir, sha = repo
    out = await verify_discover_refs(
        VerifyRefsInput(
            repo_dir=repo_dir, commit_sha=sha, proposal=_proposal(evidence=(EvidenceRef(path="."),))
        )
    )
    assert out.refusals["C1"][0] == "dropped_ref_unresolved"


@pytest.mark.asyncio
async def test_a_quote_byte_verifies_against_the_committed_bytes(repo):
    repo_dir, sha = repo
    out = await verify_discover_refs(
        VerifyRefsInput(
            repo_dir=repo_dir,
            commit_sha=sha,
            proposal=_proposal(
                evidence=(EvidenceRef(path="pay.py", lines="1-2"),), quote="gateway.charge"
            ),
        )
    )
    assert out.refusals == {}


@pytest.mark.asyncio
async def test_an_unreadable_repo_refuses_every_reference_rather_than_raising(tmp_path):
    """Fail-closed means "unverified", not "crash" -- read_committed_bytes'
    rule. Every ref unresolved trips the guard upstream, which is correct."""
    out = await verify_discover_refs(
        VerifyRefsInput(
            repo_dir=str(tmp_path),
            commit_sha="0" * 40,
            proposal=_proposal(evidence=(EvidenceRef(path="pay.py"),)),
        )
    )
    assert out.unresolved_references == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_verify_activity.py -v`
Expected: FAIL — `ImportError: cannot import name 'VerifyRefsInput'`.

- [ ] **Step 3: Write the activity**

Append to `src/sdlc/assessment/activities.py`, beside `discover_context`. Read
`_source_blobs` / `_blobs_for` in the same module first and reuse the existing
`git show` helper rather than adding a second one; if neither fits a
"resolve-or-None per path" read, call `read_committed_bytes`'s underlying
helper. The behaviour that matters: **None for unresolved, `""` for empty, and
never raise.**

```python
class VerifyRefsInput(BaseModel):
    """DD8 items 4-5's inputs. The proposal travels whole rather than as a
    path list: the pure function needs the quotes too, and splitting them
    would put half the verification decision in the activity."""

    repo_dir: str
    commit_sha: str
    proposal: DiscoverProposal


@activity.defn
async def verify_discover_refs(inp: VerifyRefsInput) -> RefVerification:
    """E-48 DD8 items 4-5. The activity READS; verify.py DECIDES.

    NFR-9: `git show <sha>:<path>` at the pinned commit. No checkout, no
    worktree mutation, and none of the assessed repository's code runs.

    A path that does not resolve -- including one that resolves to a tree --
    yields None, which verify_refs counts as a fabricated reference. An
    unreadable repository therefore refuses every reference rather than
    raising: fail-closed means "unverified", not "crash", and the phase-level
    guard is what turns a mass refusal into a not_collected phase.
    """
    blobs: dict[str, str | None] = {
        path: _committed_blob(inp.repo_dir, inp.commit_sha, path)
        for path in cited_paths(inp.proposal)
    }
    return verify_refs(inp.proposal, blobs)
```

with `_committed_blob` a module-level helper that returns `str | None` and
swallows every `subprocess` error, guarding the tree case the way
`read_committed_bytes` does.

Add the imports at the top of the module:

```python
from .discover.map import DiscoverProposal
from .discover.verify import RefVerification, cited_paths, verify_refs
```

- [ ] **Step 4: Register the activity on the worker**

In `src/sdlc/worker.py`, add `verify_discover_refs` to both the import at
line 38 and the registration list at line 138, keeping both alphabetical.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_discover_verify_activity.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Prove the worker still boots**

Run: `pytest -q -m "not temporal" -k "worker or registration"`
Expected: PASS — an activity imported but not registered surfaces later as a
confusing unregistered-activity error, which is the failure mode
`test_board_workflow.py`'s note warns about.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/assessment/activities.py src/sdlc/worker.py tests/test_discover_verify_activity.py
git commit -m "feat(discover): verify_discover_refs reads the pinned commit (E-48 DD8)"
```

---

## Task 4: The citation guard and `total_references`

**Files:**
- Modify: `src/sdlc/assessment/discover/apply.py` (`build_map` gains `total_references`)
- Modify: `src/sdlc/assessment/discover/map.py` (`CapabilityMap` validator)
- Test: `tests/test_discover_guard.py`

**Interfaces:**
- Consumes: `CITATION_GUARD_MAX_UNRESOLVED`, `RefVerification.fabrication_rate` (Task 2).
- Produces: `build_map(..., total_references: int = 0)`; `map.guard_tripped(verification) -> str` returning a reason or `""`. Task 7 calls `guard_tripped` and turns a non-empty reason into `no_discover(...)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_guard.py
"""E-48 DD8: past a 0.10 fabrication rate, too many references failed to
resolve for the surviving ones to be evidence."""

from sdlc.assessment.discover.map import (
    CITATION_GUARD_MAX_UNRESOLVED,
    guard_tripped,
)
from sdlc.assessment.discover.verify import RefVerification
from sdlc.assessment.discover.map import DiscoverProposal


def _verification(total: int, unresolved: int) -> RefVerification:
    return RefVerification(
        proposal=DiscoverProposal(), total_references=total, unresolved_references=unresolved
    )


def test_the_threshold_matches_e47bs_dead_guard():
    """Same value for the same reason -- two guards that drift apart are two
    unexplained numbers."""
    from sdlc.assessment.discover.models import DEAD_GUARD_MAX_UNRESOLVED

    assert CITATION_GUARD_MAX_UNRESOLVED == DEAD_GUARD_MAX_UNRESOLVED


def test_a_clean_proposal_does_not_trip():
    assert guard_tripped(_verification(20, 0)) == ""


def test_exactly_at_the_threshold_does_not_trip():
    """PAST 0.10, not at it -- the boundary belongs to the passing side."""
    assert guard_tripped(_verification(20, 2)) == ""


def test_past_the_threshold_trips_and_names_both_terms():
    reason = guard_tripped(_verification(20, 3))
    assert reason != ""
    assert "3" in reason and "20" in reason


def test_no_references_never_trips():
    """P3-D2: a proposer that cited nothing fabricated nothing. Unevidenced is
    a different complaint and not this guard's."""
    assert guard_tripped(_verification(0, 0)) == ""


def test_total_references_reaches_the_map():
    ...
    # asserted against build_map in the same file -- see Step 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_guard.py -v`
Expected: FAIL — `ImportError: cannot import name 'guard_tripped'`.

- [ ] **Step 3: Implement the guard and thread `total_references`**

In `map.py`, beside the constant:

```python
def guard_tripped(verification: "RefVerification") -> str:
    """DD8's phase-level guard: the reason the phase must report
    not_collected, or "" when the proposal is usable.

    Deliberately returns a REASON rather than a bool. The workflow puts this
    string on the PhaseResult, and a bare True would leave the caller to
    reinvent the explanation -- which is how two reasons that must not
    converge start converging.
    """
    if verification.fabrication_rate <= CITATION_GUARD_MAX_UNRESOLVED:
        return ""
    return (
        f"the proposer's citation fabrication rate is "
        f"{verification.unresolved_references}/"
        f"{verification.total_references} = "
        f"{verification.fabrication_rate:.2f}, past the "
        f"{CITATION_GUARD_MAX_UNRESOLVED:.2f} guard -- too many "
        f"references failed to resolve for the surviving ones to be "
        f"evidence"
    )
```

Import `RefVerification` under `TYPE_CHECKING` to keep `map.py` free of a
runtime cycle (`verify.py` imports `map.py`).

In `apply.py`, `build_map` gains the parameter and passes it through:

```python
def build_map(applied: ApplyResult, bc_of: Mapping[str, str], *,
              advisories: Sequence[Advisory] = (),
              attribution: AttributionReport | None = None,
              decomposition: DecompositionReport | None = None,
              ownership: OwnershipReport | None = None,
              total_references: int = 0) -> CapabilityMap:
```

and in the `CapabilityMap(...)` construction:

```python
total_references = (total_references,)
```

Replace plan 2's stale comment above `dropped_dispositions` — it says plan 3
divides *that* by `total_references`, which is not the ratio DD8 specifies
(P3-D2):

```python
        # The audit record of refused verdicts: one verification dropped, plus
        # one naming a candidate that does not exist. NOT the guard's
        # numerator -- DD8 measures a fabrication rate over REFERENCES, and
        # guard_tripped() divides unresolved_references by total_references
        # (P3-D2).
```

Then append the map-level assertion to the test file:

```python
def test_total_references_reaches_the_map(discover_fixtures):
    """The number a customer would need to audit the guard's arithmetic must
    be on the artifact, not only in the workflow's history."""
    applied, bc_of = discover_fixtures  # reuse test_discover_map_build.py's
    cap_map = build_map(applied, bc_of, total_references=7)
    assert cap_map.total_references == 7
```

Build `discover_fixtures` from the same producers `tests/test_discover_map_build.py`
already uses — do not hand-build an `ApplyResult`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_discover_guard.py tests/test_discover_map_build.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/map.py src/sdlc/assessment/discover/apply.py tests/test_discover_guard.py
git commit -m "feat(discover): the citation guard, over references (E-48 DD8, P3-D2)"
```

---

## Task 5: Clause D8 — the blueprint comparison

**Files:**
- Create: `src/sdlc/assessment/discover/blueprint.py`
- Create: `blueprints/apqc.yaml`
- Modify: `src/sdlc/assessment/discover/map.py` (`BlueprintGap`, `BlueprintComparison`, `CapabilityMap.blueprint`)
- Modify: `src/sdlc/assessment/discover/apply.py` (`build_map(blueprint=)`)
- Modify: `src/sdlc/assessment/activities.py` + `src/sdlc/worker.py` (`load_blueprint`)
- Test: `tests/test_discover_blueprint.py`

**Interfaces:**
- Consumes: `Capability` (exists).
- Produces:
  - `BlueprintStatus` — `PRESENT | MISSING | EXTRA`
  - `BlueprintGap(name, status, level, parent, matched_bc_id)`
  - `BlueprintComparison(blueprint, version, gaps, counts, collected)`
  - `blueprint.compare(capabilities, processes) -> BlueprintComparison`
  - `blueprint.load(path) -> tuple[BlueprintProcess, ...] | None`
  - `@activity.defn load_blueprint(inp: BlueprintInput) -> BlueprintComparison`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_blueprint.py
"""E-48 DD11 (clause D8): MISSING is context, not failure."""

import pytest

from sdlc.assessment.discover.blueprint import (
    BlueprintProcess,
    compare,
    load,
)
from sdlc.assessment.discover.map import BlueprintStatus
from sdlc.measurement import CollectionState

PROCESSES = (
    BlueprintProcess(name="Manage Financial Resources", level=1, parent=""),
    BlueprintProcess(
        name="Process Customer Payments", level=2, parent="Manage Financial Resources"
    ),
    BlueprintProcess(name="Manage Human Capital", level=1, parent=""),
)


def _cap(bc_id: str, name: str):
    """Built through the real Capability constructor so its validators run."""
    from tests.helpers.discover import capability  # add if absent

    return capability(bc_id=bc_id, name=name)


def test_a_matching_capability_is_present():
    out = compare([_cap("BC-001", "customer payments")], PROCESSES)
    row = next(g for g in out.gaps if g.name == "Process Customer Payments")
    assert row.status is BlueprintStatus.PRESENT
    assert row.matched_bc_id == "BC-001"


def test_an_unmatched_blueprint_process_is_missing_and_that_is_context():
    out = compare([_cap("BC-001", "customer payments")], PROCESSES)
    row = next(g for g in out.gaps if g.name == "Manage Human Capital")
    assert row.status is BlueprintStatus.MISSING
    assert row.matched_bc_id is None
    # MISSING never degrades the comparison itself
    assert out.collected.state is CollectionState.MEASURED


def test_a_capability_matching_nothing_is_extra():
    out = compare([_cap("BC-009", "widget calibration")], PROCESSES)
    row = next(g for g in out.gaps if g.name == "widget calibration")
    assert row.status is BlueprintStatus.EXTRA
    assert row.matched_bc_id == "BC-009"


def test_counts_carry_every_status_including_zeros():
    out = compare([], PROCESSES)
    assert set(out.counts) == set(BlueprintStatus)
    assert out.counts[BlueprintStatus.EXTRA] == 0


def test_gaps_are_sorted_and_deduped():
    out = compare([_cap("BC-001", "customer payments")], PROCESSES)
    names = [(g.status.value, g.name) for g in out.gaps]
    assert names == sorted(names)


def test_comparison_is_order_independent():
    """NFR-10."""
    caps = [_cap("BC-001", "customer payments"), _cap("BC-002", "invoicing")]
    a = compare(caps, PROCESSES)
    b = compare(list(reversed(caps)), tuple(reversed(PROCESSES)))
    assert a.model_dump_json() == b.model_dump_json()


def test_a_missing_file_degrades_the_comparison_and_names_it(tmp_path):
    """P3-D4: the rest of the map still ships."""
    assert load(str(tmp_path / "nope.yaml")) is None


def test_an_unparseable_file_degrades_rather_than_raising(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("processes: [ unclosed", encoding="utf-8")
    assert load(str(bad)) is None


def test_the_shipped_apqc_blueprint_loads_and_has_two_levels():
    processes = load("blueprints/apqc.yaml")
    assert processes is not None
    assert {p.level for p in processes} == {1, 2}
    # every level-2 process names a level-1 parent that exists
    tops = {p.name for p in processes if p.level == 1}
    assert all(p.parent in tops for p in processes if p.level == 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_blueprint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.discover.blueprint'`.

- [ ] **Step 3: Add the contracts to `map.py`**

```python
class BlueprintStatus(str, Enum):
    """Clause D8. MISSING is CONTEXT, not failure: a repository that does not
    do what its industry normally does may be correct, incomplete, or out of
    scope, and this comparison cannot tell which."""

    PRESENT = "present"
    MISSING = "missing"
    EXTRA = "extra"


class BlueprintGap(BaseModel):
    model_config = {"frozen": True}
    name: str
    status: BlueprintStatus
    level: int = 0  # 0 for an EXTRA (no blueprint level)
    parent: str = ""
    matched_bc_id: str | None = None

    @model_validator(mode="after")
    def _a_match_names_its_capability(self) -> "BlueprintGap":
        matched = self.status in (BlueprintStatus.PRESENT, BlueprintStatus.EXTRA)
        if matched != (self.matched_bc_id is not None):
            raise ValueError(
                f"matched_bc_id is set IFF the status names a capability -- "
                f"got status={self.status.value} "
                f"matched_bc_id={self.matched_bc_id}. A MISSING row that "
                f"names a capability is not a weaker claim, it is two claims"
            )
        return self


class BlueprintComparison(BaseModel):
    """DD11's artifact. Degrades on its own (P3-D4) -- a missing or
    unparseable blueprint reports not_collected here and the rest of the map
    ships."""

    blueprint: str = ""
    version: str = ""
    gaps: tuple[BlueprintGap, ...] = ()
    counts: dict[BlueprintStatus, int] = Field(default_factory=dict)
    collected: Measurement

    @model_validator(mode="after")
    def _counts_are_derived(self) -> "BlueprintComparison":
        if self.collected.state is not CollectionState.MEASURED:
            return self
        missing = [s.value for s in BlueprintStatus if s not in self.counts]
        if missing:
            raise ValueError(
                f"counts must carry every status, including zeros (missing "
                f"{missing}) -- an absent key and a zero count are different "
                f"claims and only one of them is true"
            )
        for status in BlueprintStatus:
            actual = sum(1 for g in self.gaps if g.status is status)
            if self.counts[status] != actual:
                raise ValueError(
                    f"counts[{status.value}]={self.counts[status]} but "
                    f"{actual} row(s) carry it -- counts are derived from "
                    f"rows, never assigned"
                )
        return self

    @model_validator(mode="after")
    def _gaps_are_sorted(self) -> "BlueprintComparison":
        keys = [(g.status.value, g.name) for g in self.gaps]
        if keys != sorted(set(keys)):
            raise ValueError(
                f"gaps {keys} are not sorted and deduped -- comparison order "
                f"must not reach the artifact"
            )
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> "BlueprintComparison":
        if self.collected.state is not CollectionState.MEASURED and (self.gaps or self.counts):
            raise ValueError(
                f"collected={self.collected.state.value} carries no payload, "
                f"but rows are present -- a comparison that did not happen "
                f"has no gaps (FR-915)"
            )
        return self
```

Add the field to `CapabilityMap` and extend `_unmeasured_carries_no_payload`'s
condition to include `self.blueprint is not None`:

```python
    blueprint: BlueprintComparison | None = None
```

- [ ] **Step 4: Write `src/sdlc/assessment/discover/blueprint.py`**

```python
# src/sdlc/assessment/discover/blueprint.py
"""FR-913 (E-48 DD11, clause D8): the discovered set against a reference
blueprint. MISSING is context, not failure.

Pure by design. The one impurity is `load`, which reads a repo-root YAML file
the FACTORY ships -- not the assessed repository -- so it executes nothing and
is not part of NFR-9's surface.

P3-D6: normalization is local rather than imported from scan/naming.py.
Importing it would be legal, but test_scan_rules_sha pins naming.py to six
signals' memo keys, so curating a blueprint would move six scan signal keys.
Blueprint matching is not a scan rule and must not be hashed as one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from pathlib import Path

import yaml
from pydantic import BaseModel

from ...measurement import Measurement
from .map import (
    BlueprintComparison,
    BlueprintGap,
    BlueprintStatus,
    Capability,
)

DEFAULT_BLUEPRINT = "blueprints/apqc.yaml"

# Words that carry no discriminating power in a process name. Deliberately
# short: an aggressive stop list makes everything match everything, and a
# false PRESENT hides a real gap, which is the direction that costs.
_STOP = frozenset(
    {
        "and",
        "the",
        "of",
        "for",
        "to",
        "a",
        "an",
        "manage",
        "develop",
        "deliver",
        "process",
        "maintain",
        "perform",
    }
)
_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(name: str) -> frozenset[str]:
    """Lowercase alphanumeric tokens, stop words removed, trailing plural 's'
    stripped. English-centric, and OQ-12 already records that limitation for
    S5's normalization; the same caveat applies here."""
    raw = (t for t in _SPLIT.split(name.lower()) if t)
    return frozenset(t.rstrip("s") for t in raw if t not in _STOP) - {""}


class BlueprintProcess(BaseModel):
    model_config = {"frozen": True}
    name: str
    level: int
    parent: str = ""


class Blueprint(BaseModel):
    model_config = {"frozen": True}
    name: str
    version: str
    processes: tuple[BlueprintProcess, ...]


def load(path: str = DEFAULT_BLUEPRINT) -> Blueprint | None:
    """The blueprint, or None when the file is absent or will not parse.

    Returns None rather than raising (P3-D4): the caller reports
    not_collected naming the file, and the rest of the map ships.
    """
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return Blueprint(
            name=raw["name"],
            version=str(raw["version"]),
            processes=tuple(
                BlueprintProcess(name=p["name"], level=int(p["level"]), parent=p.get("parent", ""))
                for p in raw["processes"]
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _matches(cap_tokens: frozenset[str], proc_tokens: frozenset[str]) -> bool:
    """A match is a non-empty token intersection covering at least half the
    blueprint process's tokens. Half rather than all: "Process Customer
    Payments" should match a "customer payments" capability, and requiring
    every token would make the level-2 rows unmatchable in practice."""
    if not cap_tokens or not proc_tokens:
        return False
    shared = cap_tokens & proc_tokens
    return len(shared) * 2 >= len(proc_tokens)


def compare(
    capabilities: Iterable[Capability],
    processes: Sequence[BlueprintProcess],
    *,
    name: str = "",
    version: str = "",
) -> BlueprintComparison:
    """PRESENT / MISSING / EXTRA over the discovered set.

    A capability may satisfy more than one process (a level-1 row and its
    level-2 child); each process gets its own row, so the counts describe
    processes rather than capabilities.
    """
    caps = [(c, _tokens(c.name)) for c in capabilities]
    matched_bc_ids: set[str] = set()
    gaps: list[BlueprintGap] = []

    for proc in processes:
        proc_tokens = _tokens(proc.name)
        hit = next((c for c, toks in caps if _matches(toks, proc_tokens)), None)
        if hit is None:
            gaps.append(
                BlueprintGap(
                    name=proc.name,
                    status=BlueprintStatus.MISSING,
                    level=proc.level,
                    parent=proc.parent,
                )
            )
        else:
            matched_bc_ids.add(hit.bc_id)
            gaps.append(
                BlueprintGap(
                    name=proc.name,
                    status=BlueprintStatus.PRESENT,
                    level=proc.level,
                    parent=proc.parent,
                    matched_bc_id=hit.bc_id,
                )
            )

    for cap, _ in caps:
        if cap.bc_id not in matched_bc_ids:
            gaps.append(
                BlueprintGap(name=cap.name, status=BlueprintStatus.EXTRA, matched_bc_id=cap.bc_id)
            )

    ordered = tuple(sorted(gaps, key=lambda g: (g.status.value, g.name)))
    return BlueprintComparison(
        blueprint=name,
        version=version,
        gaps=ordered,
        counts={s: sum(1 for g in ordered if g.status is s) for s in BlueprintStatus},
        collected=Measurement.measured(float(len(ordered))),
    )


def not_compared(reason: str) -> BlueprintComparison:
    """P3-D4's degraded row, named for what it is."""
    return BlueprintComparison(collected=Measurement.not_collected(reason))
```

- [ ] **Step 5: Create `blueprints/apqc.yaml`**

APQC's cross-industry Process Classification Framework, trimmed to its top two
levels (DD11). Flat-file at the repo root, matching `schedules/`' convention.

```yaml
# APQC Process Classification Framework (cross-industry), levels 1-2.
# E-48 DD11's ONE reference blueprint. MISSING is context, not failure.
# The remaining six (BIAN, TM Forum, ACORD, HL7, ARTS) are curation work with
# their own item -- see the E-48 spec's Scope section.
name: APQC PCF (cross-industry)
version: "7.2"
processes:
  - {name: Develop Vision and Strategy, level: 1}
  - {name: Define the Business Concept and Long-Term Vision, level: 2, parent: Develop Vision and Strategy}
  - {name: Develop Business Strategy, level: 2, parent: Develop Vision and Strategy}

  - {name: Develop and Manage Products and Services, level: 1}
  - {name: Manage Product and Service Portfolio, level: 2, parent: Develop and Manage Products and Services}
  - {name: Develop Products and Services, level: 2, parent: Develop and Manage Products and Services}

  - {name: Market and Sell Products and Services, level: 1}
  - {name: Understand Markets Customers and Capabilities, level: 2, parent: Market and Sell Products and Services}
  - {name: Develop Marketing Strategy, level: 2, parent: Market and Sell Products and Services}
  - {name: Develop and Manage Sales Plans, level: 2, parent: Market and Sell Products and Services}

  - {name: Deliver Physical Products, level: 1}
  - {name: Plan for and Acquire Necessary Resources, level: 2, parent: Deliver Physical Products}
  - {name: Manage Logistics and Warehousing, level: 2, parent: Deliver Physical Products}

  - {name: Deliver Services, level: 1}
  - {name: Establish Service Delivery Governance, level: 2, parent: Deliver Services}
  - {name: Deliver Service to Customer, level: 2, parent: Deliver Services}

  - {name: Manage Customer Service, level: 1}
  - {name: Develop Customer Care Strategy, level: 2, parent: Manage Customer Service}
  - {name: Manage Customer Service Requests and Inquiries, level: 2, parent: Manage Customer Service}
  - {name: Manage Customer Complaints, level: 2, parent: Manage Customer Service}

  - {name: Develop and Manage Human Capital, level: 1}
  - {name: Recruit Source and Select Employees, level: 2, parent: Develop and Manage Human Capital}
  - {name: Manage Employee Information and Analytics, level: 2, parent: Develop and Manage Human Capital}

  - {name: Manage Information Technology, level: 1}
  - {name: Develop and Manage IT Customer Relationships, level: 2, parent: Manage Information Technology}
  - {name: Develop and Manage IT Solutions, level: 2, parent: Manage Information Technology}
  - {name: Deploy Information Technology Solutions, level: 2, parent: Manage Information Technology}
  - {name: Manage Information Technology Knowledge, level: 2, parent: Manage Information Technology}

  - {name: Manage Financial Resources, level: 1}
  - {name: Perform Planning and Management Accounting, level: 2, parent: Manage Financial Resources}
  - {name: Perform Revenue Accounting, level: 2, parent: Manage Financial Resources}
  - {name: Process Customer Payments, level: 2, parent: Manage Financial Resources}
  - {name: Manage Treasury Operations, level: 2, parent: Manage Financial Resources}

  - {name: Acquire Construct and Manage Assets, level: 1}
  - {name: Plan and Acquire Assets, level: 2, parent: Acquire Construct and Manage Assets}
  - {name: Maintain Assets, level: 2, parent: Acquire Construct and Manage Assets}

  - {name: Manage Enterprise Risk Compliance Remediation and Resiliency, level: 1}
  - {name: Manage Enterprise Risk, level: 2, parent: Manage Enterprise Risk Compliance Remediation and Resiliency}
  - {name: Manage Compliance, level: 2, parent: Manage Enterprise Risk Compliance Remediation and Resiliency}
  - {name: Manage Business Resiliency, level: 2, parent: Manage Enterprise Risk Compliance Remediation and Resiliency}

  - {name: Manage External Relationships, level: 1}
  - {name: Build Investor Relationships, level: 2, parent: Manage External Relationships}
  - {name: Manage Government and Industry Relationships, level: 2, parent: Manage External Relationships}

  - {name: Develop and Manage Business Capabilities, level: 1}
  - {name: Manage Business Processes, level: 2, parent: Develop and Manage Business Capabilities}
  - {name: Manage Knowledge and Change, level: 2, parent: Develop and Manage Business Capabilities}
  - {name: Measure and Benchmark, level: 2, parent: Develop and Manage Business Capabilities}
```

- [ ] **Step 6: Add the `load_blueprint` activity**

`load` touches the filesystem, so the workflow reaches it through an activity.
Append to `src/sdlc/assessment/activities.py`:

```python
class BlueprintInput(BaseModel):
    capabilities: list[Capability] = Field(default_factory=list)
    path: str = DEFAULT_BLUEPRINT


@activity.defn
async def load_blueprint(inp: BlueprintInput) -> BlueprintComparison:
    """DD11 (clause D8). Reads a FACTORY-shipped YAML file, never the assessed
    repository -- so this adds nothing to NFR-9's surface.

    A missing or unparseable file degrades the comparison and names it
    (P3-D4); the rest of the map ships.
    """
    loaded = load(inp.path)
    if loaded is None:
        return not_compared(f"the blueprint {inp.path!r} is missing or did not parse")
    return compare(inp.capabilities, loaded.processes, name=loaded.name, version=loaded.version)
```

Register it in `src/sdlc/worker.py` alongside `verify_discover_refs`.

- [ ] **Step 7: Thread `blueprint` through `build_map`**

```python
              ownership: OwnershipReport | None = None,
              total_references: int = 0,
              blueprint: BlueprintComparison | None = None) -> CapabilityMap:
```

and pass `blueprint=blueprint` in the construction. Update `build_map`'s
docstring — it currently says plan 3 adds `domain_model` and `blueprint`
"when their producers exist"; they now do.

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_discover_blueprint.py tests/test_discover_map_build.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/assessment/discover/blueprint.py blueprints/apqc.yaml src/sdlc/assessment/discover/map.py src/sdlc/assessment/discover/apply.py src/sdlc/assessment/activities.py src/sdlc/worker.py tests/test_discover_blueprint.py
git commit -m "feat(discover): clause D8, one blueprint and MISSING as context (E-48 DD11)"
```

---

## Task 6: Clause D7 — the derived domain model

**Files:**
- Create: `src/sdlc/assessment/discover/domain.py`
- Modify: `src/sdlc/assessment/discover/map.py` (`DomainEntity`, `DomainModel`, `CapabilityMap.domain_model`)
- Modify: `src/sdlc/assessment/discover/apply.py` (`build_map(domain_model=)`)
- Test: `tests/test_discover_domain.py`

**Interfaces:**
- Consumes: `OwnershipReport`, `EntityOwnership`, `OwnershipOutcome` from `discover/models.py`; `Capability`.
- Produces: `DomainModel`, `DomainEntity`, `domain.consolidate(ownership, capabilities) -> DomainModel`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_domain.py
"""E-48 DD12 (clause D7): derived from assign(), never re-judged."""

from sdlc.assessment.discover.domain import consolidate
from sdlc.assessment.discover.models import (
    EntityOwnership,
    OwnershipOutcome,
    OwnershipReport,
)
from sdlc.measurement import CollectionState, Measurement


def _report(*rows: EntityOwnership) -> OwnershipReport:
    return OwnershipReport(
        entities=rows,
        counts={o: sum(1 for r in rows if r.outcome is o) for o in OwnershipOutcome},
        collected=Measurement.measured(float(len(rows))),
    )


def test_an_owned_entity_carries_its_owner_and_verb():
    from sdlc.assessment.discover.models import OwnershipVerb

    rep = _report(
        EntityOwnership(
            entity="orders",
            outcome=OwnershipOutcome.OWNED,
            owner="BC-001",
            verb=OwnershipVerb.OWNS,
            rule="declaration",
            claimants=("BC-001",),
        )
    )
    out = consolidate(rep, [])
    row = out.entities[0]
    assert row.entity == "orders"
    assert row.owner == "BC-001"
    assert row.outcome is OwnershipOutcome.OWNED


def test_the_three_unowned_outcomes_stay_distinct():
    """E-47c kept CONFLICT / UNDIRECTED / UNCLAIMED apart precisely so a
    CLI-written table is never reported as untouched. D7 must not
    re-collapse them."""
    rep = _report(
        EntityOwnership(
            entity="a",
            outcome=OwnershipOutcome.CONFLICT,
            rule="tie",
            claimants=("BC-001", "BC-002"),
        ),
        EntityOwnership(
            entity="b", outcome=OwnershipOutcome.UNDIRECTED, rule="reads", claimants=("BC-001",)
        ),
        EntityOwnership(entity="c", outcome=OwnershipOutcome.UNCLAIMED, rule="none"),
    )
    out = consolidate(rep, [])
    got = {e.entity: e.outcome for e in out.entities}
    assert got == {
        "a": OwnershipOutcome.CONFLICT,
        "b": OwnershipOutcome.UNDIRECTED,
        "c": OwnershipOutcome.UNCLAIMED,
    }


def test_readers_are_carried_from_claimants_minus_the_owner():
    from sdlc.assessment.discover.models import OwnershipVerb

    rep = _report(
        EntityOwnership(
            entity="orders",
            outcome=OwnershipOutcome.OWNED,
            owner="BC-001",
            verb=OwnershipVerb.OWNS,
            rule="declaration",
            claimants=("BC-001", "BC-002"),
        )
    )
    out = consolidate(rep, [])
    assert out.entities[0].readers == ("BC-002",)


def test_a_degraded_ownership_report_yields_a_not_collected_domain_model():
    """P3-D5: an empty entity table would claim the repository has no
    entities."""
    rep = OwnershipReport(
        counts={o: 0 for o in OwnershipOutcome},
        collected=Measurement.not_collected("S2 did not collect"),
    )
    out = consolidate(rep, [])
    assert out.collected.state is CollectionState.NOT_COLLECTED
    assert "S2" in out.collected.reason
    assert out.entities == ()


def test_entities_are_sorted():
    rep = _report(
        EntityOwnership(entity="zebra", outcome=OwnershipOutcome.UNCLAIMED, rule="none"),
        EntityOwnership(entity="apple", outcome=OwnershipOutcome.UNCLAIMED, rule="none"),
    )
    out = consolidate(rep, [])
    assert [e.entity for e in out.entities] == ["apple", "zebra"]


def test_consolidation_is_order_independent():
    """NFR-10."""
    rows = (
        EntityOwnership(entity="a", outcome=OwnershipOutcome.UNCLAIMED, rule="none"),
        EntityOwnership(entity="b", outcome=OwnershipOutcome.UNCLAIMED, rule="none"),
    )
    assert (
        consolidate(_report(*rows), []).model_dump_json()
        == consolidate(_report(*reversed(rows)), []).model_dump_json()
    )


def test_no_ownership_row_is_authored_here():
    """DD12: the model's standing to override a conflict is exercised through
    a disposition on the CAPABILITY, not by editing this table. So
    consolidate() must be a pure projection -- same row count in, same out."""
    rep = _report(
        EntityOwnership(
            entity="a",
            outcome=OwnershipOutcome.CONFLICT,
            rule="tie",
            claimants=("BC-001", "BC-002"),
        )
    )
    assert len(consolidate(rep, []).entities) == len(rep.entities)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_domain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.discover.domain'`.

- [ ] **Step 3: Add the contracts to `map.py`**

```python
class DomainEntity(BaseModel):
    """One entity in the consolidated domain model (clause D7). A projection
    of EntityOwnership -- never a second judgment of it (DD12)."""

    model_config = {"frozen": True}
    entity: str
    outcome: OwnershipOutcome
    owner: str | None = None
    verb: OwnershipVerb | None = None
    readers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _readers_are_sorted(self) -> "DomainEntity":
        if list(self.readers) != sorted(set(self.readers)):
            raise ValueError(
                f"readers {self.readers} are not sorted and deduped -- "
                f"discovery order must not reach the artifact"
            )
        return self


class DomainModel(BaseModel):
    """DD12's artifact: entities, their owner where one resolved, the
    capabilities that read them, and the three unowned outcomes surfaced as
    E-47c left them."""

    entities: tuple[DomainEntity, ...] = ()
    counts: dict[OwnershipOutcome, int] = Field(default_factory=dict)
    collected: Measurement

    @model_validator(mode="after")
    def _counts_are_derived(self) -> "DomainModel":
        if self.collected.state is not CollectionState.MEASURED:
            return self
        missing = [o.value for o in OwnershipOutcome if o not in self.counts]
        if missing:
            raise ValueError(
                f"counts must carry every outcome, including zeros (missing "
                f"{missing}) -- an absent key and a zero count are different "
                f"claims and only one of them is true"
            )
        for outcome in OwnershipOutcome:
            actual = sum(1 for e in self.entities if e.outcome is outcome)
            if self.counts[outcome] != actual:
                raise ValueError(
                    f"counts[{outcome.value}]={self.counts[outcome]} but "
                    f"{actual} entit(ies) carry it -- counts are derived from "
                    f"entities, never assigned"
                )
        return self

    @model_validator(mode="after")
    def _entities_are_sorted(self) -> "DomainModel":
        names = [e.entity for e in self.entities]
        if names != sorted(set(names)):
            raise ValueError(f"entities {names} are not sorted and deduped")
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> "DomainModel":
        if self.collected.state is not CollectionState.MEASURED and (self.entities or self.counts):
            raise ValueError(
                f"collected={self.collected.state.value} carries no payload, "
                f"but rows are present -- a domain model that did not happen "
                f"has no entities (FR-915)"
            )
        return self
```

Add `domain_model: DomainModel | None = None` to `CapabilityMap` and include it
in that class's `_unmeasured_carries_no_payload` condition.

- [ ] **Step 4: Write `src/sdlc/assessment/discover/domain.py`**

```python
# src/sdlc/assessment/discover/domain.py
"""FR-913 (E-48 DD12, clause D7): the consolidated domain model.

DERIVED from assign()'s OwnershipReport, never re-judged. The proposer's
standing to override a conflict is exercised through a disposition on the
CAPABILITY -- which changes the member set assign() runs over -- not by
editing this table.

Pure by design.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...measurement import CollectionState, Measurement
from .map import Capability, DomainEntity, DomainModel
from .models import OwnershipOutcome, OwnershipReport


def consolidate(ownership: OwnershipReport, capabilities: Iterable[Capability]) -> DomainModel:
    """One DomainEntity per ownership row, sorted by entity name.

    `capabilities` is accepted and currently unused for row construction: it
    is the set the bc_ids resolve against, and E-52's reports join on it. It
    stays in the signature rather than being added later because a consumer
    that has to re-derive the join is how two joins that must agree start
    disagreeing.
    """
    if ownership.collected.state is not CollectionState.MEASURED:
        # P3-D5. An empty table would claim the repository has no entities,
        # which is the FR-915 conflation this codebase refuses everywhere
        # else.
        return DomainModel(
            collected=Measurement.not_collected(
                f"ownership did not collect: {ownership.collected.reason}"
            )
        )

    rows = tuple(
        sorted(
            (
                DomainEntity(
                    entity=e.entity,
                    outcome=e.outcome,
                    owner=e.owner,
                    verb=e.verb,
                    # The owner is not its own reader. Sorted here because
                    # EntityOwnership.claimants is already sorted and set difference
                    # is not order-preserving.
                    readers=tuple(
                        sorted(set(e.claimants) - {e.owner} if e.owner else set(e.claimants))
                    ),
                )
                for e in ownership.entities
            ),
            key=lambda d: d.entity,
        )
    )

    return DomainModel(
        entities=rows,
        counts={o: sum(1 for r in rows if r.outcome is o) for o in OwnershipOutcome},
        collected=Measurement.measured(float(len(rows))),
    )
```

- [ ] **Step 5: Thread `domain_model` through `build_map`**

Add the keyword (default `None`) and pass it into the `CapabilityMap`
construction, as Task 5 did for `blueprint`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_discover_domain.py tests/test_discover_map_build.py tests/test_discover_seam.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/assessment/discover/domain.py src/sdlc/assessment/discover/map.py src/sdlc/assessment/discover/apply.py tests/test_discover_domain.py
git commit -m "feat(discover): clause D7, derived from assign() and not re-judged (E-48 DD12)"
```

---

## Task 7: Wire the judgment layer into `_discover`

**Files:**
- Modify: `src/sdlc/workflows/assessment.py:227-336`
- Test: `tests/test_assessment_workflow_e2e.py` (extend)

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: a DISCOVER phase that runs the proposer when `t_discover` is not
  None, verifies its references, trips the guard, and carries `blueprint` +
  `domain_model` onto the map.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assessment_workflow_e2e.py`, following the existing
`test_discover_goes_measured_and_the_map_reaches_the_artifact` fixture setup
exactly — same worker, same activity list plus the two new ones.

```python
# --- E-48 plan 3: the judgment layer ---------------------------------------


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_a_proposer_verdict_reaches_the_map(assessment_repo):
    """DD1/DD7: the model disposes, code stamps provenance. A CONFIRM from
    the proposer must land with source=proposer, not source=baseline."""
    ...  # TestModel returning DiscoverProposal with one CONFIRM for the
    # candidate build_context produced, citing a path that EXISTS in the
    # seeded repo.
    cap_map = result.discover
    row = cap_map.dispositions[0]
    assert row.source is DispositionSource.PROPOSER
    assert row.rationale  # a proposer verdict is explained


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_a_fabricated_citation_flags_that_candidate_only(assessment_repo):
    """DD8: a violation drops the ITEM. The phase still reports measured."""
    ...  # TestModel citing "does/not/exist.py" for one of two candidates
    assert result.discover.collected.state is CollectionState.MEASURED
    flagged = next(d for d in result.discover.dispositions if d.source is DispositionSource.DROPPED)
    assert flagged.action is DiscoverAction.FLAG
    assert flagged.rule == "dropped_ref_unresolved"


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_mass_fabrication_takes_the_phase_to_not_collected(assessment_repo):
    """DD8's guard: past 0.10, the surviving references are not evidence."""
    ...  # TestModel where every citation is fabricated
    row = next(p for p in result.phases if p.phase is PhaseId.DISCOVER)
    assert row.collected.state is CollectionState.NOT_COLLECTED
    assert "fabrication rate" in row.collected.reason
    assert result.discover is None  # the paired validator enforces this


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_the_map_carries_the_blueprint_and_the_domain_model(assessment_repo):
    """Clauses D7 and D8 reach the artifact."""
    assert result.discover.blueprint is not None
    assert result.discover.blueprint.counts  # every status, incl. zeros
    assert result.discover.domain_model is not None


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_a_proposer_map_and_a_baseline_map_do_not_share_a_memo_key(assessment_repo):
    """P2-D6 end to end: NO_PROPOSER vs the role's real prompt_sha/model.
    A run WITH the proposer must miss a memo populated WITHOUT it."""
    ...  # run 1 with t_discover monkeypatched to None -> baseline map stored
    # run 2 with the TestModel proposer -> discover_lock is called again
```

Fill each `...` with the real setup from the neighbouring plan-2 tests. Do not
hand-build `ScanResult` or `DiscoverContext` — the seam test's whole lesson
(E-47c's review) is that unit-shaped inputs hide defects the real producers
expose.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assessment_workflow_e2e.py -m temporal -v -k "proposer or fabricat or blueprint"`
Expected: FAIL — the proposer never runs, so `source` is `baseline` and
`blueprint` is `None`.

- [ ] **Step 3: Wire the proposer into `_discover`**

In `src/sdlc/workflows/assessment.py`, inside the `with workflow.unsafe.imports_passed_through()` block, add:

```python
from ..agents.roles import PROMPT_SHAS, STAGE_MODELS, t_discover
from ..assessment.activities import (
    BlueprintInput,
    VerifyRefsInput,
    load_blueprint,
    verify_discover_refs,
)
from ..assessment.discover.domain import consolidate
from ..assessment.discover.map import guard_tripped
```

Replace the memo-key block so it carries the role's real terms when the
proposer will run (P2-D6 said plan 3 changes the caller, not the memo):

```python
# P2-D6: NO_PROPOSER, never "". A baseline-only map and a proposer map
# must never share a key, so the two terms are the role's own when the
# role is shipped and the sentinel when it is not.
proposing = t_discover is not None
memo_key = DiscoverMemoInput(
    project=inp.project_key,
    tree_hash=scan_out.tree_hash,
    context_digest=context_digest(context),
    prompt_sha=PROMPT_SHAS["discover"] if proposing else NO_PROPOSER,
    model=STAGE_MODELS["discover"] if proposing else NO_PROPOSER,
)
```

Replace the `apply(context, stamp(context, None))` block with the proposer
pipeline. The proposer's own failure is DD7's *absent* case only when the role
is absent; a role that ran and raised is a degraded run, and DD9 does not list
it as a phase failure — so it degrades to the baseline with the reason
recorded, never silently:

```python
proposal = None
verification = None
if proposing:
    try:
        run = await t_discover.run(render_discover_prompt(context))
        proposal = run.output
    except Exception as e:  # noqa: BLE001
        # The role shipped but the call failed. Not DD7's ABSENT case
        # -- the reasons must not converge -- so the baseline runs and
        # the map records why judgment is missing.
        proposal = None
        advisory_reason = f"the discover proposer failed: {type(e).__name__}: {e}"[:300]

if proposal is not None:
    verification = await run_or_degrade(
        verify_discover_refs,
        VerifyRefsInput(repo_dir=inp.repo_dir, commit_sha=triage.commit_sha, proposal=proposal),
        DISCOVER_ACT,
        fallback=lambda: None,
    )
    if verification is None:
        # Verification could not run, so no citation is verified.
        # Applying the proposal anyway would ship exactly the
        # unverified claims DD8 exists to refuse.
        return no_discover(
            "verify_discover_refs did not run, so no citation could be verified (DD8 fails closed)"
        )
    tripped = guard_tripped(verification)
    if tripped:
        return no_discover(tripped)

try:
    stamped = stamp(
        context,
        verification.proposal if verification is not None else None,
        refusals=verification.refusals if verification is not None else {},
    )
    applied = apply(context, stamped)
except Exception as e:  # noqa: BLE001
    return no_discover(f"disposition apply failed: {type(e).__name__}: {e}"[:300])
```

After `discover_finalize` returns and before `build_map`, add the blueprint
call — it needs the locked capabilities' names, which only exist after the
lock:

```python
blueprint = await run_or_degrade(
    load_blueprint,
    BlueprintInput(capabilities=[...]),  # the locked capabilities
    DISCOVER_ACT,
    fallback=lambda: not_compared("load_blueprint did not run to completion"),
)
```

and extend the `build_map` call:

```python
capability_map = build_map(
    applied,
    bc_of,
    advisories=lock.advisories,
    attribution=finalized.attribution,
    decomposition=finalized.decomposition,
    ownership=finalized.ownership,
    total_references=(verification.total_references if verification is not None else 0),
    blueprint=blueprint,
    domain_model=consolidate(finalized.ownership, []),
)
```

`build_map` constructs the `Capability` rows, so the blueprint needs them
first. Restructure minimally: build the map, then compare against
`capability_map.capabilities`, then attach — or expose a small
`capabilities_of(applied, bc_of)` helper in `apply.py` so both callers share
one construction. **Prefer the helper**: two places constructing `Capability`
rows is the second-producer defect this package refuses everywhere else.

Write `render_discover_prompt(context)` in `discover/context.py` as a bounded
renderer following `context/project.py`'s `render_for_prompt()` — it must
announce its cuts rather than truncate silently.

- [ ] **Step 4: Update the phase-owner note**

`src/sdlc/workflows/assessment.py:88` says DISCOVER's body is built. It now is
*completely* built; no change needed to `PHASE_OWNER`. Do update `_discover`'s
docstring, which still says "minus the proposer plan 3 inserts".

- [ ] **Step 5: Run the workflow e2e**

Run: `pytest tests/test_assessment_workflow_e2e.py -m temporal -v`
Expected: PASS, including plan 2's `test_discover_goes_measured...` and
`test_a_second_assessment_of_the_same_tree_hits_the_memo`.

If the host contends on the time-skipping environment (P5's note records this
happening), run the file alone rather than with the rest of the temporal suite,
and record the contention in the commit message rather than deleting the test.

- [ ] **Step 6: Run the full suite**

Run: `pytest -q -m "not temporal"` then `pytest -q -m temporal`
Expected: PASS. Investigate any failure rather than adjusting the assertion.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/workflows/assessment.py src/sdlc/assessment/discover/context.py src/sdlc/assessment/discover/apply.py tests/test_assessment_workflow_e2e.py
git commit -m "feat(discover): the proposer runs, verified and guarded (E-48 DD1/DD7/DD8)"
```

---

## Task 8: Roadmap and spec deltas

**Files:**
- Modify: `ROADMAP.md:226,1043` and `docs/roadmap.html` if it mirrors those rows
- Modify: `docs/superpowers/specs/2026-08-15-e48-discover-proposers-design.md` (a "Plan 3 corrections" section, if any decision moved)

- [ ] **Step 1: Apply the spec's own Roadmap-deltas table**

The spec already states them; apply exactly these:

| Item | Change |
|---|---|
| E-48 (`ROADMAP.md:1043`) | `[ ]` → `[x]`, noting plans 1–3 and their dates |
| FR-913 (`ROADMAP.md:226`) | ⚠️ → `[x]`. **Also delete the stale clause** "`workflows/assessment.py` still returns `unbuilt(PhaseId.DISCOVER)`" — that stopped being true when plan 2 landed |
| FR-911 | stub count 5 → 4; note `PHASE_OWNER` lost its `DISCOVER` entry in plan 2 |
| FR-914 | → `[x]` — the LLM-proposing assessment consumer it was held open for |
| SC-7 | note that the "zero fabricated path/line refs" clause is now **computed on every run**, not sampled |
| NFR-10 | add `verify.py`, `blueprint.py`, `domain.py` to the order-independence roll |
| NFR-9 | note that plan 3 adds no execution of repository code: `verify_discover_refs` is `git show` at the pinned commit, and `load_blueprint` reads a factory-shipped file |
| §15 item 6 | E-48 done; **E-49 is the next audit-depth item** |

- [ ] **Step 2: Record P3-D1, P3-D2 and P3-D6 in the spec**

Add a short "Plan 3 corrections" section to the E-48 design, following E-47c's
precedent. P3-D2 in particular reconciles two places in the codebase that
disagreed about the guard's denominator, and a future reader hitting
`build_map`'s old comment needs the resolution recorded where they will look.

- [ ] **Step 3: Verify the tracker claims against the code**

Run: `pytest -q -m "not temporal"` one final time, then re-read the four
`ROADMAP.md` rows you edited and confirm each is falsifiable from code you can
point at. This tracker's own method line requires it: *"Every FR / NFR / SC /
US / ADR ... checked against actual code, not against prior audit claims."*

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md docs/roadmap.html docs/superpowers/specs/2026-08-15-e48-discover-proposers-design.md
git commit -m "docs(roadmap): E-48 lands complete -- FR-913 and FR-914 close"
```

---

## Self-Review

**Spec coverage.** DD1 → Tasks 1, 7 (the proposer disposes; code stamps). DD2 → the File Structure table's placement. DD7 → Task 1 (`OPTIONAL_ROLES`, `t_discover is not None`) and Task 2 (the two non-converging fallbacks). DD8 items 1–3 → already in plan 2's `stamp`; items 4–5 → Tasks 2–3; the guard → Task 4. DD9's degradation table → Task 7's branches. DD10 → Task 7's memo-key change (P2-D6's forward reference). DD11 → Task 5. DD12 → Task 6. DD13's plan-3 row → Tasks 1–7 in full; no `CheckResult` is computed anywhere here, which is correct (E-50/E-51 own it). The Testing section's five headings all have a home: unit-per-module (Tasks 2, 5, 6), NFR-10 determinism (a test in each of those three files), the seam test (Task 7's e2e uses real producers), grounding (Tasks 2, 3, 7), memo (Task 7's last e2e), temporal e2e (Task 7).

**Two spec items deliberately not covered**, both because the spec itself scopes them out: the other six blueprints (curation work with its own item) and `OwnershipVerb.TRACKS` (DD12 — no producer in this design has standing to emit it).

**Placeholder scan.** Task 7's e2e bodies carry `...` where the fixture setup goes, and that is the one place this plan does not hand over finished code. It is deliberate and it is called out in the step: the tests must be built from the neighbouring plan-2 tests' real fixtures, because E-47c's pre-merge review found a defect that every hand-built unit input missed. An executor who writes those bodies from the real producers gets the guarantee; one who writes them from invented structs does not. Everywhere else, every code step carries the actual code.

**Type consistency.** `verify_refs(proposal, blobs) -> RefVerification` is defined in Task 2 and consumed by Tasks 3, 4 and 7 under that name. `guard_tripped(verification) -> str` (a reason, not a bool) is defined in Task 4 and called in Task 7. `stamp(context, proposal, *, refusals={})` keeps plan 2's positional signature intact. `build_map` accumulates three keyword-only parameters across Tasks 4, 5 and 6, each defaulting so the previous task's call site keeps compiling. `not_compared(reason)` is defined in Task 5 and used as Task 7's fallback. `consolidate(ownership, capabilities)` is defined in Task 6 and called in Task 7.

**One risk worth naming before execution.** Task 7 needs the locked `Capability` rows *before* `build_map` in order to compare them against the blueprint, and today `build_map` is the only place those rows are constructed. The step says to extract a shared `capabilities_of(applied, bc_of)` helper rather than construct them twice. If the executor takes the shortcut instead, the map's rows and the blueprint's matches become two constructions that can disagree — which is the second-producer defect this package refuses everywhere else.
