# Reviewer Stage + Agent Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a clean-context Reviewer stage whose model family is structurally forbidden from matching the developer's, enforced by a versioned config-driven agent registry validated at worker boot — closing ADR-6, FR-201, FR-204, and US-5.

**Architecture:** A new `ReviewReport` proposer (no tools, no repo, no session) judges the same clean inputs the QA validator already sees (frozen contract + materialized diff + test output) inside the per-task loop; its blocking findings feed the existing bounded fix loop and a new advisory check on the deterministic merge gate. A new `config/agents.yaml` registry + `agents/loader.py` validator enforces `model_family(reviewer) ≠ model_family(developer)` and fails the worker's boot if violated.

**Tech Stack:** Python ≥3.11, Pydantic v2, Pydantic AI (`TemporalAgent`), Temporal Python SDK, PyYAML, pytest.

## Global Constraints

- Python ≥3.11; Pydantic v2 models only (`from __future__ import annotations` in every module).
- **Determinism boundary (ADR-1/§14):** nothing under `src/sdlc/workflows/` may import `subprocess`, HTTP clients, the memory client, or the harness package. The reviewer runs as a `TemporalAgent` (model call auto-offloaded to an activity) — never a direct call.
- **Agent + toolset names are Temporal activity names** (`agents/roles.py` docstring): set `name=` explicitly and never rename after deploy. The new agent is `name="reviewer_agent"`.
- **ADR-6 invariant (verbatim):** the reviewer's model family MUST differ from the developer's authoring-model family. `model_family("provider:model")` and `model_family("provider/model")` both split on the first `:` or `/`.
- **Anti-collusion is structural:** the reviewer is a proposer — it holds no tools, no repo, no worker session, and never resumes the developer's harness session (FR-204).
- Run tests with `python -m pytest` (Scripts dir may not be on PATH).
- **New module = reinstall:** after adding `src/sdlc/agents/loader.py`, re-run `pip install -e .[dev]` before importing it (setuptools strict editable wheel does not auto-discover new files — see `docs/foundation.md`).
- Commit style: `feat(scope): …` / `fix(scope): …` / `test(scope): …`.

---

## File Structure

- **Create** `src/sdlc/agents/loader.py` — registry loader + `model_family` + `validate_registry` (the FR-204/US-5 teeth).
- **Create** `config/agents.yaml` — versioned role→model registry (FR-201). First file under `config/`.
- **Modify** `src/sdlc/models.py` — `ReviewFinding`/`ReviewReport` contracts; `RoleConfig.kind` + optional `harness`; `TaskResult.review`; `PipelineConfig.review_enabled` + self-consistent default reviewer role.
- **Modify** `src/sdlc/agents/roles.py` — `REVIEWER_PROMPT`, `reviewer_agent`, `t_reviewer`, `PROMPT_SHAS["review"]`, append to `ALL_TEMPORAL_AGENTS`.
- **Modify** `src/sdlc/workflows/feature.py` — run the reviewer in `_dev_task`; fold review into the pass condition and fix-loop feedback; add the merge-gate advisory check; import `t_reviewer`.
- **Modify** `src/sdlc/worker.py` — validate the registry at boot (fail-closed).
- **Tests** `tests/test_review_models.py`, `tests/test_agents_registry.py`, `tests/test_reviewer_agent.py`, `tests/test_review_wiring.py`, `tests/test_worker_registry_gate.py`.

---

### Task 1: Contracts — ReviewReport, RoleConfig.kind, TaskResult.review

**Files:**
- Modify: `src/sdlc/models.py` (`RoleConfig` ~229-240; `TaskResult` ~181-189; `QAReport` ~192-201; `PipelineConfig` ~308-348)
- Test: `tests/test_review_models.py`

**Interfaces:**
- Produces: `ReviewFinding{assertion:str, severity:Literal["critical","high","medium","low"], detail:str, suggested_fix:str=""}`; `ReviewReport{approve:bool, findings:list[ReviewFinding]=[], confidence:float|None=None}` with property `blocking_findings -> list[ReviewFinding]` (severity in {critical, high}); `RoleConfig.kind: Literal["proposer","harness"]="harness"`, `RoleConfig.harness: HarnessKind|None=None`; `TaskResult.review: ReviewReport|None=None`; `PipelineConfig.review_enabled: bool=True`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_review_models.py`:

```python
from sdlc.models import (
    PipelineConfig, ReviewFinding, ReviewReport, RoleConfig, TaskResult,
)


