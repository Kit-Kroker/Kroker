# E-37 Per-role Model Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a benchmark case (via named *arms*) and the CLI (via `--role-model`) override each role's model per run, so the "frontier architect + cheap developer" economics probe is expressible, with ADR-6 enforced per run instead of only at boot.

**Architecture:** Role→model resolution moves from the frozen `STAGE_MODELS` constant to a per-run resolver that prefers `cfg.roles[role].model`. A shared ADR-6 model-family check (`check_adr6_families`) is reused by the existing boot validator and a new per-run validator (`validate_run_roles`), called at the two boundaries that construct a non-default config (benchmark `_cell_config`, CLI `start`). Cases express the sweep as a list of `Arm`s (role→model mixes); the matrix is `harnesses × arms`.

**Tech Stack:** Python 3.12, Pydantic v2, Temporal (`temporalio`), pytest. Package root `src/sdlc/`, tests in `tests/`.

## Global Constraints

- **ADR-6 (model-family inequality):** `dev` and `reviewer` must be different model families; if `deep_review` is present it must differ in family from `dev`. This holds per run, not only at boot.
- **Memoization correctness (E-3 lesson):** any content-addressed memo key MUST use the model that actually ran; a per-role model change must move the key.
- **Determinism:** workflow code (`workflows/feature.py`, `benchmarks/workflow.py`) may read module-level constants (`STAGE_MODELS`, `STAGE_ROLES`) but performs no file I/O. `load_registry()` (file I/O) is only allowed in `cli.py`/activities, never in workflow context.
- **Registry role names are the keys.** `cfg.roles` and `Arm.role_models` use registry role names: harness roles `dev`/`test`/`devops`; proposer roles `clarify`/`architect`/`planner`/`qa`/`reviewer`/`analyst`/`merge_verdict`/`devops_planner`; optional `deep_review`. (Note stage `plan`→role `planner`, stage `review`→role `reviewer`, stage `analyze`→role `analyst`, stage `devops`→role `devops_planner`.)
- **Backward compat:** an existing `CaseSpec` using `models: [...]` and no `arms` must expand exactly as before (harness roles swept, proposers untouched).
- Run the full suite with `python -m pytest -q` from the repo root. Single test: `python -m pytest tests/test_x.py::test_y -v`.

---

### Task 1: Per-run role→model resolver + memo-key fix

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (add `STAGE_ROLES` to the import block at lines 26-30; add module-level `resolve_role_model`; change memo key at line 383-385)
- Test: `tests/test_role_model_resolution.py` (create)

**Interfaces:**
- Produces: `resolve_role_model(cfg: PipelineConfig, stage: str) -> str` — returns `cfg.roles[role].model` when the run overrides that role, else `STAGE_MODELS[stage]`, where `role = STAGE_ROLES[stage]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_role_model_resolution.py
from sdlc.models import PipelineConfig, RoleConfig
from sdlc.workflows.feature import resolve_role_model
from sdlc.memoization.cache import content_key


def test_resolver_falls_back_to_registry_default():
    cfg = PipelineConfig()  # no proposer overrides
    # architect stage default comes from STAGE_MODELS (registry)
    from sdlc.agents.roles import STAGE_MODELS

    assert resolve_role_model(cfg, "architect") == STAGE_MODELS["architect"]


def test_resolver_prefers_per_run_override():
    cfg = PipelineConfig()
    cfg.roles["architect"] = RoleConfig(kind="proposer", model="openai/gpt-5.2")
    assert resolve_role_model(cfg, "architect") == "openai/gpt-5.2"


def test_resolver_maps_stage_to_role_name():
    # stage 'plan' resolves through role 'planner'
    cfg = PipelineConfig()
    cfg.roles["planner"] = RoleConfig(kind="proposer", model="openai/gpt-5.2")
    assert resolve_role_model(cfg, "plan") == "openai/gpt-5.2"


def test_memo_key_moves_with_per_role_model():
    base = PipelineConfig()
    override = PipelineConfig()
    override.roles["architect"] = RoleConfig(kind="proposer", model="openai/gpt-5.2")
    k_base = content_key("architect", "{}", "sha", resolve_role_model(base, "architect"), "none")
    k_over = content_key(
        "architect", "{}", "sha", resolve_role_model(override, "architect"), "none"
    )
    assert k_base != k_over
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_role_model_resolution.py -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_role_model'`.

- [ ] **Step 3: Add `STAGE_ROLES` to the import and define the resolver**

In `src/sdlc/workflows/feature.py`, extend the existing import (lines 26-30) to include `STAGE_ROLES`:

```python
from ..agents.roles import (
    PROMPT_SHAS,
    STAGE_MODELS,
    STAGE_ROLES,
    t_analyst,
    t_architect,
    t_clarify,
    t_deep_review,
    t_merge_verdict,
    t_planner,
    t_qa,
    t_research,
    t_reviewer,
)
```

Add this module-level function immediately after the imports block (before the workflow class), so it is importable and callable from workflow code:

```python
def resolve_role_model(cfg: "PipelineConfig", stage: str) -> str:
    """The model this run uses for `stage`. A per-run override in cfg.roles
    (keyed by the registry ROLE name) wins; otherwise the registry default
    (STAGE_MODELS[stage]). Keyed by stage because STAGE_ROLES is the one place
    stage↔role divergence is reconciled."""
    role = STAGE_ROLES[stage]
    rc = cfg.roles.get(role)
    if rc is not None and rc.model is not None:
        return rc.model
    return STAGE_MODELS[stage]
```

- [ ] **Step 4: Fix the memo key to use the resolved model**

