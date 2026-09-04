# One Registry Drives Every Role — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `config/agents.yaml` the single registry that governs every role, so ADR-6's anti-collusion check constrains the model that actually writes code, and so a per-role model change correctly invalidates exactly that stage's memo.

**Architecture:** `agents.yaml` gains eleven roles — three harness-execution roles named as `DevTask.role` names them (`dev`/`test`/`devops`) and eight proposer roles named for their agents. `validate_registry()` checks required roles first, then compares `reviewer`'s model family against `dev`'s (not the unused `developer`'s), then asserts `PipelineConfig.roles`' hardcoded default mirrors the registry's harness roles. `load_registry()` validates before returning. `roles.py` binds each agent to its own role's model and exposes `STAGE_MODELS`, which `_cached_stage` folds into `content_key`.

**Tech Stack:** Python 3.14, Pydantic v2, Pydantic AI (`Agent`/`TemporalAgent`), Temporal, PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-07-16-registry-drives-every-role-design.md`

## Global Constraints

- **`PipelineConfig` is constructed inside the Temporal workflow** (`feature.py:602`). Nothing reachable from `PipelineConfig()` may perform file I/O — no `default_factory` reading `agents.yaml`. This is why the mirror-check exists instead of a single source of truth.
- **The ADR-6 family check must keep biting at boot.** Every change to `validate_registry` is additive to it. `worker.py:53` stays untouched; `test_worker_registry_gate.py` asserts by source inspection that `validate_registry(` appears before `worker.run()`.
- **Registry role names are fixed by callers:** harness roles must be `dev`, `test`, `devops` because `DevTask.role` is `Literal["dev","test","devops"]` (`models.py:144`), emitted by the planner. Do not rename them.
- **`devops` vs `devops_planner`:** `devops` is the harness role that *runs* devops tasks; `devops_planner` is the proposer that *plans* them (`devops_agent`). Never merge these keys.
- Model ids verbatim: harness roles use `zai-coding-plan/glm-5.2`; proposer roles use `anthropic:glm-5.2`.
- Agent names and toolset ids become Temporal activity names (`roles.py:6`). **Do not rename any `Agent(name=...)`.** This plan changes only the model each agent binds.
- Run tests with `python -m pytest` from the repo root.

---

### Task 1: Registry shape — eleven roles, required-roles check, ADR-6 against `dev`

This is the finding-4 fix: today `validate_registry` compares `reviewer` against `agents.yaml`'s `developer`, but `feature.py:434` resolves `cfg.roles["dev"]` to do the coding, so the check constrains a role that never runs.

**Files:**
- Modify: `config/agents.yaml` (whole file)
- Modify: `src/sdlc/agents/loader.py:46-77` (`validate_registry`)
- Test: `tests/test_agents_registry.py` (whole file)

**Interfaces:**
- Consumes: `RoleConfig` (`models.py:301`), `model_family` (`loader.py:29`), `RegistryError` (`loader.py:23`).
- Produces: `REQUIRED_ROLES: frozenset[str]`, `HARNESS_ROLES: frozenset[str]` in `loader.py`. Registry keys `dev`, `test`, `devops`, `clarify`, `architect`, `planner`, `qa`, `reviewer`, `analyst`, `merge_verdict`, `devops_planner`. Test helper `_complete_registry(**overrides) -> dict[str, RoleConfig]` in `tests/test_agents_registry.py`.

- [ ] **Step 1: Rewrite `config/agents.yaml` with eleven roles**

```yaml
# Versioned agent registry (FR-201). Loaded and validated at worker boot by
# src/sdlc/agents/loader.py, which fails closed on any structural violation.
#
# This file is AUTHORITATIVE. PipelineConfig.roles (models.py) hardcodes a
# mirror of the harness roles below, because PipelineConfig is constructed
# inside the Temporal workflow sandbox and so cannot read this file. The boot
# validator asserts the two agree — drift is a boot failure, not a silent hole.
#
# ADR-6: model_family(reviewer) != model_family(dev). 'dev' is the role that
# actually writes code (feature.py:434), so it is the one the check constrains.
# Editing a model here is configuration, not a code change (US-4/US-5).
version: 1
roles:
  # --- harness-execution roles. Keys are fixed by DevTask.role
  # (Literal["dev","test","devops"], models.py:144) — do not rename.
  # Mirrored by PipelineConfig.roles.
  dev:
    kind: harness
    harness: opencode
    model: zai-coding-plan/glm-5.2
  test:
    kind: harness
    harness: opencode
    model: zai-coding-plan/glm-5.2
  devops:                         # RUNS devops tasks; see devops_planner below
    kind: harness
    harness: opencode
    model: zai-coding-plan/glm-5.2

  # --- proposer roles, bound by agents/roles.py. Clean-context, no tools.
  clarify:
    kind: proposer
    model: anthropic:glm-5.2      # DIFFERENT family than dev (ADR-6)
  architect:
    kind: proposer
    model: anthropic:glm-5.2
  planner:
    kind: proposer
    model: anthropic:glm-5.2
  qa:
    kind: proposer
    model: anthropic:glm-5.2
  reviewer:
    kind: proposer
    model: anthropic:glm-5.2
  analyst:
    kind: proposer
    model: anthropic:glm-5.2
  merge_verdict:
    kind: proposer
    model: anthropic:glm-5.2
  devops_planner:                 # PLANS devops tasks (devops_agent)
    kind: proposer
    model: anthropic:glm-5.2
```

- [ ] **Step 2: Rewrite `tests/test_agents_registry.py`**

The old tests hand-build one- and two-role registries; a required-roles check would make them raise for the wrong reason ("missing clarify" before the assertion under test). The helper fixes that: build a complete valid registry, perturb one field.

```python
import pytest

from sdlc.agents.loader import (
    REQUIRED_ROLES,
    RegistryError,
    load_registry,
    model_family,
    validate_registry,
)
from sdlc.models import HarnessKind, RoleConfig

_HARNESS_MODEL = "zai-coding-plan/glm-5.2"
_PROPOSER_MODEL = "anthropic:glm-5.2"


def _complete_registry(**overrides: RoleConfig) -> dict[str, RoleConfig]:
    """A registry that passes every check. Tests perturb ONE role via
    overrides so each assertion fails for the reason under test."""
    roles: dict[str, RoleConfig] = {
        name: RoleConfig(kind="harness", harness=HarnessKind.OPENCODE, model=_HARNESS_MODEL)
        for name in ("dev", "test", "devops")
    }
    roles.update(
        {
            name: RoleConfig(kind="proposer", model=_PROPOSER_MODEL)
            for name in (
                "clarify",
                "architect",
                "planner",
                "qa",
                "reviewer",
                "analyst",
                "merge_verdict",
                "devops_planner",
            )
        }
    )
    roles.update(overrides)
    return roles


def test_model_family_splits_on_colon_and_slash():
    assert model_family("anthropic:glm-5.2") == "anthropic"
    assert model_family("zai-coding-plan/glm-5.2") == "zai-coding-plan"
    assert model_family("OpenAI/gpt-5.2") == "openai"


def test_complete_registry_helper_is_itself_valid():
    validate_registry(_complete_registry())  # must not raise


def test_shipped_registry_loads_and_validates():
    roles = load_registry()  # default config/agents.yaml
    assert REQUIRED_ROLES <= set(roles)
    validate_registry(roles)  # must not raise


@pytest.mark.parametrize("missing", sorted(REQUIRED_ROLES))
def test_each_required_role_is_required(missing):
    roles = _complete_registry()
    del roles[missing]
    with pytest.raises(RegistryError, match=missing):
        validate_registry(roles)


def test_same_family_dev_and_reviewer_rejected():
    roles = _complete_registry(reviewer=RoleConfig(kind="proposer", model="zai-coding-plan/other"))
    with pytest.raises(RegistryError, match="family"):
        validate_registry(roles)


def test_adr6_checks_dev_not_a_bystander_role():
    """Finding 4 regression. Before this change the check compared reviewer
    against a 'developer' entry that never ran, while cfg.roles['dev'] did the
    coding. A registry where the REAL developer collides with the reviewer must
    now fail."""
    roles = _complete_registry(
        dev=RoleConfig(
            kind="harness", harness=HarnessKind.OPENCODE, model="anthropic:some-coder"
        ),  # same family as reviewer
    )
    with pytest.raises(RegistryError, match="family"):
        validate_registry(roles)


def test_different_family_accepted():
    validate_registry(_complete_registry())  # no raise


def test_deep_review_harness_reviewer_must_differ_from_developer():
    roles = _complete_registry(
        reviewer=RoleConfig(kind="harness", harness=HarnessKind.OPENCODE, model=_PROPOSER_MODEL)
    )
    with pytest.raises(RegistryError, match="harness"):
        validate_registry(roles)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_agents_registry.py -v`
Expected: FAIL — `ImportError: cannot import name 'REQUIRED_ROLES'`.

- [ ] **Step 4: Replace `validate_registry` in `src/sdlc/agents/loader.py`**

Replace the whole function (currently `:46-77`) and add the two frozensets below `DEFAULT_AGENTS_CONFIG`:

```python
# Harness-execution roles. Keys fixed by DevTask.role
# (Literal["dev","test","devops"], models.py:144). PipelineConfig.roles
# mirrors exactly this set — see _validate_pipeline_mirror.
HARNESS_ROLES = frozenset({"dev", "test", "devops"})

# Proposer roles, one per agent in agents/roles.py. 'devops_planner' PLANS
# devops tasks; the 'devops' harness role above RUNS them.
PROPOSER_ROLES = frozenset(
    {
        "clarify",
        "architect",
        "planner",
        "qa",
        "reviewer",
        "analyst",
        "merge_verdict",
        "devops_planner",
    }
)

REQUIRED_ROLES = HARNESS_ROLES | PROPOSER_ROLES
```

```python
def validate_registry(roles: dict[str, RoleConfig]) -> None:
    """Fail closed on any structural violation.

    Checks run in this order deliberately: a missing role is reported as
    itself, before any downstream check trips over its absence.

    The ADR-6 invariant is model-family inequality between the reviewer and
    'dev' — the role feature.py:434 resolves to actually write code. (It is
    NOT harness inequality; that clause applies only to the optional
    deep-review harness reviewer tier.)
    """
    missing = sorted(REQUIRED_ROLES - set(roles))
    if missing:
        raise RegistryError(f"registry is missing required role(s): {', '.join(missing)}")
    for name in ("dev", "reviewer"):
        if roles[name].model is None:
            raise RegistryError(f"role '{name}' must declare a model")
    dev, rev = roles["dev"], roles["reviewer"]
    if model_family(dev.model) == model_family(rev.model):
        raise RegistryError(
            f"ADR-6 violation: reviewer family '{model_family(rev.model)}' "
            f"equals the family of 'dev' — anti-collusion review requires a "
            f"different model family than the developer's authoring model"
        )
    if rev.kind == "harness" and rev.harness is not None and rev.harness == dev.harness:
        raise RegistryError(
            "deep-review harness reviewer must use a different harness than the developer"
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_agents_registry.py -v`
Expected: PASS, including the 11 parametrized `test_each_required_role_is_required` cases.

- [ ] **Step 6: Fix the reviewer test's stale role name**

`tests/test_reviewer_agent.py:23-27` reads `reg["developer"]`, which no longer exists. Replace `test_reviewer_model_family_differs_from_developer` with:

```python
def test_reviewer_model_family_differs_from_dev():
    """The bound reviewer model must be a different family than the model that
    actually writes code — the ADR-6 invariant. 'dev' (not 'developer') is what
    feature.py:434 resolves for coding tasks."""
    reg = load_registry()
    assert model_family(reg["reviewer"].model) != model_family(reg["dev"].model)
    # the agent actually binds that reviewer model
    assert reg["reviewer"].model in roles.reviewer_agent.model.model_id
```

- [ ] **Step 7: Run the full suite to catch other `developer` readers**

Run: `python -m pytest -q`
Expected: PASS. If anything else reads `registry["developer"]`, update it to `"dev"` — the name is gone.

- [ ] **Step 8: Commit**

```bash
git add config/agents.yaml src/sdlc/agents/loader.py tests/test_agents_registry.py tests/test_reviewer_agent.py
git commit -m "fix(registry): ADR-6 checks 'dev' — the role that actually codes

validate_registry compared reviewer against agents.yaml's 'developer', but
feature.py:434 resolves cfg.roles['dev'] to do the coding. The checked role
never ran. Rename developer -> dev, add a required-roles check that reports a
missing role as itself, and declare all eleven roles."
```

---

### Task 2: `load_registry` fails closed

Finding 3: `roles.py:38` calls `load_registry()["reviewer"]` at **import** time, but `validate_registry` runs at boot (`worker.py:53`) *after* `worker.py:35` imports the agents. A bad registry dies with a raw `KeyError` and never reaches the validator built to explain it.

**Files:**
- Modify: `src/sdlc/agents/loader.py:36-44` (`load_registry`)
- Test: `tests/test_agents_registry.py` (append)

**Interfaces:**
- Consumes: `validate_registry`, `REQUIRED_ROLES` from Task 1.
- Produces: `_parse(path) -> dict[str, RoleConfig]` (unvalidated, private). `load_registry(path=None)` keeps its signature and returns only validated registries.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agents_registry.py`:

```python
def _write_registry(tmp_path, body: str):
    cfg = tmp_path / "agents.yaml"
    cfg.write_text(body, encoding="utf-8")
    return cfg


def _yaml_for(roles: dict[str, RoleConfig]) -> str:
    lines = ["version: 1", "roles:"]
    for name, r in roles.items():
        lines.append(f"  {name}:")
        lines.append(f"    kind: {r.kind}")
        if r.harness is not None:
            lines.append(f"    harness: {r.harness.value}")
        lines.append(f"    model: {r.model}")
    return "\n".join(lines) + "\n"


def test_load_registry_via_env_override(tmp_path, monkeypatch):
    cfg = _write_registry(tmp_path, _yaml_for(_complete_registry()))
    monkeypatch.setenv("SDLC_AGENTS_CONFIG", str(cfg))
    roles = load_registry()
    assert roles["reviewer"].model == _PROPOSER_MODEL
    assert roles["reviewer"].harness is None


def test_load_registry_raises_registry_error_not_keyerror(tmp_path, monkeypatch):
    """An incomplete registry must fail through the validator that explains
    it, not as a KeyError from the first caller to index it."""
    partial = _complete_registry()
    del partial["clarify"]
    cfg = _write_registry(tmp_path, _yaml_for(partial))
    monkeypatch.setenv("SDLC_AGENTS_CONFIG", str(cfg))
    with pytest.raises(RegistryError, match="clarify"):
        load_registry()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_agents_registry.py -k "env_override or keyerror" -v`
Expected: `test_load_registry_raises_registry_error_not_keyerror` FAILS — `load_registry` returns the incomplete dict without raising. (`test_load_registry_via_env_override` should already pass.)

- [ ] **Step 3: Split parse from load in `src/sdlc/agents/loader.py`**

Replace `load_registry` (`:36-44`) with:

```python
def _parse(path: str | os.PathLike | None = None) -> dict[str, RoleConfig]:
    """Parse the registry YAML into {role_name: RoleConfig}, UNVALIDATED.
    Resolution order: explicit arg, then $SDLC_AGENTS_CONFIG, then the shipped
    default. Private: callers must go through load_registry, which validates."""
    resolved = Path(path or os.environ.get(AGENTS_CONFIG_ENV) or DEFAULT_AGENTS_CONFIG)
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    roles_raw = data.get("roles") or {}
    return {name: RoleConfig(**cfg) for name, cfg in roles_raw.items()}


def load_registry(path: str | os.PathLike | None = None) -> dict[str, RoleConfig]:
    """Parse AND validate. No unvalidated registry escapes this module, so
    roles.py's import-time call fails with a RegistryError explaining the
    problem rather than a KeyError from whichever role it indexed first."""
    roles = _parse(path)
    validate_registry(roles)
    return roles
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_agents_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS. `worker.py:53`'s `validate_registry(load_registry())` now validates twice — harmless, and it stays because `test_worker_registry_gate.py` asserts the boot gate by source inspection.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/agents/loader.py tests/test_agents_registry.py
git commit -m "fix(registry): load_registry validates before returning

roles.py loads the registry at import, before worker.py:53's boot validation
runs, so a bad registry died with a raw KeyError and never reached the
validator built to explain it."
```

---

### Task 3: The mirror-check — guard the duplication `PipelineConfig` purity forces

Finding 5: `PipelineConfig()` is constructed inside the workflow (`feature.py:602`), so its `roles` default cannot read `agents.yaml` without putting file I/O in the Temporal sandbox. The duplication stays; the boot validator makes drift fail closed.

**Files:**
- Modify: `src/sdlc/models.py:448-456` (`PipelineConfig.roles` default)
- Modify: `src/sdlc/agents/loader.py` (add `_validate_pipeline_mirror`, call from `validate_registry`)
- Test: `tests/test_registry_mirror.py` (create)

**Interfaces:**
- Consumes: `HARNESS_ROLES`, `RegistryError`, `validate_registry` from Task 1.
- Produces: `_validate_pipeline_mirror(roles: dict[str, RoleConfig]) -> None` in `loader.py`, called as `validate_registry`'s last check. `PipelineConfig().roles` keys become exactly `{"dev", "test", "devops"}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry_mirror.py`:

```python
"""PipelineConfig.roles is a hardcoded mirror of agents.yaml's harness roles.

It must be hardcoded: PipelineConfig() is constructed inside the workflow
(feature.py:602), so a default_factory reading agents.yaml would put file I/O
in the Temporal sandbox. The mirror-check makes drift a boot failure instead of
a silent divergence — which is exactly how ADR-6 came to validate a role that
never ran.
"""

import pytest

from sdlc.agents.loader import HARNESS_ROLES, RegistryError, validate_registry
from sdlc.models import HarnessKind, PipelineConfig, RoleConfig

from test_agents_registry import _complete_registry


def test_pipeline_default_roles_are_exactly_the_harness_roles():
    assert set(PipelineConfig().roles) == HARNESS_ROLES


def test_shipped_registry_and_pipeline_default_agree():
    from sdlc.agents.loader import load_registry

    validate_registry(load_registry())  # must not raise


def test_registry_drifting_from_pipeline_default_is_rejected():
    """A different-family model keeps ADR-6 satisfied, so this fails on the
    mirror and nothing else."""
    roles = _complete_registry(
        dev=RoleConfig(
            kind="harness", harness=HarnessKind.OPENCODE, model="zai-coding-plan/some-other-coder"
        )
    )
    with pytest.raises(RegistryError, match="mirror"):
        validate_registry(roles)


def test_mirror_error_names_the_role_and_both_values():
    roles = _complete_registry(
        test=RoleConfig(
            kind="harness", harness=HarnessKind.OPENCODE, model="zai-coding-plan/drifted"
        )
    )
    with pytest.raises(RegistryError) as exc:
        validate_registry(roles)
    assert "test" in str(exc.value)
    assert "zai-coding-plan/drifted" in str(exc.value)
    assert "zai-coding-plan/glm-5.2" in str(exc.value)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_registry_mirror.py -v`
Expected: FAIL — `ImportError: cannot import name 'HARNESS_ROLES'` is already resolved by Task 1, so expect `test_pipeline_default_roles_are_exactly_the_harness_roles` to FAIL (default still has a `reviewer` key) and the drift tests to FAIL (no mirror check yet).

- [ ] **Step 3: Shrink `PipelineConfig.roles`' default in `src/sdlc/models.py`**

Replace `:448-456`. The `reviewer` entry is dead config — the reviewer is a proposer bound from `agents.yaml` at `roles.py` import and never reads `cfg.roles`.

```python
# Harness-execution roles ONLY (keys match DevTask.role). This is a
# hardcoded MIRROR of agents.yaml's harness roles, not a second registry:
# PipelineConfig is constructed inside the workflow (feature.py:602), so
# this default cannot read the file. agents/loader.py asserts the two agree
# at boot. Change one, change both, or the worker won't start.
roles: dict[str, RoleConfig] = Field(
    default_factory=lambda: {
        "dev": RoleConfig(harness=HarnessKind.OPENCODE, model="zai-coding-plan/glm-5.2"),
        "test": RoleConfig(harness=HarnessKind.OPENCODE, model="zai-coding-plan/glm-5.2"),
        "devops": RoleConfig(harness=HarnessKind.OPENCODE, model="zai-coding-plan/glm-5.2"),
    }
)
```

- [ ] **Step 4: Add the mirror-check to `src/sdlc/agents/loader.py`**

Add the function, and call it as the last line of `validate_registry`:

```python
def _validate_pipeline_mirror(roles: dict[str, RoleConfig]) -> None:
    """agents.yaml is authoritative; PipelineConfig.roles is a purity-mandated
    mirror of its harness roles (see the note on PipelineConfig.roles). Drift
    between them is what let ADR-6 validate a role that never ran, so it fails
    the worker at boot."""
    from ..models import PipelineConfig  # local: avoid an import cycle at

    # module scope via models -> ...
    default_roles = PipelineConfig().roles
    if set(default_roles) != HARNESS_ROLES:
        raise RegistryError(
            f"PipelineConfig.roles must mirror exactly the harness roles "
            f"{sorted(HARNESS_ROLES)}; it has {sorted(default_roles)}"
        )
    for name in sorted(HARNESS_ROLES):
        reg, dflt = roles[name], default_roles[name]
        if (reg.kind, reg.harness, reg.model) != (dflt.kind, dflt.harness, dflt.model):
            raise RegistryError(
                f"PipelineConfig.roles['{name}'] does not mirror agents.yaml: "
                f"registry has (kind={reg.kind}, harness={reg.harness}, "
                f"model={reg.model}); PipelineConfig default has "
                f"(kind={dflt.kind}, harness={dflt.harness}, "
                f"model={dflt.model})"
            )
```

Append to `validate_registry`, after the harness-reviewer clause:

```python
    _validate_pipeline_mirror(roles)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_registry_mirror.py tests/test_agents_registry.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS. If a test asserted `cfg.roles["reviewer"]`, it was asserting dead config — delete that assertion.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/models.py src/sdlc/agents/loader.py tests/test_registry_mirror.py
git commit -m "fix(registry): assert PipelineConfig.roles mirrors agents.yaml at boot

PipelineConfig is built inside the workflow, so its roles default cannot read
the registry without breaking sandbox purity. Keep the duplication, guard it:
drift is now a boot failure. Drop the dead cfg.roles['reviewer'] entry."
```

---

### Task 4: Proposers bind their own role; `STAGE_MODELS` and the `PROMPT_SHAS` gaps

Finding 2: `content_key` takes a `model_id`, and every cached stage passes the same `MODEL` constant. Harmless only while all proposers share one model — the moment a role gets its own, the memo key wouldn't move and the stage would serve a result computed by the previous model.

**Files:**
- Modify: `src/sdlc/agents/roles.py:34-38` (constants), `:139-204` (agent constructors), `:206-214` (`PROMPT_SHAS`)
- Test: `tests/test_stage_models.py` (create)

**Interfaces:**
- Consumes: `load_registry` from Task 2; registry role names from Task 1.
- Produces, all in `roles.py`: `REGISTRY: dict[str, RoleConfig]`, `STAGE_ROLES: dict[str, str]`, `STAGE_MODELS: dict[str, str]`, `PROMPT_SHAS: dict[str, str]` (now 8 keys). **`MODEL` is deleted** — Task 5 fixes its importers.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stage_models.py`:

```python
"""Each stage's model is an input to its memo key (FR-103).

Without this, changing one role's model in agents.yaml leaves content_key
unmoved and that stage serves a cache entry computed by the PREVIOUS model.
The hardcoded MODEL constant masked this by making every stage share a model.
"""

from sdlc.agents import roles
from sdlc.memoization.cache import content_key


def test_stage_models_and_prompt_shas_span_the_same_keyspace():
    """Both are keyed by stage name and looked up together in _cached_stage.
    If they disagree about what a stage is, one of them KeyErrors at runtime."""
    assert roles.STAGE_MODELS.keys() == roles.PROMPT_SHAS.keys()


def test_prompt_shas_cover_every_stage_including_qa_and_merge_verdict():
    for stage in (
        "clarify",
        "architect",
        "plan",
        "devops",
        "review",
        "analyze",
        "qa",
        "merge_verdict",
    ):
        assert stage in roles.PROMPT_SHAS
        assert len(roles.PROMPT_SHAS[stage]) == 64  # sha256 hex digest


def test_model_constant_is_gone():
    """A fleet-wide default is the drift this increment removes; an alias
    would let new code keep reaching for it."""
    assert not hasattr(roles, "MODEL")


def test_every_stage_model_comes_from_its_registry_role():
    for stage, role in roles.STAGE_ROLES.items():
        assert roles.STAGE_MODELS[stage] == roles.REGISTRY[role].model


def test_agents_bind_their_own_roles_model():
    assert roles.REGISTRY["reviewer"].model in roles.reviewer_agent.model.model_id
    assert roles.REGISTRY["analyst"].model in roles.analyst_agent.model.model_id
    assert roles.REGISTRY["clarify"].model in roles.clarify_agent.model.model_id


def test_changing_one_roles_model_moves_only_that_stages_key():
    """The finding-2 regression test: per-role models MUST be per-stage memo
    inputs."""

    def key_for(stage: str, model: str) -> str:
        return content_key(stage, "{}", roles.PROMPT_SHAS[stage], model, "none")

    before = key_for("architect", roles.STAGE_MODELS["architect"])
    after = key_for("architect", "some-other-family/other-model")
    assert before != after, "architect's memo key must move when its model does"

    # a different stage's key is untouched by architect's model
    clarify_before = key_for("clarify", roles.STAGE_MODELS["clarify"])
    clarify_after = key_for("clarify", roles.STAGE_MODELS["clarify"])
    assert clarify_before == clarify_after
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_stage_models.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.agents.roles' has no attribute 'STAGE_MODELS'`.

- [ ] **Step 3: Replace the constants block in `src/sdlc/agents/roles.py`**

Replace `MODEL` and `REVIEWER_MODEL` (`:34-38`) with:

```python
# The registry (FR-201) is the single source of every role's model. It is
# loaded AND validated here at import (loader.load_registry validates), so a
# registry violating ADR-6 cannot even import this module, let alone boot a
# worker. There is deliberately no fleet-wide default model constant: a role's
# model comes from its own registry entry or the registry is incomplete and
# fails closed.
REGISTRY = load_registry()


def _model(role: str) -> str:
    """The model this role declares. KeyError is unreachable — REQUIRED_ROLES
    is checked during load_registry above."""
    return REGISTRY[role].model
```

- [ ] **Step 4: Point every agent at its own role**

In each `Agent(...)` constructor (`:139-204`), replace the first positional argument. **Do not touch any `name=`** — agent names are Temporal activity names (`roles.py:6`).

```python
clarify_agent = Agent(
    _model("clarify"),
    name="clarify_agent",
    ...
architect_agent = Agent(
    _model("architect"),
    name="architect_agent",
    ...
planner_agent = Agent(
    _model("planner"),
    name="planner_agent",
    ...
qa_analyst_agent = Agent(
    _model("qa"),
    name="qa_analyst_agent",
    ...
reviewer_agent = Agent(
    _model("reviewer"),
    name="reviewer_agent",
    ...
analyst_agent = Agent(
    _model("analyst"),
    name="analyst_agent",
    ...
merge_verdict_agent = Agent(
    _model("merge_verdict"),
    name="merge_verdict_agent",
    ...
devops_agent = Agent(
    _model("devops_planner"),
    name="devops_agent",
    ...
```

- [ ] **Step 5: Replace the `PROMPT_SHAS` block with the three stage-keyed maps**

Replace `:206-214`:

```python
# Stage name -> registry role. Stage names (feature.py's pipeline vocabulary)
# and role names (the registry's) genuinely differ — 'plan'/'planner',
# 'review'/'reviewer', 'analyze'/'analyst', 'devops'/'devops_planner'. This
# table is the ONE place that divergence is reconciled.
STAGE_ROLES: dict[str, str] = {
    "clarify": "clarify",
    "architect": "architect",
    "plan": "planner",
    "devops": "devops_planner",
    "review": "reviewer",
    "analyze": "analyst",
    "qa": "qa",
    "merge_verdict": "merge_verdict",
}

# Both maps are keyed by stage and looked up together in _cached_stage. Keep
# their keyspaces identical (tests/test_stage_models.py asserts it).
STAGE_MODELS: dict[str, str] = {stage: _model(role) for stage, role in STAGE_ROLES.items()}

_STAGE_PROMPTS: dict[str, str] = {
    "clarify": CLARIFY_PROMPT,
    "architect": ARCHITECT_PROMPT,
    "plan": PLAN_PROMPT,
    "devops": DEVOPS_PROMPT,
    "review": REVIEWER_PROMPT,
    "analyze": ANALYST_PROMPT,
    "qa": QA_PROMPT,
    "merge_verdict": MERGE_VERDICT_PROMPT,
}

PROMPT_SHAS: dict[str, str] = {
    stage: hashlib.sha256(prompt.encode()).hexdigest() for stage, prompt in _STAGE_PROMPTS.items()
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python -m pytest tests/test_stage_models.py -v`
Expected: PASS.

- [ ] **Step 7: Run the suite — `feature.py` still imports `MODEL` and will fail**

Run: `python -m pytest -q`
Expected: FAIL with `ImportError: cannot import name 'MODEL' from 'sdlc.agents.roles'`. That is Task 5. Do not patch it here; do not re-add `MODEL`.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/agents/roles.py tests/test_stage_models.py
git commit -m "feat(registry): every proposer binds its own role's model

Delete the fleet-wide MODEL constant; add STAGE_MODELS so a stage's real model
becomes a content_key input (FR-103), and fill the missing qa/merge_verdict
PROMPT_SHAS entries. feature.py wiring follows."
```

---

### Task 5: Wire `STAGE_MODELS` through the workflow

Closes the FR-103 bug end to end and stops the benchmark records asserting an author model no registry chose.

**Files:**
- Modify: `src/sdlc/workflows/feature.py:25-27` (imports), `:229-262` (`_judge`), `:293-303` (`_cached_stage`), `:641-643`, `:662`, `:668`, `:690-693`, `:699`, `:706`, `:729-732`, `:737`, `:744`, `:842`, `:1005`
- Test: `tests/test_memoization_wiring.py`

**Interfaces:**
- Consumes: `STAGE_MODELS`, `PROMPT_SHAS` from Task 4.
- Produces: `_cached_stage(self, cfg, stage, input_json, output_type, run_fn)` — **`model_id` parameter removed**. `_judge(self, cfg, artifact_json, stage, author_model)` — **`author_model` added as a required keyword**.

- [ ] **Step 1: Update the memoization wiring test**

In `tests/test_memoization_wiring.py`, replace `test_prompt_shas_cover_the_four_cached_stages` and add a guard that no hardcoded model literal survives:

```python
from sdlc.agents.roles import PROMPT_SHAS, STAGE_MODELS


def test_prompt_shas_cover_the_cached_stages():
    for stage in ("clarify", "architect", "plan", "devops"):
        assert stage in PROMPT_SHAS
        assert len(PROMPT_SHAS[stage]) == 64  # sha256 hex digest


def test_cached_stage_resolves_the_model_itself(feature_class):
    """_cached_stage looks up STAGE_MODELS[stage] internally, mirroring its
    PROMPT_SHAS[stage] lookup — one resolution point, so the two stage-keyed
    maps cannot disagree about what a stage is."""
    methods = _methods(feature_class)
    src = ast.unparse(methods["_cached_stage"])
    assert "STAGE_MODELS[stage]" in src
    assert "PROMPT_SHAS[stage]" in src


def test_no_hardcoded_model_literals_in_the_workflow():
    """Five benchmark records hardcoded the author model, so they lied the
    moment any role's model changed. The registry is the only source."""
    source = FEATURE_PY.read_text(encoding="utf-8")
    assert "anthropic:glm-5.2" not in source
    assert "zai-coding-plan/glm-5.2" not in source
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_memoization_wiring.py -v`
Expected: FAIL — collection fails on `ImportError: cannot import name 'MODEL'` (from Task 4's `feature.py` import).

- [ ] **Step 3: Fix the import at `src/sdlc/workflows/feature.py:25-27`**

Replace `MODEL` with `STAGE_MODELS` in the import list:

```python
    from ..agents.roles import (
        PROMPT_SHAS, STAGE_MODELS, t_analyst, t_architect, t_clarify,
```

(Keep every other name in that import exactly as it is.)

- [ ] **Step 4: Drop `model_id` from `_cached_stage` (`:293-303`)**

```python
async def _cached_stage(
    self, cfg: PipelineConfig, stage: str, input_json: str, output_type: type, run_fn
) -> tuple[object, bool]:
    """Skips `run_fn()` (a no-arg async callable invoking the proposer
    agent) when an identical (stage, input, prompt, model,
    upstream-recall-watermark) combination was already computed — the
    ADR-5 dev-loop cache. Returns (output, was_cache_hit).

    The stage's model is resolved here from STAGE_MODELS rather than passed
    in: it MUST be the model that role actually binds, or a role's model
    change would leave the key unmoved and serve a result computed by the
    previous model."""
    if not cfg.memoization_enabled:
        return await run_fn(), False
    key = content_key(
        stage, input_json, PROMPT_SHAS[stage], STAGE_MODELS[stage], self._memory_watermark or "none"
    )
```

(The rest of the method body is unchanged.)

- [ ] **Step 5: Update the three `_cached_stage` call sites**

`:641-643`:

```python
reqs, _ = await self._cached_stage(
    cfg, "clarify", idea.model_dump_json(), ClarifiedRequirements, _run_clarify
)
```

`:690-693`:

```python
arch, _ = await self._cached_stage(
    cfg, "architect", reqs.model_dump_json() + (guidance or ""), ArchitectureSpec, _produce
)
```

`:729-732`:

```python
plan, _ = await self._cached_stage(
    cfg, "plan", arch.model_dump_json() + (guidance or ""), ImplementationPlan, _produce
)
```

- [ ] **Step 6: Give `_judge` an explicit `author_model` (`:229-262`)**

Its `stage` parameter is a **rubric key** (`"clarifier"`, `"architect"`, `"planner"`) — a third keyspace, per its own docstring at `:240` — so it cannot index `STAGE_MODELS`. The caller knows both names and passes the author in.

Change the signature and drop the stale docstring paragraph at `:243-247`:

```python
    async def _judge(self, cfg: PipelineConfig, artifact_json: str,
                     stage: str, author_model: str) -> QualityScore:
```

Replace that docstring paragraph with:

```
        Author model: passed in by the caller, which knows both this rubric key
        and the stage name STAGE_MODELS is keyed by. The judge_model (e.g.
        'openai/gpt-5.2') differs from the author → ADR-6 cross-family satisfied.
```

And at `:256`:

```python
author_model = (author_model,)
```

- [ ] **Step 7: Update the three `_judge` call sites**

`:662`, `:699`, `:737` respectively:

```python
_quality = await self._judge(
    cfg, reqs.model_dump_json(), "clarifier", author_model=STAGE_MODELS["clarify"]
)
```

```python
_quality = await self._judge(
    cfg, arch.model_dump_json(), "architect", author_model=STAGE_MODELS["architect"]
)
```

```python
_quality = await self._judge(
    cfg, plan.model_dump_json(), "planner", author_model=STAGE_MODELS["plan"]
)
```

- [ ] **Step 8: Replace the five hardcoded record literals**

Each is a `model="anthropic:glm-5.2"` argument to `self._stage_record(...)`. Replace by line, using that record's stage:

- `:668` (clarify record) → `model=STAGE_MODELS["clarify"]))`
- `:706` (architecture record) → `model=STAGE_MODELS["architect"]))`
- `:744` (plan record) → `model=STAGE_MODELS["plan"]))`
- `:842` (analyze record) → `model=STAGE_MODELS["analyze"]))`
- `:1005` (merge-verdict record) → `model=STAGE_MODELS["merge_verdict"]))`

Also `:519` — `model=role_cfg.model or "zai-coding-plan/glm-5.2"` — drop the fallback literal. `role_cfg` comes from `cfg.roles`, whose default is now mirror-checked against the registry, so a `None` model there is a boot failure, not something to paper over at runtime:

```python
model = (role_cfg.model,)
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python -m pytest tests/test_memoization_wiring.py tests/test_factory_purity.py -v`
Expected: PASS.

- [ ] **Step 10: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS. Check `tests/fakes/canned.py:82` and `tests/test_analyst_wiring.py` if anything still references `MODEL`.

- [ ] **Step 11: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_memoization_wiring.py
git commit -m "fix(memoization): a stage's real model is its memo key input (FR-103)

_cached_stage passed one hardcoded MODEL constant as content_key's model_id
for every stage. Per-role models without per-stage model_id means a role's
model change leaves the key unmoved and serves a stale-model result. Also
replaces five hardcoded author-model literals in the benchmark records."
```