def test_blocking_findings_filters_to_critical_and_high():
    r = ReviewReport(approve=False, findings=[
        ReviewFinding(assertion="a1", severity="critical", detail="boom"),
        ReviewFinding(assertion="a2", severity="high", detail="bad"),
        ReviewFinding(assertion="a3", severity="medium", detail="meh"),
        ReviewFinding(assertion="a4", severity="low", detail="nit"),
    ])
    sev = [f.severity for f in r.blocking_findings]
    assert sev == ["critical", "high"]


def test_review_report_approve_defaults_clean():
    r = ReviewReport(approve=True)
    assert r.findings == []
    assert r.blocking_findings == []
    assert r.confidence is None


def test_role_config_proposer_needs_no_harness():
    rc = RoleConfig(kind="proposer", model="anthropic:glm-5.2")
    assert rc.harness is None
    assert rc.kind == "proposer"


def test_task_result_carries_optional_review():
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b")
    assert tr.review is None


def test_review_enabled_defaults_true():
    assert PipelineConfig().review_enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'ReviewReport'`.

- [ ] **Step 3: Add the contracts**

In `src/sdlc/models.py`, add `ReviewFinding` + `ReviewReport` immediately after the `QAReport` class:

```python
class ReviewFinding(BaseModel):
    assertion: str                          # which contract assertion / concern
    severity: Literal["critical", "high", "medium", "low"]
    detail: str
    suggested_fix: str = ""


class ReviewReport(BaseModel):
    """Clean-context reviewer output (ADR-6/ADR-12/FR-204). Emitted from
    orchestrator-assembled inputs only — frozen contract + materialized diff +
    test output. The reviewer holds no tools, no repo, no worker session, and
    never resumes the developer's harness session."""
    approve: bool
    findings: list[ReviewFinding] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)  # FR-301

    @property
    def blocking_findings(self) -> list[ReviewFinding]:
        return [f for f in self.findings if f.severity in ("critical", "high")]
```

In `TaskResult`, add the field after `qa`:

```python
    review: ReviewReport | None = None      # FR-204: clean-context review evidence
```

In `RoleConfig`, change the `harness` line and add `kind` at the top of the class body:

```python
    kind: Literal["proposer", "harness"] = "harness"
    harness: HarnessKind | None = None      # None for proposer roles
```

In `PipelineConfig`, add after `memoization_enabled`:

```python
    review_enabled: bool = True             # FR-204: run the clean-context
                                            # reviewer per task; disable to trade
                                            # the anti-collusion check for cost
```

Update the default `reviewer` entry in `PipelineConfig.roles` so defaults are self-consistent and family-distinct from `dev` (dev family `zai-coding-plan` ≠ reviewer family `anthropic`):

```python
        "reviewer": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review_models.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the full suite to confirm no contract regressions**

Run: `python -m pytest -q`
Expected: PASS — the `RoleConfig.harness` change is backward-compatible (all existing constructions set `harness`).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py tests/test_review_models.py
git commit -m "feat(models): add ReviewReport contract + RoleConfig.kind (FR-204)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Agent registry loader + `config/agents.yaml` + family validator

**Files:**
- Create: `src/sdlc/agents/loader.py`
- Create: `config/agents.yaml`
- Test: `tests/test_agents_registry.py`

**Interfaces:**
- Consumes: `RoleConfig` (Task 1).
- Produces: `model_family(model: str) -> str`; `load_registry(path: str | os.PathLike | None = None) -> dict[str, RoleConfig]`; `validate_registry(roles: dict[str, RoleConfig]) -> None` (raises `RegistryError` on violation); `class RegistryError(ValueError)`; `DEFAULT_AGENTS_CONFIG: Path`; env override `SDLC_AGENTS_CONFIG`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents_registry.py`:

```python
import pytest

from sdlc.agents.loader import (
    RegistryError, load_registry, model_family, validate_registry,
)
from sdlc.models import RoleConfig


def test_model_family_splits_on_colon_and_slash():
    assert model_family("anthropic:glm-5.2") == "anthropic"
    assert model_family("zai-coding-plan/glm-5.2") == "zai-coding-plan"
    assert model_family("OpenAI/gpt-5.2") == "openai"


