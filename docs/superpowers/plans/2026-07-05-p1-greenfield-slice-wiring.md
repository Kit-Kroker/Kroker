# P1 Greenfield Slice — Wiring Plan (Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the "defined but not wired" governance gaps so P1 ("one greenfield project shipped end-to-end") honors the PRD's hard invariants — above all **SC-5: zero deploys past a failed absolute gate check**. The `DeterministicQualityGate`, the ADR-14 integration branch, the REVISE gate outcome, and the context-ceiling trigger all exist as tested code but are bypassed by the live `FeatureWorkflow`. This plan wires them in.

**Architecture:** Four independent wiring changes to `src/sdlc/workflows/feature.py` and supporting activities, each protected by a new AST-purity or runtime test. The precedence rule from `docs/architecture-review-2026-07.md` Finding #5 becomes executable: *deterministic gate first (absolute failures terminal, advisory failures human-overridable); `MergeVerdict` consulted only under SOFT merge policy and only after the gate passes.* No new subsystems — this plan makes existing mechanisms load-bearing.

**Tech Stack:** Python ≥3.11, Pydantic v2, `temporalio`, `pydantic-ai-slim`, `pytest`, `git` CLI. src-layout package installed with `pip install -e .[dev]`.

## Scope and ranking

Ranked by governance risk (worst-first). Tasks 1–4 are fully specified here; Tasks 5–7 are scoped roadmap items that each warrant their own detailed plan.