---

### Task 6: Roadmap amendments

The tracker records ADR-6 and US-5 as complete on the strength of a check aimed at a role that never ran. §9 records what we've *decided to build*, so it must reflect what this increment learned.

**Files:**
- Modify: `ROADMAP.md` — §2 (FR-103, FR-201), §5 (US-5), §6 (ADR-6), §7, §8 item 7, §9.1, §9.3, §9.7

- [ ] **Step 1: Amend §6 ADR-6 and §5 US-5**

§6 ADR-6 line:

```markdown
- [x] **ADR-6** Anti-collusion review (model-family inequality, clean-context reviewer) — *the boot check validated `agents.yaml`'s `developer` entry, which nothing ran; `cfg.roles["dev"]` did the coding. Re-aimed at `dev` and the two registries mirror-checked at boot (`2026-07-16-registry-drives-every-role`).*
```

§5 US-5 line:

```markdown
- [x] **US-5** dev/reviewer different model family; registry rejects same-family — enforced at boot, against `dev` (the role that actually codes) since `2026-07-16-registry-drives-every-role`.
```

- [ ] **Step 2: Amend §2 FR-201 and FR-103**

```markdown
- [x] **FR-201** versioned `config/agents.yaml` registry (role/kind/model) — governs all eleven roles (3 harness + 8 proposer); `PipelineConfig.roles` is a purity-mandated mirror asserted at boot.
```