def test_shipped_registry_loads_and_validates():
    roles = load_registry()                      # default config/agents.yaml
    assert "developer" in roles and "reviewer" in roles
    validate_registry(roles)                     # must not raise


def test_same_family_dev_and_reviewer_rejected():
    roles = {
        "developer": RoleConfig(kind="harness", model="zai-coding-plan/glm-5.2"),
        "reviewer": RoleConfig(kind="proposer", model="zai-coding-plan/other"),
    }
    with pytest.raises(RegistryError, match="family"):
        validate_registry(roles)


def test_different_family_accepted():
    roles = {
        "developer": RoleConfig(kind="harness", model="zai-coding-plan/glm-5.2"),
        "reviewer": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
    }
    validate_registry(roles)                     # no raise


def test_missing_role_rejected():
    with pytest.raises(RegistryError, match="developer and reviewer"):
        validate_registry({"developer": RoleConfig(model="a:b")})


def test_deep_review_harness_reviewer_must_differ_from_developer():
    from sdlc.models import HarnessKind
    roles = {
        "developer": RoleConfig(kind="harness", harness=HarnessKind.OPENCODE,
                                model="zai-coding-plan/glm-5.2"),
        "reviewer": RoleConfig(kind="harness", harness=HarnessKind.OPENCODE,
                               model="anthropic:glm-5.2"),
    }
    with pytest.raises(RegistryError, match="harness"):
        validate_registry(roles)


def test_load_registry_via_env_override(tmp_path, monkeypatch):
    cfg = tmp_path / "agents.yaml"
    cfg.write_text(
        "version: 1\nroles:\n"
        "  developer:\n    kind: harness\n    harness: opencode\n"
        "    model: zai-coding-plan/glm-5.2\n"
        "  reviewer:\n    kind: proposer\n    model: anthropic:glm-5.2\n",
        encoding="utf-8")
    monkeypatch.setenv("SDLC_AGENTS_CONFIG", str(cfg))
    roles = load_registry()
    assert roles["reviewer"].model == "anthropic:glm-5.2"
    assert roles["reviewer"].harness is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agents_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.agents.loader'`.

- [ ] **Step 3: Create the registry file**

Create `config/agents.yaml`:

```yaml
# Versioned agent registry (FR-201). Loaded and validated at worker boot by
# src/sdlc/agents/loader.py. The load-time validator enforces the ADR-6
# invariant: model_family(reviewer) != model_family(developer). Editing a
# model here is a per-project configuration change, not a code change (US-4/US-5).
version: 1
roles:
  developer:
    kind: harness
    harness: opencode
    model: zai-coding-plan/glm-5.2
  reviewer:
    kind: proposer                # clean-context, no tools (ADR-6 default)
    model: anthropic:glm-5.2      # DIFFERENT family than developer
```

- [ ] **Step 4: Create the loader**

Create `src/sdlc/agents/loader.py`:

```python
"""Agent registry (FR-201) + the ADR-6 anti-collusion validator (FR-204).

The registry is a versioned YAML asset (config/agents.yaml). Loading it and
running validate_registry() at worker boot is what gives the model-family
inequality invariant teeth — a same-family developer/reviewer config cannot
boot a worker.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from ..models import RoleConfig

AGENTS_CONFIG_ENV = "SDLC_AGENTS_CONFIG"
# repo_root/config/agents.yaml — loader.py is src/sdlc/agents/loader.py, so
# three parents up from the file dir is the repo root.
DEFAULT_AGENTS_CONFIG = Path(__file__).resolve().parents[3] / "config" / "agents.yaml"


class RegistryError(ValueError):
    """A registry that violates a structural invariant (missing role, or an
    ADR-6 same-family developer/reviewer pairing)."""


def model_family(model: str) -> str:
    """Provider/family prefix of a Pydantic AI model id. Splits on the first
    ':' or '/': 'anthropic:glm-5.2' -> 'anthropic';
    'zai-coding-plan/glm-5.2' -> 'zai-coding-plan'. Case-insensitive."""
    return re.split(r"[:/]", model, maxsplit=1)[0].strip().lower()


def load_registry(path: str | os.PathLike | None = None) -> dict[str, RoleConfig]:
    """Parse the registry YAML into {role_name: RoleConfig}. Resolution order:
    explicit arg, then $SDLC_AGENTS_CONFIG, then the shipped default."""
    resolved = Path(path or os.environ.get(AGENTS_CONFIG_ENV)
                    or DEFAULT_AGENTS_CONFIG)
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    roles_raw = data.get("roles") or {}
    return {name: RoleConfig(**cfg) for name, cfg in roles_raw.items()}


def validate_registry(roles: dict[str, RoleConfig]) -> None:
    """Fail closed on any structural violation. The ADR-6 invariant is
    model-family inequality (NOT harness inequality); the harness clause only
    applies to the optional deep-review harness reviewer tier."""
    dev = roles.get("developer")
    rev = roles.get("reviewer")
    if dev is None or rev is None:
        raise RegistryError(
            "registry must define both 'developer' and 'reviewer' roles")
    if dev.model is None or rev.model is None:
        raise RegistryError("developer and reviewer roles must declare a model")
    if model_family(dev.model) == model_family(rev.model):
        raise RegistryError(
            f"ADR-6 violation: reviewer family '{model_family(rev.model)}' "
            f"equals developer family — anti-collusion review requires a "
            f"different model family than the developer's authoring model")
    if rev.kind == "harness" and rev.harness is not None \
            and rev.harness == dev.harness:
        raise RegistryError(
            "deep-review harness reviewer must use a different harness than "
            "the developer")
```

- [ ] **Step 5: Reinstall (new module) and run the tests**

Run: `pip install -e .[dev] && python -m pytest tests/test_agents_registry.py -v`
Expected: PASS (7 passed).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/agents/loader.py config/agents.yaml tests/test_agents_registry.py
git commit -m "feat(agents): add config/agents.yaml registry + family-inequality validator (FR-201/FR-204)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Reviewer agent in the role registry

**Files:**
- Modify: `src/sdlc/agents/roles.py` (`MODEL` ~30; prompts ~38-110; agents ~112-158; `PROMPT_SHAS` ~160-165; `t_*` ~168-173; `ALL_TEMPORAL_AGENTS` ~175-176)
- Test: `tests/test_reviewer_agent.py`

**Interfaces:**
- Consumes: `ReviewReport` (Task 1); `model_family` + `load_registry` (Task 2).
- Produces: `REVIEWER_PROMPT: str`; `reviewer_agent: Agent[..., ReviewReport]`; `t_reviewer: TemporalAgent`; `t_reviewer` present in `ALL_TEMPORAL_AGENTS`; `PROMPT_SHAS["review"]`. The agent binds the shipped registry's reviewer model, so its family is guaranteed distinct from the developer default.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reviewer_agent.py`:

```python
from sdlc.agents.loader import load_registry, model_family
from sdlc.agents import roles
from sdlc.models import ReviewReport


def test_reviewer_agent_emits_review_report():
    assert roles.reviewer_agent.output_type is ReviewReport


def test_reviewer_registered_for_temporal():
    assert roles.t_reviewer in roles.ALL_TEMPORAL_AGENTS


def test_review_prompt_sha_present():
    assert "review" in roles.PROMPT_SHAS
    assert len(roles.PROMPT_SHAS["review"]) == 64      # sha256 hexdigest


def test_reviewer_model_family_differs_from_developer():
    """The bound reviewer model must be a different family than the shipped
    developer model — the ADR-6 invariant, guarded so the two constants can
    never silently drift into the same family."""
    reg = load_registry()
    assert model_family(reg["reviewer"].model) \
        != model_family(reg["developer"].model)
    # the agent actually binds that reviewer model
    assert reg["reviewer"].model in str(roles.reviewer_agent.model)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reviewer_agent.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.agents.roles' has no attribute 'reviewer_agent'`.

- [ ] **Step 3: Add the reviewer prompt and agent**

In `src/sdlc/agents/roles.py`, after the existing `from ..models import (...)` block, add the registry import and reviewer model resolution near the top (below `MODEL = "anthropic:glm-5.2"`):

```python
from .loader import load_registry

# The reviewer model comes from the versioned registry (FR-201), guaranteed a
# different family than the developer by validate_registry at worker boot.
REVIEWER_MODEL = load_registry()["reviewer"].model
```

