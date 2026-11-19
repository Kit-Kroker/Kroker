# FR-502 Ops Risk-Class Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete FR-502's ops clause — pure risk classification plus the gate conjunct that makes an ops-bearing plan's repair gate HARD from birth, so policy can never approve it.

**Architecture:** A pure classification in `maintenance/gate.py` (`risk_class`, `bears_human_required`) consulted at gate construction in `workflows/maintenance.py::_repair_gate`, behind a `workflow.patched("maint-risk-class")` marker taken only on the ops-bearing branch (replay-safe). Rendering surfaces classes in the gate context and the incidents table. Zero execution — the 023a GATE 2 ruling stands.

**Tech Stack:** Python 3.13, Pydantic, Temporalio (testing env for the wire cell), pytest.

**Spec:** `docs/superpowers/specs/2026-11-19-fr502-ops-risk-class-design.md` (approved 2026-11-19)

## Global Constraints

- `gate.py` purity: no I/O, no Temporal imports, no config reads (directory AGENTS.md).
- No new `MaintenanceConfig` gate fields — R9's "no configuration can open the repair gate" stays literal.
- No stored `risk_class` field on `RepairAction`/`RepairPlan` — classification is computed, never proposed.
- `workflow.patched("maint-risk-class")` is a wire name recorded in histories — never renamed; the condition order is `bears_human_required(...) and workflow.patched(...)` so pure-code_fix runs never take the marker (payload-guard precedent, `agents/payload_guard.py:123`).
- `tests/replay/` untouched; benchmark registry untouched; PRD untouched.
- GATE 1 Q6 unchanged: a human approval of a mixed plan executes only the `code_fix` subset.
- 1000-line file ceiling (`scripts/check_file_size.py`); `ruff` + `mypy` clean on touched files.
- One commit per task; RED test before implementation (TDD).

## Review Focus

1. **Ops-bearing plan above threshold at round 1** — confidence must NOT open the gate; only a human resolves it. Pinned by Task 2's temporal cell (effective 0.95 > threshold 0.8, gate still pending human).
2. **Malformed ops action** (`kind="ops"`, `ops_action=None` — no model cross-validator exists) — classification must fail closed to `HUMAN_REQUIRED`, never to None. Pinned in Task 1.
3. **Empty plan** (`actions=[]`) — `bears_human_required` is False; round rules alone govern. Pinned in Task 1.
4. **Ops-only plan, human-approved** — no child, verbatim `OPS_REFUSAL_OUTCOME`. Already pinned by `test_execution.py::test_human_refuses_an_ops_only_plan_with_the_verbatim_outcome`; Task 2's verification re-runs it as regression.
5. **Pure code_fix plans replay-identical** — no marker taken, gate settings byte-identical. Pinned by Task 2's step re-running the existing US suites (any change in gate settings for code_fix-only plans fails them).

---

### Task 1: Classification — `RiskClass`, `risk_class`, `bears_human_required`

**Files:**
- Modify: `src/sdlc/maintenance/models.py` (add `RiskClass` near `RepairAction`, ~line 215)
- Modify: `src/sdlc/maintenance/gate.py` (add two pure functions)
- Test: `tests/maintenance/test_risk_class.py` (new)