```markdown
- [x] **FR-103** memoization, per-run watermark, audit-record-always-kept (`memoization/cache.py`, `content_key`, `_cached_stage`) — each stage's memo key now carries *its own* role's model (`STAGE_MODELS`), so a per-role model change invalidates exactly that stage.
```

- [ ] **Step 3: Rewrite §9.1's preamble and E-1/E-2/E-3**

Replace the §9.1 preamble paragraph (the one beginning "Today a role's definition is split") with:

```markdown
Today a role's definition is split: `config/agents.yaml` carries `kind`/`model`/`harness`,
while prompts are inline Python constants hashed into `PROMPT_SHAS`. §7 records this as known
drift.

**The memoization argument for consolidating has been withdrawn.** E-3 was written on the
theory that prompt files would *become* content-addressed memo inputs. They already are:
`content_key` takes a `prompt_sha` and `PROMPT_SHAS` hashes the prompt text, so editing a
prompt already invalidates exactly its stage. Moving that text into `instructions.md` hashes
the same bytes. E-1/E-2 remain justified by §7's prompts-as-assets drift and by E-4's eval
loop — but they are filing, which is what E-3's own note warned against.

The real gap E-3 pointed at was the *model*, not the prompt, and it turned out to sit on top
of an ADR-6 hole. Closed by `docs/superpowers/specs/2026-07-16-registry-drives-every-role-design.md`.
```