Add `ReviewReport` to the `from ..models import (...)` list.

Add the prompt after `QA_PROMPT`:

```python
REVIEWER_PROMPT = (
    "You are a clean-context code reviewer. You receive ONLY: the task's "
    "frozen ValidationContract assertions, the test output, and the "
    "materialized diff. You never see, and must never request, the "
    "implementer's summary, reasoning, or session. Judge whether the diff "
    "correctly and safely satisfies each contract assertion. Report concrete "
    "findings with a severity of 'critical', 'high', 'medium', or 'low' and a "
    "suggested fix. Set 'approve' to false if ANY finding is 'critical' or "
    "'high'. Set confidence to a calibrated 0.0-1.0 self-assessment."
)
```

Add the agent after `qa_analyst_agent`:

```python
reviewer_agent = Agent(
    REVIEWER_MODEL,
    name="reviewer_agent",
    output_type=ReviewReport,
    model_settings=MODEL_SETTINGS,
    system_prompt=REVIEWER_PROMPT,
)
```

Add to `PROMPT_SHAS`:

```python
    "review": hashlib.sha256(REVIEWER_PROMPT.encode()).hexdigest(),
```

Add the Temporal wrapper after `t_qa`:

```python
t_reviewer = TemporalAgent(reviewer_agent, activity_config=AGENT_ACTIVITY_CONFIG)
```

Append `t_reviewer` to `ALL_TEMPORAL_AGENTS`:

```python
ALL_TEMPORAL_AGENTS = [t_clarify, t_architect, t_planner, t_qa,
                       t_reviewer, t_merge_verdict, t_devops]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_reviewer_agent.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Confirm the worker still registers cleanly**

Run: `python -m pytest tests/test_worker_registration.py -v`
Expected: PASS — `t_reviewer.temporal_activities` are picked up via the `ALL_TEMPORAL_AGENTS` iteration in `worker.py`.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/agents/roles.py tests/test_reviewer_agent.py
git commit -m "feat(agents): add clean-context reviewer_agent bound to registry model (ADR-6)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Fail-closed registry validation at worker boot

**Files:**
- Modify: `src/sdlc/worker.py` (imports ~28-42; `main()` ~47-52)
- Test: `tests/test_worker_registry_gate.py`

**Interfaces:**
- Consumes: `load_registry`, `validate_registry` (Task 2).
- Produces: `worker.main()` calls `validate_registry(load_registry())` before starting the worker; a bad registry raises `RegistryError` at boot.

- [ ] **Step 1: Write the failing test**

Create `tests/test_worker_registry_gate.py`:

```python
import pathlib

WORKER_SRC = pathlib.Path("src/sdlc/worker.py")


def test_worker_validates_registry_at_boot():
    src = WORKER_SRC.read_text(encoding="utf-8")
    assert "validate_registry" in src, (
        "worker.main() must validate the agent registry at boot so a "
        "same-family developer/reviewer config fails closed (FR-204)")
    assert "load_registry(" in src


def test_worker_validation_runs_before_worker_run():
    """The validation call must precede `await worker.run()` so a bad config
    never reaches the run loop."""
    src = WORKER_SRC.read_text(encoding="utf-8")
    assert src.index("validate_registry(") < src.index("worker.run()")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_worker_registry_gate.py -v`
Expected: FAIL — `AssertionError: worker.main() must validate the agent registry at boot`.

- [ ] **Step 3: Wire the boot gate**

In `src/sdlc/worker.py`, add the import beside the other agent imports:

```python
from .agents.loader import load_registry, validate_registry
```

In `main()`, add as the first statement inside the function body (before `client = await Client.connect(...)`):

```python
    # Fail closed: a registry that violates the ADR-6 family-inequality
    # invariant must never boot a worker (FR-204/US-5).
    validate_registry(load_registry())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_worker_registry_gate.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/worker.py tests/test_worker_registry_gate.py
git commit -m "feat(worker): validate agent registry at boot, fail closed (FR-204)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Wire the reviewer into the per-task loop

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (imports ~23-53; `_dev_task` QA/pass block ~466-508; fix-loop feedback ~509; escalation return ~549-558)
- Test: `tests/test_review_wiring.py`