**Interfaces:**
- Consumes: `RepairAction` (`kind: Literal["code_fix","ops"]`, `ops_action: Literal["rollback","restart","scale"] | None`), `RepairPlan` (`.actions`) from `maintenance/models.py`.
- Produces: `class RiskClass(StrEnum): HUMAN_REQUIRED = "human_required"` (corrected 2026-11-19 from the plan's original `(str, Enum)` — ruff UP042 forbids that form; `StrEnum` is behaviorally identical for the contract); `risk_class(action: RepairAction) -> RiskClass | None`; `bears_human_required(plan: RepairPlan) -> bool` — both in `sdlc.maintenance.gate`.

- [ ] **Step 1: Write the failing tests** in `tests/maintenance/test_risk_class.py`

```python
from sdlc.maintenance.gate import bears_human_required, risk_class
from sdlc.maintenance.models import RepairAction, RepairPlan

def _plan(*actions):
    return RepairPlan(analysis="a", actions=list(actions),
                      self_confidence=0.9, floor=0.9, effective=0.9,
                      author_model="m")

def test_each_ops_verb_is_human_required():
    for verb in ("rollback", "restart", "scale"):
        a = RepairAction(kind="ops", summary="s", ops_action=verb)
        assert risk_class(a) == RiskClass.HUMAN_REQUIRED

def test_code_fix_has_no_class_confidence_governs():
    assert risk_class(RepairAction(kind="code_fix", summary="s",
                                   target_paths=["p.py"])) is None

def test_malformed_ops_action_fails_closed():
    # kind="ops" with ops_action=None has no model validator — the
    # classification must never let it pass as unclassed (Review Focus 2).
    assert risk_class(RepairAction(kind="ops", summary="s")) == RiskClass.HUMAN_REQUIRED

def test_bears_human_required_over_plan_shapes():
    assert bears_human_required(_plan(
        RepairAction(kind="code_fix", summary="s", target_paths=["p.py"]),
        RepairAction(kind="ops", summary="s", ops_action="rollback"))) is True
    assert bears_human_required(_plan(
        RepairAction(kind="code_fix", summary="s", target_paths=["p.py"]))) is False
    assert bears_human_required(_plan()) is False  # Review Focus 3
```

Import `RiskClass` from `sdlc.maintenance.models` in the test's imports.

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/maintenance/test_risk_class.py -q`
Expected: FAIL — `ImportError`/`AttributeError` (`RiskClass`/functions do not exist).

- [ ] **Step 3: Implement**

`RiskClass(str, Enum)` in `models.py` with docstring naming FR-502 and the growth path (adapters add classes). In `gate.py`: `risk_class` returns `HUMAN_REQUIRED` for every `kind == "ops"` action regardless of `ops_action` (fail closed — the verb never lowers the class), `None` for `code_fix`; `bears_human_required` is `any(risk_class(a) is not None for a in plan.actions)`. No confidence read anywhere (Review Focus 1's pure half).

- [ ] **Step 4: Run to verify GREEN**

Run: `uv run pytest tests/maintenance/test_risk_class.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/maintenance/models.py src/sdlc/maintenance/gate.py tests/maintenance/test_risk_class.py
git commit -m "feat(maintenance): FR-502 risk classification — ops verbs are HUMAN_REQUIRED, code_fix unclassed (pure)"
```

---

### Task 2: The gate conjunct — HARD from birth for ops-bearing plans

**Files:**
- Modify: `src/sdlc/workflows/maintenance.py:374-377` (`_repair_gate`'s `human_only`/`auto`)
- Test: `tests/maintenance/test_workflow_risk_class.py` (new, temporal)

**Interfaces:**
- Consumes: `bears_human_required` from Task 1; `workflow.patched` (in-workflow only).
- Produces: the wire behavior later docs describe — `human_only = inc.gate_round > 1 or (bears_human_required(inc.plan) and workflow.patched("maint-risk-class"))`.

- [ ] **Step 1: Write the failing temporal test** in `tests/maintenance/test_workflow_risk_class.py`

Follow the `test_workflow_us1.py` harness verbatim: `WorkflowEnvironment` + `Worker` on a dedicated `TASK_QUEUE = "maint-risk"`, `_cfg`/`_state` helpers, `_maintainer_activities(proposal)` with a TestModel proposal, `fake_triage.TRIAGE_ACTIVITIES`, `commit_build_break` from `tests/maintenance/conftest.py`; `pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]`.

The proposal: one `code_fix` action plus one `ops` action (`ops_action="rollback"`), `self_confidence=0.95` (above the default 0.8 threshold — Review Focus 1). The cell asserts:
1. after the cycle, the incident is `awaiting_decision` — NOT auto-approved (no `decided_by="policy"` anywhere in the state);
2. resolving the gate via a human approve (the US-suite `submit_gate_decision` pattern) starts exactly one child seeded with the code_fix paths — the ops action is recorded `not executed — ops proposal only`.

Name it `test_ops_bearing_plan_is_human_only_even_above_threshold`.

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest -m temporal tests/maintenance/test_workflow_risk_class.py -q`
Expected: FAIL — the incident is auto-approved (`decided_by="policy"`), no pending gate.

- [ ] **Step 3: Implement the conjunct** in `_repair_gate`

Replace `human_only = inc.gate_round > 1` with the conjunction from the Interfaces block; leave the `auto = ... if not human_only and ...` line untouched (it follows `human_only`). Keep the existing comment and add one dated line explaining the FR-502 conjunct and the marker's replay role.

- [ ] **Step 4: Run to verify GREEN + regression**