Replace the E-1, E-2, E-3 items:

```markdown
- [ ] **E-1** `agents/<role>/` directory loader — `load_registry()` walks a directory (`agent.yaml` + `instructions.md`) instead of parsing one file. *Migration must be a strict refactor: same `RoleConfig`, same boot failure on a same-family pairing, same mirror-check against `PipelineConfig.roles`.* **Re-ranked down**: with the memoization payoff already banked, this is reorganisation.
- [ ] **E-2** Move inline prompt constants out of `agents/roles.py` into `agents/<role>/instructions.md`; `PROMPT_SHAS` derives from file content rather than a Python literal. Blocked on E-1.
- [x] **E-3** ~~Wire prompt-file content into `content_key`~~ — **the prompt half was already wired before the item was written** (`content_key(prompt_sha=...)` + `PROMPT_SHAS`). The *model* half was the real gap: every stage passed one hardcoded `MODEL` constant as `content_key`'s `model_id`, so per-role models would have served stale-model cache hits. Closed together with the ADR-6 hole (§9.1 preamble); `STAGE_MODELS` now resolves each stage's real model.
```

- [ ] **Step 4: Add E-26 to §9.3**

§9.3 is where cross-cutting registry/config items live alongside E-25. Append:

```markdown
- [ ] **E-26** Make `cfg.roles` genuinely per-project (US-4) without reintroducing drift. `PipelineConfig.roles` is a hardcoded mirror of `agents.yaml`'s harness roles because `PipelineConfig()` is constructed *inside* the workflow (`feature.py:602`), so its default cannot read the file without breaking sandbox purity. The boot mirror-check makes drift fail closed, but it also means a per-project override must resolve at the boundary (`cli.py`, `benchmarks/workflow.py`) and satisfy ADR-6 *per run*, not just at boot. **Nothing populates `cfg.roles` today**, which is the only reason the mirror can be a static assertion.
```