**Interfaces:**
- Consumes: `t_reviewer` (Task 3); `ReviewReport` (Task 1); `PipelineConfig.review_enabled` (Task 1).
- Produces: in `_dev_task`, a `review: ReviewReport | None` computed from the same clean inputs as QA when `cfg.review_enabled`; the success path requires `review is None or review.approve`; review blocking findings join the fix-loop issue text; `TaskResult.review` is populated on both the success and escalation returns.

- [ ] **Step 1: Write the failing test**

Create `tests/test_review_wiring.py`:

```python
import pathlib

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def test_dev_task_runs_reviewer_on_clean_inputs():
    src = SRC.read_text(encoding="utf-8")
    assert "t_reviewer.run(" in src, (
        "_dev_task must run the clean-context reviewer (FR-204)")
    # Reviewer must see the diff patch — the same materialized diff QA sees,
    # never the implementer's narrative.
    idx = src.find("t_reviewer.run(")
    call = src[idx: idx + 400]
    assert "diff['patch']" in call or 'diff["patch"]' in call


def test_review_gated_on_config_flag():
    src = SRC.read_text(encoding="utf-8")
    assert "cfg.review_enabled" in src, (
        "reviewer must be skippable via PipelineConfig.review_enabled")


def test_pass_condition_requires_review_approval():
    src = SRC.read_text(encoding="utf-8")
    assert "review is None or review.approve" in src, (
        "the task success path must require reviewer approval when review ran")


def test_task_result_carries_review():
    src = SRC.read_text(encoding="utf-8")
    assert "review=review" in src, (
        "TaskResult must carry the ReviewReport as merge-gate evidence")


def test_reviewer_imported():
    src = SRC.read_text(encoding="utf-8")
    assert "t_reviewer" in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review_wiring.py -v`
Expected: FAIL — `AssertionError: _dev_task must run the clean-context reviewer`.

- [ ] **Step 3: Import the reviewer**

In `src/sdlc/workflows/feature.py`, add `t_reviewer` to the `from ..agents.roles import (...)` block:

```python
    from ..agents.roles import (
        MODEL, PROMPT_SHAS, t_architect, t_clarify, t_merge_verdict,
        t_planner, t_qa, t_reviewer,
    )
```

- [ ] **Step 4: Run the reviewer and fold it into the pass condition**

In `_dev_task`, locate the block where `qa` is produced from `t_qa.run(...)` (ends ~line 478) followed by the success check `if qa.tests_passed and not qa.issues:`. Insert the reviewer run immediately after `qa` is assigned and change the success guard.

Add right after the `qa = (await t_qa.run(...)).output` assignment:

```python
            # Second clean-context judge (FR-204): same inputs as QA — frozen
            # contract + materialized diff + test output. No narrative, no
            # session. A different model family than the developer (ADR-6).
            review = None
            if cfg.review_enabled:
                review = (await t_reviewer.run(
                    "Frozen contract assertions:\n- " + "\n- ".join(assertions)
                    + f"\nTest results: {qa_raw.model_dump_json()}"
                    + f"\nDiff:\n{diff['patch']}")).output
```

Change the success guard from `if qa.tests_passed and not qa.issues:` to:

```python
            review_ok = review is None or review.approve
            if qa.tests_passed and not qa.issues and review_ok:
```

In the `TaskResult(...)` returned inside that success block, add `review=review`:

```python
                return TaskResult(task_id=task.id, status="done",
                                  attempts=attempt, branch=handle.branch,
                                  run=run, handoff=handoff, qa=qa_raw,
                                  review=review)
```

- [ ] **Step 5: Feed review findings into the fix loop**

Locate `issues = "\n- ".join(qa.issues or qa.failing_tests)` (~line 509). Replace it with:

```python
            review_issues = (
                [f"{f.severity}: {f.assertion} — {f.detail}"
                 for f in review.blocking_findings] if review else [])
            issues = "\n- ".join(
                list(qa.issues or qa.failing_tests) + review_issues)
```

- [ ] **Step 6: Carry the review onto the escalation return**

Locate the escalation `TaskResult(...)` after the fix loop exhausts (the return with `status="done" if decision.approved else "quarantined"`, ~line 551). Add `review=review`:

```python
        return TaskResult(
            task_id=task.id,
            status="done" if decision.approved else "quarantined",
            attempts=cfg.max_fix_attempts + 1,
            branch=handle.branch,
            qa=qa_raw,
            review=review,
            notes=decision.comments or "",
        )
```