| # | Task | Risk addressed | Detail |
|---|---|---|---|
| 1 | Wire `DeterministicQualityGate` into merge | **SC-5 broken** — merge uses only advisory `MergeVerdict` | Full TDD |
| 2 | Implement REVISE outcome + bounded revision loop | Gate contract incomplete — architecture/plan can't loop back | Full TDD |
| 3 | Wire ADR-14 integration branch | Dependent tasks can't see predecessors' code (Finding #1) | Full TDD |
| 4 | Consult `near_context_ceiling()` in fix loop | Compaction treated as recoverable; reasoning thread lost | Full TDD |
| 5 | Constitution + retro + intake routing stages | 6-stage flow, not the 14-stage DAG | Roadmap |
| 6 | Second task queue `ai-sdlc-harness` (ADR-9) | No proposer/harness pool split | Roadmap |
| 7 | `fake_harness.py` + observability export | No CI stand-in; no `events.jsonl`/`report.html` | Roadmap |

## Global Constraints

- **Python floor 3.11** (`pyproject.toml requires-python = ">=3.11"`). If the dev interpreter (3.14.3) fails to build `temporalio`/`pydantic-ai-slim`, use a 3.12 or 3.13 venv.
- **src layout**: package is `sdlc` under `src/`. Tests import `sdlc.*`; editable install required. No `sys.path` hacks.
- **Established patterns**: activity inputs/outputs are `@dataclass`es (`activities.py`); pipeline contracts are Pydantic `BaseModel`s (`models.py`); pure logic lives outside the workflow class (`gate.py`). Keep that split.
- **Workflow determinism**: nothing under `workflows/` may import `subprocess`, `httpx`, the memory client, or the harness package. Enforced today by `tests/test_factory_purity.py` + `tests/test_memory_purity.py` (AST). New wiring must route I/O through activities only.
- **Temporal payload discipline**: keep model fields small; large blobs stay behind `ArtifactRef`. Do not add large inline fields to anything that travels through workflow history.
- **No `--allowedTools` edits in prompts**: risk classing lives in the `pre_tool` hook layer (still a roadmap item); this plan does not touch harness permissions.
- **P1 = hard gates everywhere, no memory**: soft-gate `MergeVerdict` consultation is wired (Task 1) but the default merge policy stays `HARD` (`models.py:289`). Memory stays `enabled=False`.
- TDD (test first, watch it fail, minimal impl, watch it pass), DRY, YAGNI, frequent commits.

---

## File Structure

| File | Responsibility | This plan |
|---|---|---|
| `src/sdlc/workflows/feature.py` | `FeatureWorkflow` — the wiring target | Modify (Tasks 1–4) |
| `src/sdlc/activities.py` | add `run_lint` activity; reuse `evaluate_gate`, integration activities | Modify (Task 1, 3) |
| `src/sdlc/models.py` | add `MAX_GATE_ROUNDS` constant on `PipelineConfig`; `LinterInput`/evidence types as needed | Modify (Task 2) |
| `src/sdlc/agents/roles.py` | none required (Task 2 revises the calling pattern, not the agents) | — |
| `tests/test_merge_gate_wiring.py` | runtime + AST: gate runs before `MergeVerdict`; absolute failure terminal | Create (Task 1) |
| `tests/test_gate_revision_loop.py` | REVISE loops back with guidance, bounded by `MAX_GATE_ROUNDS` | Create (Task 2) |
| `tests/test_integration_branch_wired.py` | AST + git: tasks branch from integration head; merge-back updates head | Create (Task 3) |
| `tests/test_context_ceiling_trigger.py` | `near_context_ceiling()` forces a fresh session mid-loop | Create (Task 4) |

---

## Task 1: Wire `DeterministicQualityGate` into the merge stage

**Why first:** this is the only gap that violates a *hard* PRD invariant. SC-5 ("zero deploys past a failed absolute check") is currently unenforced in the live path: `feature.py:548-570` consults only the advisory `MergeVerdict`, and the tested `evaluate_quality_gate` (`gate.py:61`, `tests/test_quality_gate.py`) is dead code in the workflow. The merge comment at `feature.py:548-549` even says "Plan 2 runs the DeterministicQualityGate before this consult" — this is that plan.

**Precedence to implement (Finding #5, ARCH §10):**
1. Collect typed evidence (per-task QA + a lint run).
2. `evaluate_gate` activity → `GateReport`.
3. Any **absolute** check in `blocking` → terminal `rejected:merge:absolute-gate-failed`. No human, no policy, no `MergeVerdict` can override.
4. **Advisory** checks in `blocking` → the merge gate wait *is* the override mechanism; a human `APPROVE` records `GateOverride`s, a human `REJECT` terminates.
5. Gate passed clean → consult `MergeVerdict` **only under `SOFT` merge policy**; `HARD` proceeds on the human's decision; `OFF` proceeds.

**Files:**
- Modify: `src/sdlc/activities.py` (add `run_lint` + `LintInput`)
- Modify: `src/sdlc/workflows/feature.py` (`_dev_task` returns QA evidence; merge stage rewritten)
- Create: `tests/test_merge_gate_wiring.py`

**Interfaces:**
- Consumes: `evaluate_gate` activity (`activities.py:269`), `evaluate_quality_gate` pure fn (`gate.py:61`), `CheckResult`/`GateOverride`/`GateReport` (`gate.py`), `MergeVerdict` (`models.py:233`), per-task `QAReport` (`models.py:168`).
- Produces: a run-level `evidence: dict[str, QAReport]` accumulated by `_dev_task`; merge stage emits `GateReport` retained to memory; new `run_lint` activity.

- [ ] **Step 1: Write the failing AST test (gate is consulted before MergeVerdict)**

Create `tests/test_merge_gate_wiring.py`:

```python
import ast, pathlib, pytest

SRC = pathlib.Path("src/sdlc/workflows/feature.py")

def _fn(tree, name):
    for n in ast.walk(tree):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == name:
            return n
    raise AssertionError(f"function {name} not found")

@pytest.fixture(scope="module")
def feature_src():
    return SRC.read_text(encoding="utf-8")

@pytest.fixture(scope="module")
def feature_tree(feature_src):
    return ast.parse(feature_src)

def test_merge_stage_calls_evaluate_gate_before_merge_verdict(feature_tree):
    """SC-5: the deterministic gate is a hard precondition. Its activity
    call must textually precede any t_merge_verdict.run call in run()."""
    run = _fn(feature_tree, "run")
    src = ast.get_source_segment(run)  # type: ignore[arg-type]
    assert src is not None
    g = src.find("evaluate_gate")
    v = src.find("t_merge_verdict")
    assert g != -1, "merge stage does not call evaluate_gate activity"
    # When MergeVerdict is unreachable (e.g. gate failed), v may be -1;
    # when it is present it MUST come after the gate.
    if v != -1:
        assert g < v, "MergeVerdict consulted before DeterministicQualityGate"

def test_merge_stage_terminates_on_absolute_failure(feature_src):
    """An absolute gate failure is terminal — the workflow must return
    before any human-gate wait or MergeVerdict consult."""
    needle = "absolute-gate-failed"
    assert needle in feature_src, (
        "merge stage must short-circuit on absolute gate failure "
        f"(looked for return marker containing {needle!r})")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_merge_gate_wiring.py -v`
Expected: FAIL — `evaluate_gate` not found in `run()`; marker string absent.

- [ ] **Step 3: Add the `run_lint` activity**

In `src/sdlc/activities.py`, add after `run_test_suite` (line ~219):

```python
@dataclass
class LintInput:
    worktree: str
    lint_cmd: str = "ruff check ."


@activity.defn
async def run_lint(inp: LintInput) -> tuple[bool, str]:
    """Run a linter; return (clean, detail). P1 runs the repo's configured
    linter; non-zero exit = not clean. `detail` is the tail of stdout for
    the gate's CheckResult.detail."""
    proc = await asyncio.create_subprocess_shell(
        inp.lint_cmd, cwd=inp.worktree,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out_b, _ = await proc.communicate()
    out = out_b.decode(errors="replace")
    return proc.returncode == 0, out[-2000:]
```

- [ ] **Step 4: Surface per-task QA evidence from `_dev_task`**

`_dev_task` currently runs `qa_raw` (a `QAReport`) and discards it. Add it to `TaskResult` so the merge stage can aggregate. In `src/sdlc/models.py`, extend `TaskResult` (line 158):

```python
class TaskResult(BaseModel):
    task_id: str
    status: Literal["done", "failed", "quarantined"]
    attempts: int
    branch: str
    run: HarnessRunResult | None = None
    handoff: HandoffSummary | None = None   # FR-805
    qa: QAReport | None = None              # NEW: evidence for the merge gate
    notes: str = ""
```

In `feature.py:_dev_task`, set `qa=qa_raw` on the returned `TaskResult` (both the success return at line ~353 and — as `None` — on the quarantined return at line ~384). Import `QAReport` is already in scope via `activities`.

- [ ] **Step 5: Rewrite the merge stage with gate-first precedence**

Replace the body of `run()` from the `# 5. MERGE gate` comment (line ~548) through the `open_pull_request` call (line ~577) with:

```python
        # 5. MERGE — DeterministicQualityGate first (SC-5), then the human
        # gate (which doubles as the advisory-override mechanism), then
        # MergeVerdict advisory only under SOFT policy.
        _started = workflow.now()

        # 5a. Collect typed evidence from the run.
        integration_worktree = repo_path  # Task 3 will make this the integration wt
        lint_clean, lint_detail = await workflow.execute_activity(
            run_lint, LintInput(worktree=integration_worktree), **ACT)
        all_tests_green = all(
            r.qa.tests_passed for r in done.values() if r.qa is not None)

        checks = [
            build_check("build_integration_green", all_tests_green,
                        CheckClass.ABSOLUTE,
                        detail="aggregate of per-task pytest runs"),
            build_check("lint_clean", lint_clean, CheckClass.ABSOLUTE,
                        detail=lint_detail),
        ]
        gate_report: GateReport = await workflow.execute_activity(
            evaluate_gate, QualityGateInput(checks=checks), **ACT)

        # 5b. Absolute failure = terminal. No override path exists.
        absolute_blocking = [
            c.name for c in gate_report.checks
            if c.name in gate_report.blocking
            and c.classification is CheckClass.ABSOLUTE]
        if absolute_blocking:
            await self._retain(
                cfg, MemoryKind.GATE_FEEDBACK, cfg.memory.project_bank,
                text=f"merge blocked (absolute): {absolute_blocking}",
                metadata={"gate": "merge", "run_id": workflow.info().workflow_id})
            return f"rejected:merge:absolute-gate-failed:{','.join(absolute_blocking)}"

        # 5c. Advisory failure: the human merge gate IS the override. A
        # human APPROVE records audited GateOverrides; REJECT terminates.
        overrides: list[GateOverride] = []
        if not gate_report.passed:
            advisory_blocking = [
                c.name for c in gate_report.checks
                if c.name in gate_report.blocking
                and c.classification is CheckClass.ADVISORY]
            gate = await self._gate("merge", cfg)
            if not gate.approved:
                return "rejected:merge:advisory"
            # Human waved the advisory checks through — record each waiver.
            reviewer = gate.reviewer or "human"
            reason = gate.comments or "advisory override"
            overrides = [
                GateOverride(check=n, approved_by=reviewer, reason=reason)
                for n in advisory_blocking]
            gate_report = await workflow.execute_activity(
                evaluate_gate,
                QualityGateInput(checks=checks, overrides=overrides), **ACT)
        else:
            # 5d. Gate passed clean. MergeVerdict is advisory and ONLY
            # consulted under SOFT policy — it can approve an already-clean
            # build; it can never reach this branch otherwise.
            if cfg.gates.get("merge", GatePolicy.HARD) == GatePolicy.SOFT:
                verdict: MergeVerdict = (await t_merge_verdict.run(
                    "Advisory only — the deterministic gate already passed. "
                    f"Task results: {[r.model_dump() for r in done.values()]}"
                )).output
                if not verdict.approve:
                    # Soft policy + negative verdict = escalate to human.
                    gate = await self._gate("merge", cfg)
                    if not gate.approved:
                        return "rejected:merge:soft-verdict"
            gate = GateDecision(gate="merge", outcome=GateOutcome.APPROVE,
                                decided_by="policy")

        _ended = workflow.now()
        await self._record(cfg, self._stage_record(
            cfg, stage="merge", role="reviewer",
            started=_started, ended=_ended,
            quality_score=(1.0 if gate_report.passed else 0.0),
            judge="deterministic_gate",
            outcome=BenchmarkOutcome.PASS,
            model="deterministic"))
        await self._retain(
            cfg, MemoryKind.GATE_FEEDBACK, cfg.memory.project_bank,
            text=(f"merge gate: passed={gate_report.passed} "
                  f"overridden={[o.check for o in overrides]}"),
            metadata={"gate": "merge", "run_id": workflow.info().workflow_id})

        pr_url = await workflow.execute_activity(
            open_pull_request,
            PROpenInput(worktree=repo_path, title=idea.title,
                        body=arch.overview, base_branch=idea.base_branch),
            **ACT,
        )
```

Add the new imports inside the `with workflow.unsafe.imports_passed_through():` block at the top of `feature.py`:

```python
    from ..activities import (
        CodingTaskInput, DeployInput, DiffInput, LintInput, PROpenInput,
        QAInput, WorktreeInput, create_worktree, deploy, evaluate_gate,
        get_task_diff, open_pull_request, run_coding_task, run_lint,
        run_test_suite,
    )
    from ..gate import (
        CheckClass, CheckResult, GateOverride, GateReport, QualityGateInput,
        build_check,
    )
```

(Note: `QualityGateInput` currently lives in `activities.py:263` — import it from there, or move it to `gate.py` and import from both. Prefer moving it to `gate.py` next to the types it references, then re-export from `activities.py` for the activity. Pick one home; do not duplicate.)

- [ ] **Step 6: Run the AST tests to verify they pass**

Run: `pytest tests/test_merge_gate_wiring.py -v`
Expected: PASS.

- [ ] **Step 7: Add a runtime test for the precedence logic**

Append to `tests/test_merge_gate_wiring.py`:

```python
from sdlc.gate import (
    CheckClass, GateOverride, build_check, evaluate_quality_gate,
)

def test_absolute_failure_blocks_despite_override():
    """SC-5: an absolute check failure cannot be waived by a human override."""
    checks = [build_check("build_integration_green", False,
                          CheckClass.ABSOLUTE, detail="tests red")]
    report = evaluate_quality_gate(
        checks, overrides=[GateOverride(check="build_integration_green",
                                        approved_by="human", reason="ship it")])
    assert not report.passed
    assert "build_integration_green" in report.blocking
    assert report.overridden == []

def test_advisory_failure_passes_with_audited_override():
    checks = [build_check("coverage_gate", False, CheckClass.ADVISORY)]
    report = evaluate_quality_gate(
        checks, overrides=[GateOverride(check="coverage_gate",
                                        approved_by="human", reason="accepted")])
    assert report.passed
    assert "coverage_gate" in report.overridden
```

- [ ] **Step 8: Run the full suite**

Run: `pytest -q`
Expected: PASS (existing tests unaffected; `TaskResult.qa` defaults to `None`).

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/activities.py src/sdlc/models.py src/sdlc/workflows/feature.py \
        tests/test_merge_gate_wiring.py
git commit -m "feat(merge): wire DeterministicQualityGate ahead of MergeVerdict (SC-5)"
```

---

## Task 2: Implement REVISE outcome + bounded revision loop

**Why:** `GateOutcome.REVISE` exists (`models.py:36`) and `GateDecision.guidance` exists (`models.py:183`), but `_gate()` (`feature.py:237-266`) only branches on APPROVE/REJECT and `_gate_decisions` is keyed by gate name alone — so a REVISE signal cannot loop the producer, and a second-round decision would overwrite or be ignored. The architecture/plan gates therefore can't "send back with comments" (PRD US-2, FR-301).

**Files:**
- Modify: `src/sdlc/models.py` (`PipelineConfig.max_gate_rounds`)
- Modify: `src/sdlc/workflows/feature.py` (round-keyed signals; `_revisable_stage` helper)
- Modify: `src/sdlc/cli.py` (optional `--round` on approve/reject; default to current)
- Create: `tests/test_gate_revision_loop.py`

**Interfaces:**
- Consumes: `gate_key(gate, round)` (`models.py:228`), `GateDecision.guidance`.
- Produces: `_revisable_stage(name, cfg, run_fn)` — runs `run_fn`, calls `_gate(name, cfg, round=round)`, on REVISE re-invokes `run_fn(decision.guidance)` at `round+1` up to `max_gate_rounds`; on exhaustion escalates to a hard human gate.

- [ ] **Step 1: Write the failing AST + behavior test**

Create `tests/test_gate_revision_loop.py`:

```python
import ast, pathlib, pytest
from sdlc.models import PipelineConfig, gate_key

SRC = pathlib.Path("src/sdlc/workflows/feature.py")

def test_gate_decisions_keyed_by_round():
    src = SRC.read_text(encoding="utf-8")
    # Signal handler must use gate_key(...) when storing the decision.
    assert "gate_key(" in src, (
        "submit_gate_decision must key by gate_key(gate, round), "
        "not by bare gate name — REVISE needs round-scoped identity")

def test_pipeline_config_has_max_gate_rounds():
    cfg = PipelineConfig()
    assert cfg.max_gate_rounds >= 1, "FR-301: MAX_GATE_ROUNDS default ≥ 1"

def test_gate_key_is_round_scoped():
    assert gate_key("architecture", 1) == "architecture#1"
    assert gate_key("architecture", 2) == "architecture#2"
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/test_gate_revision_loop.py -v`
Expected: FAIL — `gate_key(` not yet used in `feature.py`; `max_gate_rounds` absent.

- [ ] **Step 3: Add `max_gate_rounds` to `PipelineConfig`**

In `src/sdlc/models.py`, inside `PipelineConfig` (after `max_fix_attempts`, line ~303):

```python
    max_gate_rounds: int = 2                # FR-301: bounded revision loop;
                                            # exhaustion escalates to a hard
                                            # human gate
```

- [ ] **Step 4: Make the signal handler round-aware**

In `src/sdlc/workflows/feature.py`, change `_gate_decisions` usage. The signal becomes:

```python
    @workflow.signal
    def submit_gate_decision(self, decision: GateDecision) -> None:
        # Idempotent per (gate, round): first decision for a round wins.
        key = gate_key(decision.gate, decision.round)
        if key not in self._gate_decisions:
            decision.decided_at = workflow.now()
            self._gate_decisions[key] = decision
```

Add `gate_key` to the `..models` import block.

- [ ] **Step 5: Make `_gate` round-aware and add `_revisable_stage`**

Extend `_gate`'s signature to take `round: int = 1` and wait on `gate_key(name, round)`:

```python
    async def _gate(self, name: str, cfg: PipelineConfig,
                    auto_decision: GateDecision | None = None,
                    round: int = 1) -> GateDecision:
        policy = cfg.gates.get(name, GatePolicy.HARD)
        key = gate_key(name, round)
        if policy == GatePolicy.OFF:
            decision = GateDecision(gate=name, round=round,
                                    outcome=GateOutcome.APPROVE, decided_by="policy")
        elif policy == GatePolicy.SOFT and auto_decision and auto_decision.approved:
            decision = auto_decision
        else:
            self._status = f"awaiting:{name}"
            try:
                await workflow.wait_condition(
                    lambda: key in self._gate_decisions,
                    timeout=timedelta(hours=cfg.gate_timeout_hours))
                decision = self._gate_decisions[key]
            except TimeoutError:
                decision = GateDecision(gate=name, round=round,
                                        outcome=GateOutcome.REJECT, decided_by="timeout")
            finally:
                self._status = "running"
        await self._retain(
            cfg, MemoryKind.GATE_FEEDBACK, cfg.memory.project_bank,
            text=f"gate {name}#{round}: {decision.outcome.value}"
                 f"{' — ' + decision.comments if decision.comments else ''}",
            metadata={"gate": name, "round": str(round),
                      "run_id": workflow.info().workflow_id})
        return decision
```

Add the revision helper near `_gate`:

```python
    async def _revisable_stage(self, name: str, cfg: PipelineConfig,
                               run_fn) -> tuple[object, GateDecision]:
        """Run a proposer stage, gate it, and on REVISE re-run with the
        human's guidance at round+1, up to cfg.max_gate_rounds. Past that,
        escalate to a HARD human gate (FR-301). `run_fn(guidance: str | None)`
        must re-execute the producer with the guidance injected."""
        guidance: str | None = None
        for round in range(1, cfg.max_gate_rounds + 1):
            artifact = await run_fn(guidance)
            decision = await self._gate(name, cfg, round=round)
            if decision.outcome is not GateOutcome.REVISE:
                return artifact, decision
            guidance = decision.guidance or decision.comments
        # Exhausted: one final HARD gate decides accept-anyway vs abandon.
        artifact = await run_fn(guidance)
        decision = await self._gate(name, cfg, round=cfg.max_gate_rounds + 1)
        return artifact, decision
```

- [ ] **Step 6: Route the architecture + plan stages through `_revisable_stage`**

For each of the architecture and plan stages, wrap the existing `_cached_stage` + `_gate` calls in a single `run_fn(guidance)` closure that appends `guidance` to the agent prompt when present, then calls `_revisable_stage(name, cfg, run_fn)`. Keep the existing benchmark/memory retains around the returned artifact. (Minimal diff: the body inside the closure is the current `_run_architect` / `_run_plan` plus a `guidance` parameter.)

- [ ] **Step 7: CLI — default `--round` to current**

In `src/sdlc/cli.py`, the `approve`/`reject` subcommands construct a `GateDecision`. Add an optional `--round` flag (default `1`) propagated to the signal. Operators usually act on the current round; the flag exists for correctness when a round is open.

- [ ] **Step 8: Run the suite**

Run: `pytest tests/test_gate_revision_loop.py tests/test_gate_decision.py -q`
Expected: PASS (existing `test_gate_decision.py` round assertions still hold).

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/models.py src/sdlc/workflows/feature.py src/sdlc/cli.py \
        tests/test_gate_revision_loop.py
git commit -m "feat(gates): implement REVISE outcome + bounded revision loop (FR-301)"
```

---

## Task 3: Wire the ADR-14 running integration branch

**Why:** `setup_integration_branch` and `merge_into_integration` exist and are registered (`activities.py:73,108`, `worker.py`) but `FeatureWorkflow` never calls them — `run_one` passes `idea.base_branch` straight to `_dev_task` (`feature.py:520`), so a dependent task's worktree contains none of its predecessors' code (Finding #1). The merge-conflict-as-falsified-overlaps logic is dead code.

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (run-start setup; per-task `from_ref`; merge-back; PR base)
- Create: `tests/test_integration_branch_wired.py`

**Interfaces:**
- Consumes: `setup_integration_branch`, `merge_into_integration`, `MergeInput`, `IntegrationInput` (all in `activities.py`).
- Produces: `self._integration_head: str` updated after each successful task; the merge-gate PR targets `sdlc/<run_id>/integration` → `base`.

- [ ] **Step 1: Write the failing AST + git test**

Create `tests/test_integration_branch_wired.py`:

```python
import ast, pathlib, pytest

SRC = pathlib.Path("src/sdlc/workflows/feature.py")

def test_workflow_calls_setup_integration_branch():
    src = SRC.read_text(encoding="utf-8")
    assert "setup_integration_branch" in src, (
        "FeatureWorkflow.run must call setup_integration_branch at run start")

def test_workflow_calls_merge_into_integration():
    src = SRC.read_text(encoding="utf-8")
    assert "merge_into_integration" in src, (
        "on task completion, run_one must merge the task branch back into "
        "the integration branch (ADR-14)")

def test_dev_task_branches_from_integration_head():
    """`from_ref` passed to create_worktree must not be idea.base_branch."""
    src = SRC.read_text(encoding="utf-8")
    # The wiring passes self._integration_head, not idea.base_branch, as
    # the from_ref into _dev_task.
    assert "_integration_head" in src
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/test_integration_branch_wired.py -v`
Expected: FAIL — neither symbol referenced in `feature.py`.

- [ ] **Step 3: Add the integration setup + merge-back to `run()`**

In `src/sdlc/workflows/feature.py`, after the memory-watermark capture (line ~405) and before the CLARIFY stage, add:

```python
        # ADR-14: one sdlc/<run_id>/integration branch accumulates completed
        # task work; dependent tasks branch from its head.
        self._integration_head: str = await workflow.execute_activity(
            setup_integration_branch,
            IntegrationInput(repo_path=repo_path, run_id=workflow.info().workflow_id,
                             base_branch=idea.base_branch),
            **ACT,
        )
```

Add `self._integration_head: str | None = None` to `__init__`.

- [ ] **Step 4: Branch tasks from the integration head; merge back on success**

Update `run_one` (line ~519) to pass `self._integration_head` as the `from_ref`, and merge the task branch back when it finishes clean:

```python
        async def run_one(t: DevTask) -> None:
            r = await self._dev_task(t, repo_path, self._integration_head,
                                     cfg, handoffs)
            done[r.task_id] = r
            if r.handoff:
                handoffs.append(r.handoff)
            remaining.pop(r.task_id)
            if r.status == "done":
                merge_res = await workflow.execute_activity(
                    merge_into_integration,
                    MergeInput(repo_path=repo_path,
                               run_id=workflow.info().workflow_id,
                               task_branch=r.branch),
                    **ACT,
                )
                if merge_res.conflict:
                    # Falsified `overlaps` declaration → serialize/escalate.
                    raise RuntimeError(
                        f"integration conflict on task {r.task_id}: "
                        "declared overlaps were incomplete")
                self._integration_head = merge_res.integration_head
```

Update `_dev_task`'s signature: rename the `base_branch: str` parameter to `from_ref: str` and pass it through as `WorktreeInput.from_ref` (it already threads into `create_worktree` correctly — only the call-site argument name changes).

For wave mode, snapshot `self._integration_head` at wave start and merge sequentially within the batch (the `asyncio.gather` becomes a serialize-then-merge to keep integration updates ordered). P1 default is SERIAL, so the simple path is the priority; the wave path can serialize merges in completion order.

- [ ] **Step 5: Point the merge-gate PR at the integration branch**

In the merge stage (Task 1's rewritten block), change `open_pull_request` to push the integration worktree and target the run branch. The integration worktree path is `os.path.join(_worktrees_root(), run_id, "integration")` — expose it via a small helper or read it in the activity. Minimal change: pass `worktree=<integration path>` and `base_branch=idea.base_branch` (the PR is `integration → base`, exactly as ADR-14 specifies).

- [ ] **Step 6: Run the suite**

Run: `pytest tests/test_integration_branch_wired.py tests/test_integration_activities.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_integration_branch_wired.py
git commit -m "feat(code): wire ADR-14 running integration branch into FeatureWorkflow"
```

---

## Task 4: Consult `near_context_ceiling()` in the fix loop

**Why:** `HarnessRunResult.near_context_ceiling()` (`models.py:145`) is tested (`tests/test_harness_result.py`) but never called. `_dev_task` (`feature.py:367-380`) decides resume-vs-fresh-session on resume count alone, so a harness that silently compacts mid-task keeps getting resumed — ADR-13's "compaction is failure" rule is violated.

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (one condition in `_dev_task`)
- Create: `tests/test_context_ceiling_trigger.py`

**Interfaces:**
- Consumes: `HarnessRunResult.near_context_ceiling()`.

- [ ] **Step 1: Write the failing AST test**

Create `tests/test_context_ceiling_trigger.py`:

```python
import pathlib, pytest

SRC = pathlib.Path("src/sdlc/workflows/feature.py")

def test_dev_task_consults_near_context_ceiling():
    src = SRC.read_text(encoding="utf-8")
    assert "near_context_ceiling" in src, (
        "_dev_task must call run.near_context_ceiling() to force a fresh "
        "session when the harness is at/over its context budget (ADR-13)")
```

- [ ] **Step 2: Run it to verify failure**

Run: `pytest tests/test_context_ceiling_trigger.py -v`
Expected: FAIL.

- [ ] **Step 3: Add the ceiling check to the resume/fresh decision**

In `feature.py:_dev_task`, replace the resume decision (line ~367):

```python
            if resumes < cfg.max_session_resumes and not run.near_context_ceiling():
                session_id = run.session_id       # resume: context intact
                resumes += 1
                prompt = f"Previous attempt has issues. Fix them:\n- {issues}"
            else:
                # Either past the resume bound OR at/over the context
                # ceiling (compaction = failure) → fresh session seeded
                # with a structured handoff (FR-802, ADR-13).
                session_id = None
                prompt = (
                    f"Task: {task.title}\n{task.description}\n"
                    "A previous session implemented part of this in the same "
                    f"worktree (files: {', '.join(diff['files'][:20])}). "
                    "Review the current state, then fix these unmet contract "
                    f"assertions:\n- {issues}\n"
                    "Contract:\n- " + "\n- ".join(assertions)
                )
```

- [ ] **Step 4: Run the suite**

Run: `pytest tests/test_context_ceiling_trigger.py tests/test_harness_result.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_context_ceiling_trigger.py
git commit -m "feat(code): force fresh session at context ceiling (ADR-13)"
```

---

## Roadmap (Tasks 5–7) — each needs its own detailed plan

These are out of scope for *this* wiring plan because each introduces a new subsystem (not just wiring existing code) and would more than double the document. They are sequenced after Tasks 1–4.

### Task 5 — Constitution + retro + intake routing (the rest of the 14-stage DAG)
**Scope:** Add the deterministic `constitution` stage (stage 1 — pure code emitting a `Constitution` model), the `retro` stage (stage 13 — emits `RunSummary` + drives `reflect`), and `intake` routing that resolves `ProjectMode` and (for brownfield) will hand off to the Cartographer. Add the missing models: `Constitution`, `RunSummary`. Replace the `str` return of `run()` with a `RunSummary`. Exit criterion: the greenfield path executes all deterministic stages; brownfield still no-ops context.
**Why deferred:** it's pipeline *addition*, not wiring; the existing 6 stages already produce a deployable greenfield run, and P1's exit criteria don't require constitution/retro to ship.

### Task 6 — Second task queue `ai-sdlc-harness` (ADR-9)
**Scope:** Split `worker.py` so harness activities (`run_coding_task`, `run_test_suite`, `run_lint`, `deploy`, git activities) register on `ai-sdlc-harness` and proposer/support activities stay on `ai-sdlc`. Tag activities with `@activity.defn(dynamic=True)`-style or explicit `name=` + per-activity `task_queue` on `execute_activity`. Add a second Worker entrypoint. Exit criterion: harness and proposer pools scale independently; harness workers hold the only repo credentials.
**Why deferred:** operational/deployment concern; doesn't affect correctness of a single P1 run.

### Task 7 — `fake_harness.py` + observability export
**Scope:** (a) A deterministic `FakeHarness` implementing `CodingHarness` that emits canned `HarnessRunResult`s from a fixture file, registered behind a `SDLC_HARNESS=fake` env var, so CI can run the full workflow without `claude`/`opencode`. (b) An `observability/` module with a `render_history` activity that walks Temporal history + artifact refs and writes `events.jsonl` + `report.html` (the retro stage consumes it). Exit criterion: `pytest -q` runs the full `FeatureWorkflow` against the fake harness end-to-end in CI.
**Why deferred:** the existing AST purity tests adequately protect the wiring in Tasks 1–4; the fake harness unlocks *runtime* workflow tests, which is a different investment.

---

## Self-Review

**1. Spec coverage** (against PRD P1 exit: "one project shipped end-to-end"):
- SC-5 (no deploy past failed absolute check) → Task 1. ✅
- FR-301 (gate `approve|reject|revise`, bounded by `MAX_GATE_ROUNDS`) → Task 2. ✅
- FR-104 / ADR-14 (tasks integrate on a running branch) → Task 3. ✅
- ADR-13 (compaction is failure; context by reference) → Task 4. ✅
- FR-106 (deterministic gate, absolute vs advisory) → already built; Task 1 makes it load-bearing. ✅
- Constitution, retro, intake routing (FR-101 14-stage DAG) → Task 5 roadmap. P1 exit doesn't require them; flagged.
- Two task queues (ADR-9 / NFR-2) → Task 6 roadmap. P1 single-run exit doesn't require it; flagged.
- `events.jsonl` / `report.html` (FR-704) → Task 7 roadmap. Flagged.

**2. Placeholder scan:** all steps contain concrete code or exact commands. The wave-mode merge-ordering note in Task 3 Step 4 ("can serialize merges in completion order") is an explicit defer-to-implementation hint for the non-default path, not a placeholder — the SERIAL default is fully specified.

**3. Type consistency:** `GateReport`, `CheckClass`, `CheckResult`, `GateOverride`, `build_check`, `QualityGateInput`, `evaluate_gate` are used consistently with their definitions in `gate.py` / `activities.py`. `_revisable_stage`'s `run_fn(guidance)` signature matches how the architecture/plan closures inject guidance. `TaskResult.qa` is a new optional field with a default, so existing constructors remain valid. `from_ref` renames the `_dev_task` parameter but threads to the same `WorktreeInput.from_ref` field — no contract change.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-05-p1-greenfield-slice-wiring.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