- [ ] **Step 5: Update §8 item 7 and §9.7's ordering**

§8 item 7 — replace with:

```markdown
7. **Repo hardening via agents-as-folders** — closes §7's prompts-as-assets drift. Tasks: **E-1, E-2, E-4** (§9.1). *Re-ranked down*: the memoization payoff that justified it was already banked (see §9.1), and the ADR-6 hole it sat next to is closed. Cheapest self-contained item on this list, but now purely reorganisation.
```

§9.7 — replace ordering item 2:

```markdown
2. ~~**E-1 → E-2 → E-3**~~ — superseded. E-3's payoff was already wired; its model half plus an ADR-6 hole (the boot check validated a role that never ran) closed by `2026-07-16-registry-drives-every-role`. E-1/E-2 remain as reorganisation, no longer ranked here.
```

- [ ] **Step 6: Update the header's "Last verified" line**

```markdown
| Last verified | 2026-07-16 (against `src/sdlc/`, `interfaces/`, `tests/`, `config/`) |
```

Leave the date as is — it is already 2026-07-16 — but append to the §0 note block above §1, after the existing paragraph:

```markdown
> **2026-07-16 — ADR-6 correction.** The anti-collusion check was validating `config/agents.yaml`'s `developer` role, which nothing ever ran; `cfg.roles["dev"]` (a second, hardcoded registry in `models.py`) selected the coding model. The invariant held only while two hardcoded lists agreed. `agents.yaml` is now the single registry, the check compares `reviewer` against `dev`, and `PipelineConfig.roles` is asserted at boot to mirror it. Prior `[x]` marks on ADR-6/US-5 were true of the mechanism, not of the pairing it constrained.
```