- [ ] **Step 7: Run the wiring tests and the workflow-purity guard**

Run: `python -m pytest tests/test_review_wiring.py tests/test_factory_purity.py -v`
Expected: PASS — wiring assertions hold and the determinism/import-linter guard still passes (the reviewer is a `TemporalAgent`, not a direct call).

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_review_wiring.py
git commit -m "feat(code): run clean-context reviewer in the per-task loop (ADR-6/FR-204)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Advisory review check on the deterministic merge gate

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (merge check assembly ~790-796)
- Test: `tests/test_review_wiring.py` (extend)

**Interfaces:**
- Consumes: `TaskResult.review` (Task 5); `build_check`, `CheckClass` (already imported in `feature.py`).
- Produces: a `review_severity` **advisory** check in the merge gate's `checks` list, passing iff every task either had review disabled (`review is None`) or was approved.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_review_wiring.py`:

```python
def test_merge_gate_has_review_severity_check():
    src = SRC.read_text(encoding="utf-8")
    assert '"review_severity"' in src, (
        "the deterministic merge gate must consume ReviewReport evidence as "
        "an advisory check (FR-106)")
    idx = src.find('"review_severity"')
    block = src[idx: idx + 220]
    assert "CheckClass.ADVISORY" in block, "review check must be advisory"
    assert "r.review is None or r.review.approve" in block, (
        "review check passes iff every task was approved or had review off")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review_wiring.py::test_merge_gate_has_review_severity_check -v`
Expected: FAIL — `AssertionError: the deterministic merge gate must consume ReviewReport evidence`.

- [ ] **Step 3: Add the advisory check**

In `feature.py`, locate the `checks = [ ... ]` list built for the merge gate (`build_check("build_integration_green", ...)` and `build_check("lint_clean", ...)`, ~line 790). Append a third element inside that list:

```python
            build_check(
                "review_severity",
                all(r.review is None or r.review.approve
                    for r in done.values()),
                CheckClass.ADVISORY,
                detail="clean-context reviewer blocking findings (FR-204)"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review_wiring.py -v`
Expected: PASS (all wiring tests, including the new merge check).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — no regressions; the merge gate now has three checks and the advisory `review_severity` is human-overridable via the existing merge gate path (`feature.py` §5c), while absolute checks stay terminal (SC-5 untouched).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_review_wiring.py
git commit -m "feat(merge): add advisory review_severity check to the quality gate (FR-106)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- ADR-6 (model-family inequality, clean-context reviewer) → Tasks 2 (validator), 3 (agent), 5 (stage). ✅
- FR-201 (versioned `agents.yaml` registry) → Task 2. ✅
- FR-204 (reviewer clean-context, family-inequality enforced by validator, no session resume) → Tasks 2–5; the reviewer is a proposer with no session (structural). ✅
- FR-106 (deterministic gate consumes review evidence) → Task 6 adds the advisory check; the absolute-floor/security gap is **out of scope** (separate finding #4, audit §7 item 4). ✅ (partial, as scoped)
- FR-105 (review fix loop, default 2) → Task 5 folds review findings into the existing `max_fix_attempts` loop; escalation path reused. ✅
- US-5 (registry rejects same-family dev/reviewer) → Tasks 2 + 4 (boot gate). ✅

**Out of scope (documented, not silently dropped):** the optional harness *deep-review tier* (validator clause exists in Task 2 but no harness reviewer stage is wired); full unification of `PipelineConfig.roles` with `config/agents.yaml` (the workflow still reads `cfg.roles["dev"]` for the developer harness/model — the registry governs the reviewer + boot validation only); populating the gate's `security_no_critical` absolute floor (audit priority #4, its own change).

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every test step shows the command and expected result.

**Type consistency:** `ReviewReport`/`ReviewFinding`/`blocking_findings` (Task 1) are used identically in Tasks 5–6; `model_family`/`load_registry`/`validate_registry`/`RegistryError` (Task 2) match their uses in Tasks 3–4; `RoleConfig.kind`/`.harness` optional (Task 1) match the loader's construction and validator (Task 2); `review=review` / `r.review` naming is consistent across Tasks 5–6; `t_reviewer` naming consistent across Tasks 3–5.