In `_cached_stage` (around line 383), replace `STAGE_MODELS[stage]` with the resolver and update the docstring line that claims the model comes from `STAGE_MODELS`:

```python
key = content_key(
    stage,
    input_json,
    PROMPT_SHAS[stage],
    resolve_role_model(cfg, stage),
    self._memory_watermark or "none",
)
```

Update the docstring sentence at lines 377-380 to: `The stage's model is resolved per-run (resolve_role_model): a per-role override MUST move the key, or a stale result computed by a different model would be served.`

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_role_model_resolution.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_role_model_resolution.py
git commit -m "feat(workflow): per-run role->model resolver + memo-key fix (E-37)"
```

---

### Task 2: Route every proposer call site through the resolver

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (all `STAGE_MODELS[...]` proposer call sites: lines 519, 521, 534, 763, 764, 802, 810, 1094, 1097, 1136, 1142, 1158, 1197, 1208, 1215, 1230, 1240, 1250, 1257, 1340, 1341, 1354, 1549)
- Test: `tests/test_role_model_resolution.py` (add a grep-style guard test)

**Interfaces:**
- Consumes: `resolve_role_model` (Task 1).
- Produces: no new symbol; every proposer stage now records and runs the *resolved* model so `RoleUsage.model` / `BenchmarkRecord.model` / `author_model` match what actually executed.

- [ ] **Step 1: Write the failing guard test**

```python
# add to tests/test_role_model_resolution.py
import re
from pathlib import Path