Run: `uv run pytest -m temporal tests/maintenance/test_workflow_risk_class.py -q` — Expected: PASS.
Run: `uv run pytest tests/maintenance/test_execution.py tests/maintenance/test_risk_class.py -q` and `uv run pytest -m temporal tests/maintenance/test_workflow_us1.py tests/maintenance/test_workflow_us2.py tests/maintenance/test_inbox_decide.py -q` — Expected: all PASS (Review Focus 4/5: Q6 semantics and code_fix-only gate settings unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/maintenance.py tests/maintenance/test_workflow_risk_class.py
git commit -m "feat(maintenance): an ops-bearing plan's repair gate is HARD from birth — policy can never approve it (FR-502, maint-risk-class marker)"
```

---

### Task 3: Rendering — gate context line + incidents class column

**Files:**
- Modify: `src/sdlc/maintenance/render.py` (`gate_context_text` ~line 43, `incidents_table`/`_HEADER` ~line 65)
- Test: append to `tests/maintenance/test_risk_class.py`

**Interfaces:**
- Consumes: `risk_class` from Task 1; existing `Incident`, `NO_EXECUTE_LINE`, `_HEADER`.
- Produces: a context line and a table column, exact copy below.

- [ ] **Step 1: Write the failing tests** (append to `test_risk_class.py`)

Assert `gate_context_text(incident_with_mixed_plan)` contains the exact line
`human-required ops: rollback — a human must decide; policy cannot approve` (verbs joined by `, ` in plan order, deduped); a code_fix-only incident's context does NOT contain `human-required ops`. Assert `incidents_table([mixed_incident])` renders the class column with `rollback[HUMAN_REQUIRED]`-style text and a code_fix-only row renders `-`. Follow `test_render.py`'s incident-fixture helpers for building incidents.

- [ ] **Step 2: Run to verify RED**

Run: `uv run pytest tests/maintenance/test_risk_class.py -q`
Expected: FAIL on the new cells (no such line/column).

- [ ] **Step 3: Implement**

In `gate_context_text`: after the plan block, when `incident.plan` bears classes, append the line from Step 1 (exact copy). In `incidents_table`: extend `_HEADER` and the row format with a bounded class column after `gate` — render each classed action as `<verb>[<class-value>]` joined by `, `, `-` when none; truncate the column like `key` is (`:<44.44` precedent). Update `test_render.py::test_table_header_has_the_six_contract_columns` with a dated correction for the new column (the house pattern: dated note, not silent edit).

- [ ] **Step 4: Run to verify GREEN + render regression**

Run: `uv run pytest tests/maintenance/test_risk_class.py tests/maintenance/test_render.py tests/maintenance/test_render_023b.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/maintenance/render.py tests/maintenance/test_risk_class.py tests/maintenance/test_render.py
git commit -m "feat(maintenance): risk classes surface — gate context names human-required ops, incidents table gains the class column (FR-502)"
```

---

### Task 4: Close-out — AGENTS row, battery, FR-502 → `[x]`, log, banner

**Files:**
- Modify: `src/sdlc/maintenance/AGENTS.md` (invariants list)
- Modify: `ROADMAP.md` (FR-502 row ~line 342, "Last verified" cell)
- Modify: `ARCHITECTURE.md` (§7 banner ~line 563)
- Modify: `docs/roadmap/last-verified-log.md` (prepend)

**Interfaces:**
- Consumes: Tasks 1-3 landed; the battery below.
- Produces: FR-502 `[x]`; recorded verification.

- [ ] **Step 1: Add the invariant row** to `maintenance/AGENTS.md`'s invariants: "Ops actions are risk-classed (`gate.risk_class`, FR-502): every ops action is `HUMAN_REQUIRED` today, so an ops-bearing plan's repair gate is HARD from birth behind the `maint-risk-class` marker — policy can never approve one; execution stays never (GATE 2)."

- [ ] **Step 2: Run the battery** (evidence for the flip)

`uv run ruff check src/sdlc/maintenance src/sdlc/workflows/maintenance.py && uv run ruff format --check src/sdlc/maintenance src/sdlc/workflows/maintenance.py && uv run mypy && uv run python scripts/check_file_size.py`
`uv run pytest tests/maintenance/ -q` → exit 0 (492 + the new fast cells: Task 1's four + Task 3's render cells).
`uv run pytest -m temporal tests/maintenance/ -q` → exit 0 (84 tests: 83 + the new cell).
Any red is fixed in the owning task's files, never suppressed.

- [ ] **Step 3: Flip FR-502 to `[x]`** with the landing note (both clauses delivered: code-fix 023b, ops risk-classing 2026-11-19 — classification pure, HARD-from-birth conjunct, classes surfaced; execution still never per GATE 2; adapters deferred past P4), refresh the one-sentence "Last verified" cell, prepend the full entry to `docs/roadmap/last-verified-log.md` (root AGENTS.md rule), and update the §7 banner's FR-502 sentence to "ops actions are risk-classed (2026-11-19); execution stays never."

- [ ] **Step 4: Verify battery green on the final tree, `git status --short tests/replay/` empty**

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/maintenance/AGENTS.md ROADMAP.md ARCHITECTURE.md docs/roadmap/last-verified-log.md
git commit -m "docs: FR-502 closed — ops risk-classing landed and verified (496 fast + 84 temporal); AGENTS row, log prepend, banner"
```

Staging note: the working tree carries another session's in-flight edits (retro row in ROADMAP.md, `filesystem-first.md`, `schedules/`, `tests/test_nightly_reflect_asset.py`, org-bank docs) — stage only this plan's hunks (filtered patch for ROADMAP.md).