- [ ] **Step 7: Verify the tracker's claims against the code**

Run: `python -m pytest -q`
Expected: PASS — the tracker's §2/§5/§6 claims are only as good as the suite that holds them.

- [ ] **Step 8: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): record the ADR-6 correction; withdraw E-3's premise

ADR-6/US-5 were [x] on a check aimed at a role that never ran. E-3's
memoization argument was already satisfied before the item was written, which
re-ranks E-1/E-2 down to reorganisation. Adds E-26 for per-project cfg.roles."
```

---

## Verification

- [ ] `python -m pytest -q` — full suite green.
- [ ] `python -c "from sdlc.agents import roles; print(roles.STAGE_MODELS)"` — prints eight stages, no import error, proving the registry loads and validates at import.
- [ ] Temporarily set `reviewer`'s model in `config/agents.yaml` to `zai-coding-plan/anything` and run `python -c "import sdlc.worker"`. Expected: `RegistryError` naming the ADR-6 family violation. **Revert the edit.** This is the invariant the increment exists to protect — confirm it bites by observation, not by assumption.
- [ ] Temporarily change `dev`'s model in `config/agents.yaml` to `zai-coding-plan/other` and run the same import. Expected: `RegistryError` naming the mirror mismatch against `PipelineConfig.roles`. **Revert the edit.**