def test_no_raw_stage_models_lookup_in_feature_workflow():
    """Every proposer model reference must go through resolve_role_model so
    per-run overrides and the memo key stay consistent. The only allowed raw
    STAGE_MODELS[...] is inside resolve_role_model itself."""
    src = Path("src/sdlc/workflows/feature.py").read_text(encoding="utf-8")
    # strip the resolver body (the one legitimate raw lookup)
    src_wo_resolver = re.sub(
        r"def resolve_role_model.*?return STAGE_MODELS\[stage\]", "", src, flags=re.DOTALL
    )
    assert "STAGE_MODELS[" not in src_wo_resolver
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_role_model_resolution.py::test_no_raw_stage_models_lookup_in_feature_workflow -v`
Expected: FAIL (many `STAGE_MODELS[` occurrences remain).

- [ ] **Step 3: Replace each proposer call site**

In `src/sdlc/workflows/feature.py`, replace `STAGE_MODELS["<stage>"]` with `resolve_role_model(cfg, "<stage>")` at every listed line. `cfg` is in scope in each of these methods. Concretely, the stages and their occurrences:

- `deep_review`: lines 519, 521, 534 → `resolve_role_model(cfg, "deep_review")`
- `qa`: lines 763, 764, 802, 810 → `resolve_role_model(cfg, "qa")`
- `clarify`: lines 1094, 1097, 1136, 1142 → `resolve_role_model(cfg, "clarify")`
- `architect`: lines 1158, 1197, 1208, 1215 → `resolve_role_model(cfg, "architect")`
- `plan`: lines 1230, 1240, 1250, 1257 → `resolve_role_model(cfg, "plan")`
- `analyze`: lines 1340, 1341, 1354 → `resolve_role_model(cfg, "analyze")`
- `devops`: line 1549 (`STAGE_MODELS["devops"]`) → `resolve_role_model(cfg, "devops")`

Do NOT change the raw `STAGE_MODELS[stage]` inside `resolve_role_model` (it is the fallback). Line 384's memo key was already handled in Task 1.

Note: these methods already pass `cfg` (e.g. `self._run_role(cfg, "architect", STAGE_MODELS["architect"], ...)` becomes `self._run_role(cfg, "architect", resolve_role_model(cfg, "architect"), ...)`). Verify `cfg` is the parameter name in each method; it is throughout `feature.py`.

- [ ] **Step 4: Run the guard test + full suite**

Run: `python -m pytest tests/test_role_model_resolution.py -v && python -m pytest -q`
Expected: guard test PASS; full suite PASS (no behavior change when no overrides are set — resolver returns the same `STAGE_MODELS` value).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_role_model_resolution.py
git commit -m "feat(workflow): route proposer model refs through resolve_role_model (E-37)"
```

---

### Task 3: Shared ADR-6 family check + per-run validator

**Files:**
- Modify: `src/sdlc/agents/loader.py` (extract `check_adr6_families`, add `validate_run_roles`, refactor `validate_registry` to reuse the helper — lines ~200-222)
- Test: `tests/test_run_roles_validation.py` (create)

**Interfaces:**
- Produces:
  - `check_adr6_families(role_models: dict[str, str]) -> None` — raises `RegistryError` if `dev`/`reviewer` share a family, or if `deep_review` (when present) shares `dev`'s family. Requires `dev` and `reviewer` keys.
  - `validate_run_roles(role_models: dict[str, str]) -> None` — the per-run boundary entry point; delegates to `check_adr6_families`.
- Consumes (in later tasks): both, from `sdlc.agents.loader`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_roles_validation.py
import pytest

from sdlc.agents.loader import RegistryError, validate_run_roles


def test_passes_when_families_differ():
    validate_run_roles({"dev": "zai-coding-plan/glm-5.2", "reviewer": "openai/gpt-5.2"})  # no raise


def test_rejects_dev_reviewer_same_family():
    with pytest.raises(RegistryError, match="ADR-6"):
        validate_run_roles(
            {"dev": "anthropic:claude-opus-4-8", "reviewer": "anthropic:claude-haiku-4-5"}
        )


def test_rejects_deep_review_sharing_dev_family():
    with pytest.raises(RegistryError, match="deep_review"):
        validate_run_roles(
            {
                "dev": "anthropic:claude-opus-4-8",
                "reviewer": "openai/gpt-5.2",
                "deep_review": "anthropic:claude-haiku-4-5",
            }
        )


def test_deep_review_absent_is_fine():
    validate_run_roles(
        {"dev": "zai-coding-plan/glm-5.2", "reviewer": "openai/gpt-5.2"}
    )  # no deep_review key, no raise


def test_missing_dev_or_reviewer_raises():
    with pytest.raises(RegistryError):
        validate_run_roles({"dev": "zai-coding-plan/glm-5.2"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_roles_validation.py -v`
Expected: FAIL with `ImportError: cannot import name 'validate_run_roles'`.

- [ ] **Step 3: Add the shared helper and per-run validator**

In `src/sdlc/agents/loader.py`, add these two functions (near `validate_registry`):

```python
def check_adr6_families(role_models: dict[str, str]) -> None:
    """The ADR-6 model-family inequality invariant, over a resolved
    role->model map. `dev` and `reviewer` must differ in family; if
    `deep_review` is present it must differ from `dev`. This is the single
    implementation reused at boot (validate_registry) and per run
    (validate_run_roles)."""
    dev = role_models.get("dev")
    rev = role_models.get("reviewer")
    if dev is None or rev is None:
        raise RegistryError("ADR-6 check requires both 'dev' and 'reviewer' models")
    if model_family(dev) == model_family(rev):
        raise RegistryError(
            f"ADR-6 violation: reviewer family '{model_family(rev)}' "
            f"equals the family of 'dev' — anti-collusion review requires a "
            f"different model family than the developer's authoring model"
        )
    dr = role_models.get("deep_review")
    if dr is not None and model_family(dr) == model_family(dev):
        raise RegistryError(
            f"ADR-6 violation: deep_review family '{model_family(dr)}' "
            f"equals the family of 'dev' — the transcript lens must not "
            f"correlate with the authoring model"
        )


def validate_run_roles(role_models: dict[str, str]) -> None:
    """Per-run ADR-6 enforcement at a boundary that constructs a non-default
    role→model map (benchmark arm, CLI --role-model). Registry-structural
    checks (harness inequality, research provider) stay at boot; this guards
    only what a per-run override can break: model-family inequality."""
    check_adr6_families(role_models)
```

- [ ] **Step 4: Refactor `validate_registry` to reuse the helper**

In `validate_registry`, replace the inline dev/reviewer/deep_review family logic (currently lines ~200-222) with a call to `check_adr6_families`, keeping the model-presence guards and the harness-inequality check (which is registry-structural, not model-family):

```python
for name in ("dev", "reviewer"):
    if roles[name].model is None:
        raise RegistryError(f"role '{name}' must declare a model")
dev, rev = roles["dev"], roles["reviewer"]
role_models = {"dev": dev.model, "reviewer": rev.model}
if "deep_review" in roles:
    if roles["deep_review"].model is None:
        raise RegistryError("role 'deep_review' must declare a model")
    role_models["deep_review"] = roles["deep_review"].model
check_adr6_families(role_models)
if rev.kind == "harness" and rev.harness is not None and rev.harness == dev.harness:
    raise RegistryError(
        "deep-review harness reviewer must use a different harness than the developer"
    )
```

- [ ] **Step 5: Run the new test + existing registry tests**

Run: `python -m pytest tests/test_run_roles_validation.py tests/test_agents_registry.py tests/test_registry_mirror.py tests/test_worker_registry_gate.py -v`
Expected: PASS (new validator works; existing ADR-6 boot behavior and messages unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/agents/loader.py tests/test_run_roles_validation.py
git commit -m "feat(loader): shared ADR-6 family check + validate_run_roles (E-37)"
```

---

### Task 4: `Arm` model + `CaseSpec.arms` + `BenchmarkCell` fields

**Files:**
- Modify: `src/sdlc/benchmarks/models.py` (add `Arm`; add `arms` to `CaseSpec`; add `arm_name`/`role_models` to `BenchmarkCell` and update `cell_id`)
- Test: `tests/test_benchmark_arms.py` (create)

**Interfaces:**
- Produces:
  - `Arm(name: str, default: str | None = None, role_models: dict[str, str] = {})` with `Arm.resolve() -> dict[str, str]`:
    - if `default is None`: returns a copy of `role_models` (only named roles overridden).
    - if `default` is set: every overridable role (`HARNESS_ROLES | PROPOSER_ROLES`) mapped to `default`, then `role_models` applied on top.
  - `CaseSpec.arms: list[Arm]` (default `[]`).
  - `BenchmarkCell.arm_name: str`, `BenchmarkCell.role_models: dict[str, str]`; `cell_id == f"{case_id}#{harness.value}#{arm_name}"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_benchmark_arms.py
from sdlc.benchmarks.models import Arm, BenchmarkCell, CaseSpec
from sdlc.models import HarnessKind


def test_arm_resolve_named_only():
    arm = Arm(
        name="frontier-arch",
        role_models={"architect": "anthropic:claude-opus-4-8", "dev": "zai-coding-plan/glm-5.2"},
    )
    assert arm.resolve() == {
        "architect": "anthropic:claude-opus-4-8",
        "dev": "zai-coding-plan/glm-5.2",
    }


def test_arm_resolve_default_fills_all_overridable_roles():
    arm = Arm(
        name="all-cheap",
        default="zai-coding-plan/glm-5.2",
        role_models={"reviewer": "openai/gpt-5.2"},
    )
    resolved = arm.resolve()
    # every harness + proposer role present
    assert resolved["dev"] == "zai-coding-plan/glm-5.2"
    assert resolved["architect"] == "zai-coding-plan/glm-5.2"
    assert resolved["devops_planner"] == "zai-coding-plan/glm-5.2"
    # role_models wins over default
    assert resolved["reviewer"] == "openai/gpt-5.2"


def test_cell_id_uses_arm_name():
    cell = BenchmarkCell(
        case_id="c1",
        harness=HarnessKind.OPENCODE,
        arm_name="frontier-arch",
        role_models={"dev": "zai-coding-plan/glm-5.2"},
    )
    assert cell.cell_id == "c1#opencode#frontier-arch"


def test_casespec_arms_default_empty():
    spec = CaseSpec(
        case_id="c1",
        idea_summary="x",
        harnesses=[HarnessKind.OPENCODE],
        models=["m"],
        judge_model="openai/gpt-5.2",
    )
    assert spec.arms == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_benchmark_arms.py -v`
Expected: FAIL with `ImportError: cannot import name 'Arm'`.

- [ ] **Step 3: Implement `Arm` and wire the model fields**

In `src/sdlc/benchmarks/models.py`, add near the top (after imports):

```python
from ..agents.loader import HARNESS_ROLES, PROPOSER_ROLES


class Arm(BaseModel):
    """A named role→model mix: one cell of the model×role sweep. `default`
    (optional) sets the model for every overridable role; `role_models`
    overrides specific roles and wins over `default`. Roles left unset (with
    `default=None`) keep the registry default at run time."""

    name: str
    default: str | None = None
    role_models: dict[str, str] = Field(default_factory=dict)

    def resolve(self) -> dict[str, str]:
        if self.default is None:
            return dict(self.role_models)
        base = {r: self.default for r in (HARNESS_ROLES | PROPOSER_ROLES)}
        base.update(self.role_models)
        return base
```

Add to `CaseSpec` (after `extra_args_by_model`):

```python
    # E-37: named role→model mixes. Each arm is one cell (crossed with
    # harnesses). When empty, `models` is desugared to one arm per model
    # (harness roles only) for backward compatibility — see expand_matrix.
    arms: list[Arm] = Field(default_factory=list)
```

Update `BenchmarkCell`:

```python
class BenchmarkCell(BaseModel):
    """One cell of the matrix: a (case, harness, arm) triple to execute."""

    case_id: str
    harness: HarnessKind
    arm_name: str
    role_models: dict[str, str] = Field(default_factory=dict)

    @property
    def cell_id(self) -> str:
        return f"{self.case_id}#{self.harness.value}#{self.arm_name}"
```

Note: `_GIT_UNSAFE` sanitisation now applies to `arm_name` at authoring time (arm names should be git-safe slugs); keep the existing `_GIT_UNSAFE` import only if still referenced elsewhere, otherwise remove it to avoid an unused import.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_benchmark_arms.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run existing benchmark model tests**

Run: `python -m pytest tests/test_benchmark_models.py -v`
Expected: PASS, OR failures pointing only at the removed `BenchmarkCell.model` field — those are fixed in Task 5 (expansion) and are expected here. If `test_benchmark_models.py` constructs `BenchmarkCell(model=...)`, update those constructions to the new `arm_name`/`role_models` shape in this step and re-run.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/benchmarks/models.py tests/test_benchmark_arms.py tests/test_benchmark_models.py
git commit -m "feat(benchmarks): Arm model + CaseSpec.arms + arm-keyed BenchmarkCell (E-37)"
```

---

### Task 5: `expand_matrix` over arms + judge guard + backward-compat desugar

**Files:**
- Modify: `src/sdlc/benchmarks/matrix.py`
- Test: `tests/test_benchmark_matrix.py` (extend existing)

**Interfaces:**
- Consumes: `Arm`, `CaseSpec`, `BenchmarkCell` (Task 4).
- Produces: `expand_matrix(spec: CaseSpec) -> list[BenchmarkCell]` — desugars `models`→arms when `spec.arms` is empty; validates `judge_model` family differs from every model explicitly named across all arms; emits `harnesses × arms` cells carrying each arm's resolved `role_models`.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_benchmark_matrix.py
from sdlc.benchmarks.models import Arm


def _spec_arms(arms, harnesses=None, judge="openai/gpt-5.2"):
    return CaseSpec(
        case_id="c1",
        idea_summary="x",
        harnesses=harnesses or [HarnessKind.OPENCODE],
        models=[],
        arms=arms,
        judge_model=judge,
        rubrics={},
    )


def test_arms_cross_harnesses():
    spec = _spec_arms(
        [
            Arm(name="a", role_models={"dev": "zai-coding-plan/glm-5.2"}),
            Arm(name="b", role_models={"dev": "openai/gpt-5.2"}),
        ],
        harnesses=[HarnessKind.CLAUDE_CODE, HarnessKind.OPENCODE],
    )
    cells = expand_matrix(spec)
    assert len(cells) == 2 * 2
    assert {c.arm_name for c in cells} == {"a", "b"}


def test_arm_role_models_reach_cell():
    spec = _spec_arms(
        [
            Arm(
                name="a",
                role_models={
                    "architect": "anthropic:claude-opus-4-8",
                    "dev": "zai-coding-plan/glm-5.2",
                },
            )
        ]
    )
    (cell,) = expand_matrix(spec)
    assert cell.role_models["architect"] == "anthropic:claude-opus-4-8"


def test_judge_rejects_family_shared_with_any_arm_model():
    spec = _spec_arms(
        [Arm(name="a", role_models={"architect": "openai/gpt-5.2"})], judge="openai/gpt-5.2"
    )  # judge shares family with an arm producer
    with pytest.raises(SameFamilyJudgeError):
        expand_matrix(spec)


def test_backward_compat_models_desugar_to_harness_arms():
    # old-style spec: models set, arms empty → one arm per model, harness-only
    spec = CaseSpec(
        case_id="c1",
        idea_summary="x",
        harnesses=[HarnessKind.OPENCODE],
        models=["zai-coding-plan/glm-5.2", "openai/gpt-5.2"],
        judge_model="google/gemini-2-pro",
        rubrics={},
    )
    cells = expand_matrix(spec)
    assert len(cells) == 2
    for c in cells:
        # only the 3 harness roles are overridden; no proposer keys
        assert set(c.role_models) == {"dev", "test", "devops"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_benchmark_matrix.py -v`
Expected: FAIL — new tests error (arms unsupported); old `test_full_cross_product` etc. may also fail once `BenchmarkCell(model=...)` is gone.

- [ ] **Step 3: Rewrite `expand_matrix`**

Replace `src/sdlc/benchmarks/matrix.py` with:

```python
"""Expand a CaseSpec into (harness × arm) cells, enforcing the ADR-6
cross-family judge rule: the judge model's family must differ from EVERY
model explicitly named in EVERY arm."""

from __future__ import annotations

from .models import Arm, BenchmarkCell, CaseSpec


class SameFamilyJudgeError(ValueError):
    pass


def _family(model: str) -> str:
    # "anthropic:claude-sonnet-4-6" → "anthropic"; "openai/gpt-5.2" → "openai"
    sep = ":" if ":" in model else "/"
    return model.split(sep, 1)[0].lower()


def _arms_for(spec: CaseSpec) -> list[Arm]:
    if spec.arms:
        return spec.arms
    # backward compat: one arm per model, harness roles only (proposers keep
    # the registry default, exactly as the pre-E-37 uniform sweep did).
    return [
        Arm(
            name=_family(m) + "-" + m.rsplit("/", 1)[-1].rsplit(":", 1)[-1],
            role_models={"dev": m, "test": m, "devops": m},
        )
        for m in spec.models
    ]


def expand_matrix(spec: CaseSpec) -> list[BenchmarkCell]:
    arms = _arms_for(spec)
    judge_family = _family(spec.judge_model)
    # every model a producer role is explicitly set to, across all arms
    author_models = {m for arm in arms for m in arm.resolve().values()}
    author_families = {_family(m) for m in author_models}
    if judge_family in author_families:
        raise SameFamilyJudgeError(
            f"judge model family {judge_family!r} matches a producer model "
            f"family in {sorted(author_families)}; ADR-6 requires the judge "
            f"to differ from every producer family in the matrix"
        )
    return [
        BenchmarkCell(case_id=spec.case_id, harness=h, arm_name=arm.name, role_models=arm.resolve())
        for h in spec.harnesses
        for arm in arms
    ]
```

Note: the desugared arm name must be git-safe and unique per model; the expression above strips any `provider/` or `provider:` prefix and the model tail is used. If two models could collide on that tail, prefer the full `_GIT_UNSAFE`-sanitised model string — but for the current corpus the tail is unique. Keep arm names unique; `test_cell_ids_unique` (below) guards it.

- [ ] **Step 4: Fix the pre-existing matrix tests**

The original tests (`test_full_cross_product`, `test_rejects_same_family_judge`, `test_different_family_judge_ok`, `test_cell_ids_unique`) use `models=[...]` and assert cell counts — they still pass unchanged because desugaring preserves `harnesses × models` counts. Verify `test_cell_ids_unique` still holds; if the two chosen models share a sanitised tail it will fail — in that case widen those models to clearly distinct names. No change expected for the committed fixtures.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_benchmark_matrix.py -v`
Expected: PASS (old + new).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/benchmarks/matrix.py tests/test_benchmark_matrix.py
git commit -m "feat(benchmarks): expand_matrix over arms + judge guard + desugar (E-37)"
```

---

### Task 6: `_cell_config` builds `cfg.roles` from the arm + per-run ADR-6

**Files:**
- Modify: `src/sdlc/benchmarks/workflow.py` (`_cell_config` signature + body; import `STAGE_MODELS`, `validate_run_roles`, `RegistryError`; update the call site at ~line 122)
- Test: `tests/test_cell_config.py` (create)

**Interfaces:**
- Consumes: `BenchmarkCell.role_models` (Task 5), `validate_run_roles` (Task 3), `STAGE_MODELS`.
- Produces: `_cell_config(base, idea, spec, cell, bench_run_id, rubrics=None) -> PipelineConfig` — builds `cfg.roles` (harness roles → `RoleConfig(harness=cell.harness, model=...)`, proposer roles → `RoleConfig(kind="proposer", model=...)`), validates ADR-6 for the resolved (dev, reviewer, deep_review) map, then applies the existing benchmark/gate/research setup.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cell_config.py
import pytest

from sdlc.agents.loader import RegistryError
from sdlc.benchmarks.models import BenchmarkCell, CaseSpec
from sdlc.benchmarks.workflow import _cell_config
from sdlc.models import HarnessKind, IdeaBrief, PipelineConfig, ProjectMode


def _spec():
    return CaseSpec(
        case_id="c1",
        idea_summary="x",
        harnesses=[HarnessKind.OPENCODE],
        models=[],
        judge_model="openai/gpt-5.2",
        rubrics={},
    )


def _idea():
    return IdeaBrief(title="c1", description="x", mode=ProjectMode.GREENFIELD)


def test_cell_config_overrides_proposer_and_harness_roles():
    cell = BenchmarkCell(
        case_id="c1",
        harness=HarnessKind.OPENCODE,
        arm_name="a",
        role_models={"architect": "anthropic:claude-opus-4-8", "dev": "zai-coding-plan/glm-5.2"},
    )
    cfg = _cell_config(PipelineConfig(), _idea(), _spec(), cell, bench_run_id="b1", rubrics={})
    assert cfg.roles["architect"].model == "anthropic:claude-opus-4-8"
    assert cfg.roles["architect"].kind == "proposer"
    assert cfg.roles["dev"].model == "zai-coding-plan/glm-5.2"
    assert cfg.roles["dev"].harness == HarnessKind.OPENCODE


def test_cell_config_rejects_adr6_violating_arm():
    # dev opus + reviewer opus (same family) → ADR-6 breach at the boundary
    cell = BenchmarkCell(
        case_id="c1",
        harness=HarnessKind.OPENCODE,
        arm_name="bad",
        role_models={"dev": "anthropic:claude-opus-4-8", "reviewer": "anthropic:claude-haiku-4-5"},
    )
    with pytest.raises(RegistryError, match="ADR-6"):
        _cell_config(PipelineConfig(), _idea(), _spec(), cell, bench_run_id="b1", rubrics={})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cell_config.py -v`
Expected: FAIL — `_cell_config` still has the old signature (`harness, model`) / no ADR-6 check.

- [ ] **Step 3: Rewrite `_cell_config`**

In `src/sdlc/benchmarks/workflow.py`, add imports inside the existing `workflow.unsafe.imports_passed_through()` block (or top-level import block used by this module):

```python
    from ..agents.loader import validate_run_roles, RegistryError
    from ..agents.roles import STAGE_MODELS
    from ..agents.loader import HARNESS_ROLES
```

Replace `_cell_config` (currently `def _cell_config(base, idea, spec, harness, model, bench_run_id, rubrics=None)`) with:

```python
def _cell_config(
    base: PipelineConfig,
    idea: IdeaBrief,
    spec: CaseSpec,
    cell: BenchmarkCell,
    bench_run_id: str,
    rubrics: dict[str, str] | None = None,
) -> PipelineConfig:
    """Build a per-cell PipelineConfig from the cell's arm: each role in
    role_models is overridden to its model (harness roles carry the cell's
    harness + the base role's context budget / extra args; proposer roles are
    kind='proposer'). ADR-6 is validated for the resolved review roles before
    the cell runs — a violation raises, recording a failed cell rather than a
    silent bad run."""
    cfg = base.model_copy(deep=True)
    resolved = cell.role_models
    roles: dict[str, RoleConfig] = {}
    for role, model in resolved.items():
        if role in HARNESS_ROLES:
            rc = base.roles.get(role)
            roles[role] = RoleConfig(
                harness=cell.harness,
                model=model,
                context_budget_tokens=(rc.context_budget_tokens if rc else 30_000),
                extra_args=list(rc.extra_args) if rc else [],
            )
        else:
            roles[role] = RoleConfig(kind="proposer", model=model)
    cfg.roles = roles

    # Per-run ADR-6 (Task 3): resolve the review roles, defaulting any the arm
    # did not override to the registry model (STAGE_MODELS).
    adr6 = {
        "dev": roles["dev"].model if "dev" in roles else base.roles["dev"].model,
        "reviewer": resolved.get("reviewer", STAGE_MODELS["review"]),
    }
    if "deep_review" in STAGE_MODELS:
        adr6["deep_review"] = resolved.get("deep_review", STAGE_MODELS["deep_review"])
    validate_run_roles(adr6)

    # research provider is a property of the RUN, not the repo (registry keeps
    # provider: fake so CI needs no key); inject the real provider only when a
    # case asked for research.
    cfg.research_enabled = spec.research_enabled
    if spec.research_enabled:
        cfg.roles["research"] = RoleConfig(kind="research", provider="tavily")
    cfg.benchmark = BenchmarkConfig(
        case_id=spec.case_id,
        bench_run_id=bench_run_id,
        rubrics=dict(rubrics or {}),
        judge_model=spec.judge_model,
    )
    cfg.gates = {name: GateConfig(policy=GatePolicy.OFF) for name in cfg.gates}
    cfg.default_gate_policy = GatePolicy.OFF
    return cfg
```

Note: `spec.extra_args_by_model` was previously keyed by the single cell model. With per-role models it no longer has a single model; if the corpus still needs it, apply `spec.extra_args_by_model.get(model, [])` per harness role inside the loop. For this task, fold per-model extra args into the harness-role branch: `extra_args=[*(rc.extra_args if rc else []), *spec.extra_args_by_model.get(model, [])]`.

- [ ] **Step 4: Update the `_cell_config` call site**

In `BenchmarkWorkflow.run` (around line 122), the loop currently iterates and calls `_cell_config(base, idea, spec, cell.harness, cell.model, ...)`. Change to pass the cell:

```python
for cell in cells:
    cfg = _cell_config(base, idea, spec, cell, bench_run_id=bench_run_id, rubrics=rubrics)
    child_id = f"{bench_run_id}/{cell.cell_id}"
    try:
        await workflow.execute_child_workflow(
            FeatureWorkflow.run,
            args=[idea, cfg],
            id=child_id,
            task_queue=workflow.info().task_queue,
        )
    except Exception as e:
        workflow.logger.warning("cell %s failed: %s", child_id, e)
```

The `_oracle_record` call uses `cell.harness`/`cell.model`; replace `base_cell.model` references there with `base_cell.arm_name` (the record's `model` field for the oracle can be the arm name, since an oracle grade is per-cell not per-role). Update `_oracle_record` signature usage accordingly: set `model=base_cell.arm_name` in the `BenchmarkRecord(...)` it builds.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_cell_config.py tests/test_benchmark_workflow.py -v`
Expected: PASS. If `test_benchmark_workflow.py` constructs `_cell_config` with the old signature or references `cell.model`, update those call sites to the cell-based signature / `arm_name`.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/benchmarks/workflow.py tests/test_cell_config.py tests/test_benchmark_workflow.py
git commit -m "feat(benchmarks): _cell_config builds cfg.roles from arm + per-run ADR-6 (E-37)"
```

---

### Task 7: CLI `--role-model` override (US-4 surface)

**Files:**
- Modify: `src/sdlc/cli.py` (add `--role-model` to the `start` subparser at line 93-98; parse + validate + build `cfg.roles` at the `start` handler line 160-172)
- Create: `src/sdlc/cli_roles.py` (pure parse/build helpers — keeps `cli.py` thin and the logic unit-testable)
- Test: `tests/test_cli_role_model.py` (create)

**Interfaces:**
- Consumes: `validate_run_roles` (Task 3), `load_registry`, `HARNESS_ROLES`, `KNOWN_ROLES`.
- Produces:
  - `parse_role_models(pairs: list[str]) -> dict[str, str]` — parses `["role=model", ...]`, raising `ValueError` on malformed entries or unknown role names.
  - `build_role_overrides(overrides: dict[str, str]) -> dict[str, RoleConfig]` — builds `cfg.roles` entries (harness roles keep the default harness; others `kind="proposer"`), after validating ADR-6 against the registry-resolved map.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_role_model.py
import pytest

from sdlc.agents.loader import RegistryError
from sdlc.cli_roles import build_role_overrides, parse_role_models


def test_parse_valid_pairs():
    assert parse_role_models(
        ["architect=anthropic:claude-opus-4-8", "dev=zai-coding-plan/glm-5.2"]
    ) == {"architect": "anthropic:claude-opus-4-8", "dev": "zai-coding-plan/glm-5.2"}


def test_parse_rejects_malformed():
    with pytest.raises(ValueError):
        parse_role_models(["architectopus"])  # no '='


def test_parse_rejects_unknown_role():
    with pytest.raises(ValueError, match="unknown role"):
        parse_role_models(["wizard=openai/gpt-5.2"])


def test_build_overrides_sets_proposer_and_harness():
    roles = build_role_overrides({"architect": "openai/gpt-5.2"})
    assert roles["architect"].kind == "proposer"
    assert roles["architect"].model == "openai/gpt-5.2"


def test_build_overrides_rejects_adr6_violation():
    # force dev into the registry reviewer's family; expect a raise.
    # registry reviewer is a fixed family; dev override sharing it must fail.
    from sdlc.agents.loader import load_registry

    reg = load_registry()
    rev_model = reg["reviewer"].model
    with pytest.raises(RegistryError, match="ADR-6"):
        build_role_overrides({"dev": rev_model})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_role_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.cli_roles'`.

- [ ] **Step 3: Implement the pure helpers**

Create `src/sdlc/cli_roles.py`:

```python
"""Pure helpers for the CLI --role-model override (E-37, US-4). Kept out of
cli.py so the parse/validate/build logic is unit-testable without argparse."""

from __future__ import annotations

from .agents.loader import (
    HARNESS_ROLES,
    KNOWN_ROLES,
    load_registry,
    validate_run_roles,
)
from .models import RoleConfig


def parse_role_models(pairs: list[str]) -> dict[str, str]:
    """Parse ['role=model', ...] into {role: model}. Raises ValueError on a
    missing '=' or an unknown role name."""
    out: dict[str, str] = {}
    for p in pairs:
        if "=" not in p:
            raise ValueError(f"--role-model expects role=model, got {p!r}")
        role, model = p.split("=", 1)
        role, model = role.strip(), model.strip()
        if role not in KNOWN_ROLES:
            raise ValueError(f"unknown role {role!r}; known roles: {sorted(KNOWN_ROLES)}")
        if not model:
            raise ValueError(f"--role-model {role!r} has an empty model")
        out[role] = model
    return out


def build_role_overrides(overrides: dict[str, str]) -> dict[str, RoleConfig]:
    """Validate ADR-6 for the registry-resolved role→model map with these
    overrides applied, then build cfg.roles entries. Harness roles keep the
    registry's default harness; other roles are kind='proposer'."""
    reg = load_registry()
    resolved = {r: rc.model for r, rc in reg.items() if rc.model is not None}
    resolved.update(overrides)
    validate_run_roles(resolved)  # raises RegistryError on ADR-6 breach
    roles: dict[str, RoleConfig] = {}
    for role, model in overrides.items():
        if role in HARNESS_ROLES:
            roles[role] = RoleConfig(harness=reg[role].harness, model=model)
        else:
            roles[role] = RoleConfig(kind="proposer", model=model)
    return roles
```

- [ ] **Step 4: Run helper tests to verify they pass**

Run: `python -m pytest tests/test_cli_role_model.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Wire the flag into `cli.py`**

In `src/sdlc/cli.py`, add to the `start` subparser (after line 98):

```python
s.add_argument(
    "--role-model",
    action="append",
    default=[],
    dest="role_model",
    metavar="ROLE=MODEL",
    help="override a role's model, e.g. --role-model "
    "architect=anthropic:claude-opus-4-8 (repeatable)",
)
```

In the `start` handler (line 160-172), build the config with overrides before starting the workflow:

```python
if args.cmd == "start":
    from .cli_roles import build_role_overrides, parse_role_models

    cfg = PipelineConfig()
    if args.role_model:
        try:
            overrides = parse_role_models(args.role_model)
            cfg.roles.update(build_role_overrides(overrides))
        except Exception as e:  # ValueError / RegistryError
            print(f"invalid --role-model: {e}")
            raise SystemExit(1)
    wf_id = f"feature-{slug(args.title)}"
    handle = await client.start_workflow(
        FeatureWorkflow.run,
        args=[
            IdeaBrief(
                title=args.title,
                description=args.description,
                mode=ProjectMode(args.mode),
                repo_url=args.repo,
            ),
            cfg,
        ],
        id=wf_id,
        task_queue=TASK_QUEUE,
    )
    print(f"started {handle.id}")
    return
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/cli.py src/sdlc/cli_roles.py tests/test_cli_role_model.py
git commit -m "feat(cli): --role-model per-run override with ADR-6 guard (E-37, US-4)"
```

---

### Task 8: Documentation — mark E-37/E-26 landed, answer OQ-B2

**Files:**
- Modify: `ROADMAP.md` (E-37 §9.8; E-26 §9.3; the §9.8 ordering line)
- Modify: `BENCHMARK.md` (§3.2 blocker note; the Model×role axis table row §193-196; OQ-B2 §444-448)

**Interfaces:** none (docs only).

- [ ] **Step 1: Update ROADMAP.md E-37**

Change the `- [ ] **E-37**` bullet to `- [x] **E-37**` and append a `*Landed:*` sentence:

```
*Landed:* per-run `resolve_role_model` (proposers + memo key) + shared
`check_adr6_families`/`validate_run_roles` + named `Arm`s on `CaseSpec`
(harness `models` desugared for back-compat) + fixed-judge-validated-at-
expansion (answers OQ-B2) + `--role-model` CLI surface (folds E-26, US-4).
Spec `docs/superpowers/specs/2026-07-24-per-role-model-sweep-design.md`,
plan `docs/superpowers/plans/2026-07-24-per-role-model-sweep.md`.
```

Mark E-26 (§9.3) `- [x]` with a one-line note that E-37 resolved `cfg.roles` at the CLI and benchmark boundaries with per-run ADR-6.

- [ ] **Step 2: Update BENCHMARK.md**

In §3.2, replace the "Blocker to be honest about" paragraph's conclusion with a note that E-37 landed the boundary resolution and per-run ADR-6, so the full model×role sweep is now expressible via arms. Update the Model×role table row (§196) "Roadmap dependency" cell from "`cfg.roles` not yet per-project — **E-26** blocks per-run overrides" to "landed (E-37): per-cell arms + `--role-model`, ADR-6 per run". Update **OQ-B2** to **ANSWERED**: the judge stays fixed per case and its family is validated at expansion against every producer model in every arm (it does not re-resolve per cell).

- [ ] **Step 3: Verify no stale claims remain**

Run: `grep -n "E-37\|OQ-B2\|E-26" ROADMAP.md BENCHMARK.md`
Expected: E-37 shows `[x]`; E-26 shows `[x]`; OQ-B2 shows ANSWERED.

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md BENCHMARK.md
git commit -m "docs: E-37/E-26 landed, OQ-B2 answered (E-37)"
```

---

## Self-Review

**Spec coverage:**
- §3.1 per-run resolver + memo key → Task 1. ✅
- §3.1 all call sites → Task 2. ✅
- §3.2 `cfg.roles` may carry proposers → Task 4 (`Arm`) + Task 6 (`_cell_config` builds them) + comment; default class-config unchanged so mirror-check untouched. ✅
- §3.3 `validate_run_roles` + shared helper + closes latent hole → Task 3 (helper) + Task 6 (benchmark enforcement rejects the uniform-collision case). ✅
- §3.4 `Arm`/`CaseSpec.arms`/`BenchmarkCell` → Task 4. ✅
- §3.5 expansion + judge guard + desugar → Task 5. ✅
- §3.6 `_cell_config` from arm + validate → Task 6. ✅
- §3.7 CLI `--role-model` → Task 7. ✅
- §5 tests → each task ships its tests (resolver, memo-key-moves, per-run ADR-6, latent-hole regression via `test_cell_config_rejects_adr6_violating_arm`, arm resolution, judge guard, backward compat, CLI). ✅
- §6 out-of-scope (arm report slicing, per-role harness, running a sweep, OQ-E2) → not implemented, as intended. ✅
- §7 three enforcement points → boot (unchanged), benchmark (Task 6), CLI (Task 7). ✅

**Placeholder scan:** No TBD/TODO; every code step shows full code. ✅

**Type consistency:** `resolve_role_model(cfg, stage)` used identically in Tasks 1/2. `check_adr6_families`/`validate_run_roles` take `dict[str,str]` in Tasks 3/6/7. `Arm.resolve() -> dict[str,str]` used in Tasks 4/5/6. `BenchmarkCell.role_models`/`arm_name` defined in Task 4, consumed in Tasks 5/6. `_cell_config(base, idea, spec, cell, bench_run_id, rubrics)` signature consistent between Task 6 definition and call site. `parse_role_models`/`build_role_overrides` consistent Tasks 7. ✅

**Known cross-task follow-through:** Removing `BenchmarkCell.model` (Task 4) forces edits in Tasks 5 (expand), 6 (`_oracle_record` uses `arm_name`), and any test constructing `BenchmarkCell(model=...)` — each is called out in the task that touches it. Run `grep -rn "\.model" src/sdlc/benchmarks/ | grep -i cell` during Task 6 to catch stragglers.
