# Deploy Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace DAG stage 13's hardcoded `make deploy ENV=staging` with a frozen `DeployPlan` → deterministic child `DeploymentWorkflow` (apply → smoke → rollback) → `DeployReport` → human `deploy_failed` gate.

**Architecture:** Contracts in `models.py`; a pure adapter seam in a new `src/sdlc/deploy/` package (compose + script) that produces command strings and never runs a subprocess; four activities that execute them; a child workflow that sequences them and contains no model call; the parent `FeatureWorkflow` awaits the child and owns the HITL gate, because Temporal signals are addressed to the run ID operators actually know.

**Tech Stack:** Python 3.12+, Pydantic v2, `temporalio` (workflows, activities, child workflows, `RetryPolicy`), `pytest` with the existing `slow` / `temporal` / `live` markers, Docker Compose for the one integration test.

**Source spec:** `docs/superpowers/specs/2026-08-06-deploy-contract-design.md`

**Branch:** `feat/deploy-contract` (already checked out)

## Global Constraints

- **Adapters are pure.** A `DeployAdapter` returns command strings and identity only — never runs a subprocess, never touches the network. Execution lives in activities. This mirrors `src/sdlc/toolchain/adapters.py`, which states the same rule.
- **`DeploymentWorkflow` contains no model call.** It is deterministic, joining the quality gate in ARCHITECTURE §2's "never LLM calls" row.
- **A smoke result is never a boolean.** `passed` / `failed` / `errored`. An unreachable service is `errored`, counts as failure for the rollback decision, and is reported distinctly.
- **`deploy.enabled` defaults to `False`.** Nothing existing may start shelling out to Docker when this lands.
- **The `DeployPlan` carries no adapter field.** FR-1105: the adapter is resolved from `PipelineConfig.deploy.adapter`.
- **New module? Re-run `pip install -e .`** — setuptools' editable wheel does not auto-discover new files (README, Develop).
- **Default test run must stay green and Docker-free:** `python -m pytest` excludes `slow` and `temporal`; the new `docker` marker joins that exclusion.
- Commit after every task. Message style: `feat: …` / `test: …`, imperative, no trailing period.

---

### Task 1: Deploy contracts

**Files:**
- Modify: `src/sdlc/models.py` (add near the other artifact contracts; import `model_validator`)
- Test: `tests/test_deploy_contracts.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `FeatureFlag`, `SmokeCheck`, `SmokeState`, `SmokeCheckResult`, `RollbackPolicy`, `DeployPlan`, `DeployReport` — all importable from `sdlc.models`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deploy_contracts.py`:

```python
"""E-67/FR-1104: the deploy contract. A smoke result that was never
observed must not be representable as a pass, and a failed deploy must
account for what happened to the rollback."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.models import (
    DeployPlan,
    DeployReport,
    FeatureFlag,
    RollbackPolicy,
    SmokeCheck,
    SmokeCheckResult,
    SmokeState,
)


def _plan(**over) -> DeployPlan:
    base = dict(
        environment="staging",
        version="v1",
        smoke_checks=[SmokeCheck(name="health", kind="http", path="/health")],
    )
    base.update(over)
    return DeployPlan(**base)


def test_plan_is_frozen_by_default():
    """Same default as ValidationContract.frozen -- the plan gate freezes it."""
    assert _plan().frozen is True


def test_plan_defaults_to_auto_rollback():
    assert _plan().rollback == RollbackPolicy(auto=True, to="previous")


def test_plan_has_no_adapter_field():
    """FR-1105/D-1: the operator picks the adapter, not the planner."""
    assert "adapter" not in DeployPlan.model_fields


def test_http_check_requires_a_path():
    with pytest.raises(ValidationError):
        SmokeCheck(name="health", kind="http", path="")


def test_command_check_requires_a_command():
    with pytest.raises(ValidationError):
        SmokeCheck(name="migrated", kind="command", command="")


def test_passed_result_needs_no_detail():
    assert SmokeCheckResult(name="health", state=SmokeState.PASSED).passed


@pytest.mark.parametrize("state", [SmokeState.FAILED, SmokeState.ERRORED])
def test_non_passing_result_must_explain_itself(state):
    """Mirrors Measurement: a missing observation carries its reason."""
    with pytest.raises(ValidationError):
        SmokeCheckResult(name="health", state=state, detail="   ")


def test_errored_is_not_passed():
    """D-3: 'we could not reach it' is not 'it works'."""
    r = SmokeCheckResult(name="health", state=SmokeState.ERRORED, detail="connection refused")
    assert r.passed is False


def _report(**over) -> DeployReport:
    base = dict(deployed=True, environment="staging", version="v1", adapter="compose")
    base.update(over)
    return DeployReport(**base)


def test_rolled_back_requires_a_target():
    with pytest.raises(ValidationError):
        _report(deployed=False, rolled_back=True, rolled_back_to=None)


def test_failed_deploy_without_rollback_must_say_why():
    with pytest.raises(ValidationError):
        _report(deployed=False, rolled_back=False, rollback_reason="")


def test_failed_deploy_with_no_previous_version_is_representable():
    """First-ever deploy: nothing to restore, and the report says so."""
    r = _report(deployed=False, rolled_back=False, rollback_reason="no previous version to restore")
    assert r.rolled_back is False


def test_flag_is_recorded_not_managed():
    """NG7: name + cohort, nothing else -- we do not build flagging."""
    assert set(FeatureFlag.model_fields) == {"name", "cohort"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deploy_contracts.py -q`
Expected: FAIL — `ImportError: cannot import name 'DeployPlan' from 'sdlc.models'`

- [ ] **Step 3: Add the contracts**

In `src/sdlc/models.py`, extend the pydantic import at the top:

```python
from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)
```

Then append the contracts (place them after `ReviewReport`, alongside the other stage artifacts):

```python
class FeatureFlag(BaseModel):
    """NG7: recorded and exported to the adapter, never managed. The factory
    does not build feature flagging -- it names the flag the customer's own
    system owns."""

    name: str
    cohort: str = "all"


class SmokeCheck(BaseModel):
    """A deterministic, machine-checkable assertion authored BEFORE the code
    exists (D-2), so it tests the requirement rather than the implementation.
    It may not reference an implementation detail the planner could not know
    at plan time -- ports and base URLs come from adapter config."""

    name: str
    kind: Literal["http", "command"]
    path: str = ""  # http: resolved against adapter.endpoint()
    expect_status: int = 200  # http
    command: str = ""  # command: expects exit 0
    timeout_s: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _kind_carries_its_fields(self) -> "SmokeCheck":
        if self.kind == "http" and not self.path.strip():
            raise ValueError("an http smoke check requires a path")
        if self.kind == "command" and not self.command.strip():
            raise ValueError("a command smoke check requires a command")
        return self


class SmokeState(str, Enum):
    PASSED = "passed"
    FAILED = "failed"  # the assertion was evaluated and did not hold
    ERRORED = "errored"  # we could not evaluate it at all


class SmokeCheckResult(BaseModel):
    """Tri-state on purpose (D-3). 'The adapter could not reach the service'
    is not a pass and is not a failed assertion -- collapsing the two is
    E-40's malformed-SARIF-reads-as-clean hole in a new location. Both
    non-passing states carry a reason, exactly as Measurement does."""

    name: str
    state: SmokeState
    detail: str = ""

    @model_validator(mode="after")
    def _failure_explains_itself(self) -> "SmokeCheckResult":
        if self.state is not SmokeState.PASSED and not self.detail.strip():
            raise ValueError(f"{self.state.value} requires a detail")
        return self

    @property
    def passed(self) -> bool:
        return self.state is SmokeState.PASSED


class RollbackPolicy(BaseModel):
    auto: bool = True
    to: Literal["previous"] = "previous"


class DeployPlan(BaseModel):
    """FR-1104. Authored by devops_planner at the planning stage, frozen and
    hashed at the plan gate with ValidationContract.frozen semantics.

    Carries intent, never mechanics, and deliberately has NO adapter field:
    FR-1105 resolves the adapter from PipelineConfig.deploy.
    """

    environment: str
    version: str
    flag: FeatureFlag | None = None
    smoke_checks: list[SmokeCheck] = Field(default_factory=list)
    rollback: RollbackPolicy = Field(default_factory=RollbackPolicy)
    frozen: bool = True


class DeployReport(BaseModel):
    """FR-1104 outcome artifact. `deployed` is earned by passing smoke checks,
    never by a zero exit code."""

    deployed: bool
    environment: str
    version: str
    adapter: str
    endpoint: str = ""
    checks: list[SmokeCheckResult] = Field(default_factory=list)
    rolled_back: bool = False
    rollback_reason: str = ""
    rolled_back_to: str | None = None
    report_ref: ArtifactRef | None = None

    @model_validator(mode="after")
    def _failure_accounts_for_the_rollback(self) -> "DeployReport":
        if self.rolled_back and not self.rolled_back_to:
            raise ValueError("rolled_back requires rolled_back_to")
        if not self.deployed and not self.rolled_back and not self.rollback_reason.strip():
            raise ValueError("a failed deploy must say why it was not rolled back")
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_deploy_contracts.py -q`
Expected: PASS (13 tests)

- [ ] **Step 5: Run the full fast suite for regressions**

Run: `python -m pytest -q`
Expected: PASS — `models.py` gained only additive definitions.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py tests/test_deploy_contracts.py
git commit -m "feat: DeployPlan/DeployReport contracts with tri-state smoke results"
```

---

### Task 2: `PipelineConfig.deploy`

**Files:**
- Modify: `src/sdlc/models.py` (add `DeployConfig`; add the field to `PipelineConfig`, which starts at `models.py:808`)
- Test: `tests/test_deploy_config.py` (create)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `DeployConfig(enabled, adapter, base_url, commands, readiness_timeout_s)` and `PipelineConfig.deploy`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deploy_config.py`:

```python
"""D-9: the deploy stage is opt-in. Nothing that exists today may start
shelling out to Docker when E-67 lands."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.models import DeployConfig, PipelineConfig


def test_deploy_is_disabled_by_default():
    assert PipelineConfig().deploy.enabled is False


def test_compose_is_the_default_adapter():
    """FR-1105 reference adapter."""
    assert PipelineConfig().deploy.adapter == "compose"


def test_unknown_adapter_is_rejected_at_the_boundary():
    with pytest.raises(ValidationError):
        DeployConfig(adapter="kubernetes")


def test_script_adapter_is_available():
    """D-7: a seam with one implementation ossifies into a substrate."""
    assert DeployConfig(adapter="script").adapter == "script"


def test_readiness_timeout_must_be_positive():
    with pytest.raises(ValidationError):
        DeployConfig(readiness_timeout_s=0)


def test_config_round_trips_through_dicts():
    """PipelineConfig is constructed from dicts in benchmark cell config."""
    cfg = PipelineConfig(
        deploy={"enabled": True, "adapter": "script", "commands": {"deploy": "make ship"}}
    )
    assert cfg.deploy.enabled is True
    assert cfg.deploy.commands["deploy"] == "make ship"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deploy_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'DeployConfig'`

- [ ] **Step 3: Add the config**

In `src/sdlc/models.py`, above `class PipelineConfig`:

```python
class DeployConfig(BaseModel):
    """FR-1105: the hosting target is an adapter resolved from configuration,
    not a choice an agent makes. Off by default (D-9)."""

    enabled: bool = False
    adapter: Literal["compose", "script"] = "compose"
    # compose: base URL http smoke checks resolve against. The port is a
    # deployment fact the planner cannot know at plan time, so it lives here
    # rather than in the frozen DeployPlan.
    base_url: str | None = None
    # script: overrides for the deploy/rollback/version make targets.
    commands: dict[str, str] = Field(default_factory=dict)
    readiness_timeout_s: int = Field(default=60, ge=1)
```

Then inside `PipelineConfig`, next to `research: ResearchConfig`:

```python
    deploy: DeployConfig = Field(default_factory=DeployConfig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_deploy_config.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/models.py tests/test_deploy_config.py
git commit -m "feat: PipelineConfig.deploy, off by default"
```

---

### Task 3: Pure deploy adapters

**Files:**
- Create: `src/sdlc/deploy/__init__.py`
- Create: `src/sdlc/deploy/adapters.py`
- Test: `tests/test_deploy_adapters.py` (create)

**Interfaces:**
- Consumes: `DeployPlan`, `FeatureFlag` (Task 1); `DeployConfig` (Task 2).
- Produces: `DeployKind`, `DeployAdapter`, `ComposeAdapter`, `ScriptAdapter`, `ADAPTERS`, `resolve(cfg) -> DeployAdapter`. Adapter methods: `apply_cmd(plan)`, `current_version_cmd(plan)`, `rollback_cmd(plan, to_version)`, `endpoint(plan)`, `env(plan, version=None)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deploy_adapters.py`:

```python
"""FR-1105/ADR-19. The adapter object is PURE -- command strings and identity
only, never a subprocess. Same rule and same shape as toolchain/adapters.py."""

from __future__ import annotations

import pytest

from sdlc.deploy.adapters import (
    ADAPTERS,
    ComposeAdapter,
    DeployKind,
    ScriptAdapter,
    resolve,
)
from sdlc.models import DeployConfig, DeployPlan, FeatureFlag


def _plan(**over) -> DeployPlan:
    base = dict(environment="staging", version="v2")
    base.update(over)
    return DeployPlan(**base)


def test_registry_holds_both_adapters():
    """D-7: two implementations keep the seam from ossifying."""
    assert set(ADAPTERS) == {DeployKind.COMPOSE, DeployKind.SCRIPT}


def test_resolve_reads_the_config_not_the_plan():
    assert isinstance(resolve(DeployConfig(adapter="compose")), ComposeAdapter)
    assert isinstance(resolve(DeployConfig(adapter="script")), ScriptAdapter)


def test_env_carries_environment_and_version():
    env = resolve(DeployConfig()).env(_plan())
    assert env["DEPLOY_ENV"] == "staging"
    assert env["DEPLOY_VERSION"] == "v2"


def test_env_omits_flag_keys_when_there_is_no_flag():
    env = resolve(DeployConfig()).env(_plan())
    assert "DEPLOY_FLAG" not in env
    assert "DEPLOY_COHORT" not in env


def test_env_exports_the_flag_when_present():
    """NG7: exported for the customer's own flag system to read."""
    env = resolve(DeployConfig()).env(_plan(flag=FeatureFlag(name="sso", cohort="beta")))
    assert env["DEPLOY_FLAG"] == "sso"
    assert env["DEPLOY_COHORT"] == "beta"


def test_env_version_override_targets_the_rollback_tag():
    """Rollback must run with the PRIOR version in the environment, not the
    one we just tried to ship."""
    env = resolve(DeployConfig()).env(_plan(), version="v1")
    assert env["DEPLOY_VERSION"] == "v1"


def test_compose_tags_the_image_from_the_version():
    env = ComposeAdapter(DeployConfig()).env(_plan(), version="v1")
    assert env["IMAGE_TAG"] == "v1"


def test_compose_apply_builds_and_waits():
    cmd = ComposeAdapter(DeployConfig()).apply_cmd(_plan())
    assert "docker compose up" in cmd and "--build" in cmd


def test_compose_rollback_does_not_rebuild():
    """The prior image already exists; rebuilding it would re-run the
    failing build we are escaping from."""
    cmd = ComposeAdapter(DeployConfig()).rollback_cmd(_plan(), "v1")
    assert "--no-build" in cmd


def test_compose_endpoint_prefers_configured_base_url():
    cfg = DeployConfig(base_url="http://localhost:9999")
    assert ComposeAdapter(cfg).endpoint(_plan()) == "http://localhost:9999"


def test_compose_endpoint_falls_back_to_a_local_default():
    assert ComposeAdapter(DeployConfig()).endpoint(_plan()).startswith("http://localhost")


def test_script_uses_make_targets_by_default():
    a = ScriptAdapter(DeployConfig(adapter="script"))
    assert a.apply_cmd(_plan()) == "make deploy"
    assert a.rollback_cmd(_plan(), "v1") == "make rollback"
    assert a.current_version_cmd(_plan()) == "make version"


def test_script_targets_are_overridable():
    a = ScriptAdapter(DeployConfig(adapter="script", commands={"deploy": "./ship.sh"}))
    assert a.apply_cmd(_plan()) == "./ship.sh"
    assert a.rollback_cmd(_plan(), "v1") == "make rollback"


def test_adapters_never_shell_out():
    """The purity rule, asserted as a reviewable import check."""
    import pathlib

    src = pathlib.Path("src/sdlc/deploy/adapters.py").read_text(encoding="utf-8")
    for forbidden in ("subprocess", "asyncio", "os.system", "requests"):
        assert forbidden not in src, forbidden
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deploy_adapters.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.deploy'`

- [ ] **Step 3: Create the package**

Create `src/sdlc/deploy/__init__.py` (empty, matching `src/sdlc/toolchain/__init__.py`):

```python
```

Create `src/sdlc/deploy/adapters.py`:

```python
"""Hosting adapters (ADR-19, FR-1105).

A DeployAdapter resolves a DeployPlan into the commands that apply it, read
the running version, and restore a prior one. Structurally identical to
toolchain/adapters.py and harness/adapters.py: an ABC + concrete adapters +
a module-level registry dict.

The adapter object is PURE -- it produces command strings and identity only,
never runs a subprocess. Execution lives in Temporal activities
(deploy/activities.py), exactly as ToolchainAdapter never runs a test.

Two adapters ship. FR-1105 requires one reference (compose); script is the
second because a seam with a single implementation quietly becomes a
substrate -- and it preserves any target repo that already has `make deploy`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from ..models import DeployConfig, DeployPlan


class DeployKind(str, Enum):
    COMPOSE = "compose"
    SCRIPT = "script"


class DeployAdapter(ABC):
    kind: DeployKind

    def __init__(self, cfg: DeployConfig) -> None:
        self.cfg = cfg

    @abstractmethod
    def apply_cmd(self, plan: DeployPlan) -> str:
        """Command bringing `plan.version` up."""

    @abstractmethod
    def current_version_cmd(self, plan: DeployPlan) -> str:
        """Command whose stdout identifies the currently running version.
        Empty stdout means nothing is deployed yet (first-ever deploy)."""

    @abstractmethod
    def rollback_cmd(self, plan: DeployPlan, to_version: str) -> str:
        """Command restoring a specific prior version."""

    @abstractmethod
    def endpoint(self, plan: DeployPlan) -> str:
        """Base URL `http` smoke checks resolve their paths against."""

    def env(self, plan: DeployPlan, version: str | None = None) -> dict[str, str]:
        """Environment exported to every command. `version` overrides the
        plan's own -- rollback must run with the PRIOR version in scope, not
        the one that just failed."""
        env = {
            "DEPLOY_ENV": plan.environment,
            "DEPLOY_VERSION": version or plan.version,
        }
        if plan.flag is not None:
            env["DEPLOY_FLAG"] = plan.flag.name
            env["DEPLOY_COHORT"] = plan.flag.cohort
        return env


class ComposeAdapter(DeployAdapter):
    """FR-1105 reference adapter. Assumes the target repo's compose file
    reads ${IMAGE_TAG} for the image it builds/runs."""

    kind = DeployKind.COMPOSE
    DEFAULT_BASE_URL = "http://localhost:8000"

    def apply_cmd(self, plan: DeployPlan) -> str:
        # --wait blocks until containers report healthy (or the compose
        # healthcheck fails), so a green exit code means something is up --
        # the smoke checks then decide whether it WORKS.
        return "docker compose up -d --build --wait"

    def current_version_cmd(self, plan: DeployPlan) -> str:
        return "docker compose images --format json"

    def rollback_cmd(self, plan: DeployPlan, to_version: str) -> str:
        # --no-build on purpose: the prior image already exists, and
        # rebuilding would re-run the very build we are escaping.
        return "docker compose up -d --no-build --wait"

    def endpoint(self, plan: DeployPlan) -> str:
        return self.cfg.base_url or self.DEFAULT_BASE_URL

    def env(self, plan: DeployPlan, version: str | None = None) -> dict[str, str]:
        env = super().env(plan, version)
        env["IMAGE_TAG"] = version or plan.version
        return env


class ScriptAdapter(DeployAdapter):
    """The generalization of the pre-E-67 `make deploy ENV=staging` shell-out.
    Delegates semantics to a convention the target repo already owns."""

    kind = DeployKind.SCRIPT
    DEFAULTS = {"deploy": "make deploy", "rollback": "make rollback", "version": "make version"}

    def _cmd(self, key: str) -> str:
        return self.cfg.commands.get(key, self.DEFAULTS[key])

    def apply_cmd(self, plan: DeployPlan) -> str:
        return self._cmd("deploy")

    def current_version_cmd(self, plan: DeployPlan) -> str:
        return self._cmd("version")

    def rollback_cmd(self, plan: DeployPlan, to_version: str) -> str:
        return self._cmd("rollback")

    def endpoint(self, plan: DeployPlan) -> str:
        return self.cfg.base_url or ""


# Classes, not instances (unlike TOOLCHAINS) -- a deploy adapter is
# constructed with the run's DeployConfig, so there is no useful singleton.
ADAPTERS: dict[DeployKind, type[DeployAdapter]] = {
    DeployKind.COMPOSE: ComposeAdapter,
    DeployKind.SCRIPT: ScriptAdapter,
}


def resolve(cfg: DeployConfig) -> DeployAdapter:
    """FR-1105: resolved from configuration, never from an agent artifact."""
    return ADAPTERS[DeployKind(cfg.adapter)](cfg)
```

- [ ] **Step 4: Reinstall so the new package is importable**

Run: `pip install -e .`
Expected: succeeds. (Required — setuptools' editable wheel does not auto-discover new modules.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_deploy_adapters.py -q`
Expected: PASS (14 tests)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/deploy/ tests/test_deploy_adapters.py
git commit -m "feat: pure compose and script deploy adapters"
```

---

### Task 4: `deploy_current_version` and `deploy_apply` activities

**Files:**
- Create: `src/sdlc/deploy/activities.py`
- Modify: `docs/superpowers/specs/2026-08-06-deploy-contract-design.md` (§5.1 correction, below)
- Test: `tests/test_deploy_activities.py` (create)

**Interfaces:**
- Consumes: `resolve` (Task 3); `DeployPlan`, `DeployConfig` (Tasks 1–2).
- Produces:
  - `class DeployActivityInput(BaseModel): plan, cfg, repo_path`
  - `class CurrentVersionResult(BaseModel): version: str | None`
  - `class ApplyResult(BaseModel): endpoint: str, detail: str`
  - `async def deploy_current_version(inp: DeployActivityInput) -> CurrentVersionResult`
  - `async def deploy_apply(inp: DeployActivityInput) -> ApplyResult`
  - `async def _run(cmd: str, cwd: str, env: dict[str, str], timeout_s: int) -> tuple[int, str]`

**Spec correction (do this in this task's commit).** The spec's §5.1 states `current_version_cmd` runs *inside* `deploy_apply`. That is wrong: when `deploy_apply` raises, the workflow never receives the prior version — and that is precisely the path where §7 requires a rollback ("rollback runs on apply failure too"). Reading the current version is therefore its own activity, so the value lands in workflow state before anything changes.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deploy_activities.py`:

```python
"""E-67 activities. These execute the pure adapters' command strings; the
adapters themselves stay subprocess-free."""

from __future__ import annotations

import pytest

from sdlc.deploy.activities import (
    ApplyResult,
    CurrentVersionResult,
    DeployActivityInput,
    deploy_apply,
    deploy_current_version,
)
from sdlc.models import DeployConfig, DeployPlan


def _inp(tmp_path, **cfg_over) -> DeployActivityInput:
    cfg = DeployConfig(adapter="script", **cfg_over)
    return DeployActivityInput(
        plan=DeployPlan(environment="staging", version="v2"), cfg=cfg, repo_path=str(tmp_path)
    )


@pytest.mark.asyncio
async def test_current_version_returns_trimmed_stdout(tmp_path):
    inp = _inp(tmp_path, commands={"version": "echo   v1  "})
    assert (await deploy_current_version(inp)) == CurrentVersionResult(version="v1")


@pytest.mark.asyncio
async def test_empty_stdout_means_nothing_is_deployed_yet(tmp_path):
    """First-ever deploy: there is no prior version, and None says so."""
    inp = _inp(tmp_path, commands={"version": "echo"})
    assert (await deploy_current_version(inp)).version is None


@pytest.mark.asyncio
async def test_failing_version_probe_is_not_fatal(tmp_path):
    """A target with no `make version` target must not break the deploy --
    it only means we cannot roll back, which the report states plainly."""
    inp = _inp(tmp_path, commands={"version": "exit 3"})
    assert (await deploy_current_version(inp)).version is None


@pytest.mark.asyncio
async def test_apply_returns_the_endpoint_on_success(tmp_path):
    inp = _inp(tmp_path, commands={"deploy": "echo shipped"}, base_url="http://localhost:1234")
    result = await deploy_apply(inp)
    assert isinstance(result, ApplyResult)
    assert result.endpoint == "http://localhost:1234"


@pytest.mark.asyncio
async def test_apply_raises_on_a_nonzero_exit(tmp_path):
    inp = _inp(tmp_path, commands={"deploy": "exit 1"})
    with pytest.raises(RuntimeError, match="deploy failed"):
        await deploy_apply(inp)


@pytest.mark.asyncio
async def test_apply_refuses_an_unfrozen_plan(tmp_path):
    """Catches 'someone edited the plan after the gate' (spec §7)."""
    inp = _inp(tmp_path, commands={"deploy": "echo shipped"})
    inp.plan.frozen = False
    with pytest.raises(ValueError, match="frozen"):
        await deploy_apply(inp)


@pytest.mark.asyncio
async def test_apply_exports_the_plan_environment(tmp_path):
    out = tmp_path / "env.txt"
    inp = _inp(tmp_path, commands={"deploy": f'printf "%s" "$DEPLOY_VERSION" > "{out.as_posix()}"'})
    await deploy_apply(inp)
    assert out.read_text().strip() == "v2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deploy_activities.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.deploy.activities'`

- [ ] **Step 3: Write the activities**

Create `src/sdlc/deploy/activities.py`:

```python
"""Deploy activities (E-67). The adapters produce command strings; this
module is the only place that runs them.

Split note: reading the current version is its OWN activity rather than a
step inside deploy_apply. If apply raises, the workflow must still hold the
prior version -- that is exactly the path where a rollback is needed.
"""

from __future__ import annotations

import asyncio
import os

from pydantic import BaseModel
from temporalio import activity

from .adapters import resolve
from ..models import DeployConfig, DeployPlan

# A version probe or an apply that hangs must not sit on the activity's
# start_to_close_timeout doing nothing visible; these bound the subprocess
# itself so the failure is ours to report.
VERSION_TIMEOUT_S = 60
APPLY_TIMEOUT_S = 3600


class DeployActivityInput(BaseModel):
    plan: DeployPlan
    cfg: DeployConfig
    repo_path: str


class CurrentVersionResult(BaseModel):
    version: str | None = None


class ApplyResult(BaseModel):
    endpoint: str = ""
    detail: str = ""


async def _run(cmd: str, cwd: str, env: dict[str, str], timeout_s: int) -> tuple[int, str]:
    """Run `cmd` in `cwd` with `env` layered over the worker's own. Returns
    (returncode, combined output). Never raises on a nonzero exit -- callers
    decide what a failure means."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        env={**os.environ, **env},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, f"timed out after {timeout_s}s"
    return proc.returncode or 0, out_b.decode(errors="replace")[-4000:]


@activity.defn
async def deploy_current_version(inp: DeployActivityInput) -> CurrentVersionResult:
    """Best-effort read of what is running now, BEFORE anything changes.

    A failed or empty probe is not an error: it means we have no rollback
    target, which the DeployReport states plainly rather than pretending a
    rollback is available."""
    adapter = resolve(inp.cfg)
    code, out = await _run(
        adapter.current_version_cmd(inp.plan),
        inp.repo_path,
        adapter.env(inp.plan),
        VERSION_TIMEOUT_S,
    )
    if code != 0:
        activity.logger.info("version probe failed (%s): %s", code, out[-200:])
        return CurrentVersionResult(version=None)
    return CurrentVersionResult(version=out.strip() or None)


@activity.defn
async def deploy_apply(inp: DeployActivityInput) -> ApplyResult:
    """Bring plan.version up. A zero exit means something is running -- the
    smoke checks, not this activity, decide whether it works."""
    if not inp.plan.frozen:
        # Non-retryable by construction: retrying cannot make it frozen.
        raise ValueError(
            "refusing to apply a DeployPlan that is not frozen (it must be frozen at the plan gate)"
        )
    adapter = resolve(inp.cfg)
    code, out = await _run(
        adapter.apply_cmd(inp.plan), inp.repo_path, adapter.env(inp.plan), APPLY_TIMEOUT_S
    )
    if code != 0:
        raise RuntimeError(f"deploy failed ({code}): {out[-2000:]}")
    return ApplyResult(endpoint=adapter.endpoint(inp.plan), detail=out[-2000:])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_deploy_activities.py -q`
Expected: PASS (7 tests)

> On Windows these tests shell out through `cmd.exe`, where `exit 1` and `printf` behave differently. If the suite runs on Windows, mark the two shell-dependent tests with `@pytest.mark.skipif(os.name == "nt", reason="POSIX shell syntax")` — the `docker` integration test in Task 9 covers the real path.

- [ ] **Step 5: Correct the spec**

In `docs/superpowers/specs/2026-08-06-deploy-contract-design.md`, replace the line under §5.1:

> `current_version_cmd` runs *before* apply, inside `deploy_apply`, so `rolled_back_to` is known before anything changes.

with:

> `deploy_current_version` is a **separate activity** running before `deploy_apply`, so the prior version lands in workflow state before anything changes. Folding it into `deploy_apply` would lose it whenever apply raises — which is exactly when §7 requires a rollback. A failed or empty probe returns `None` and is not an error; it means there is no rollback target.

Add `deploy_current_version` as the first row of the §5.1 activity table, retry policy **3 attempts**, note "read-only and idempotent, so retrying is free".

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/deploy/activities.py tests/test_deploy_activities.py \
        docs/superpowers/specs/2026-08-06-deploy-contract-design.md
git commit -m "feat: deploy_current_version and deploy_apply activities

Reading the current version is its own activity, not a step inside
deploy_apply: when apply raises, the workflow must still hold the prior
version, which is exactly when a rollback is needed. Spec 5.1 corrected."
```

---

### Task 5: `smoke_check` and `deploy_rollback` activities

**Files:**
- Modify: `src/sdlc/deploy/activities.py`
- Test: `tests/test_smoke_check.py` (create)

**Interfaces:**
- Consumes: `_run`, `DeployActivityInput` (Task 4); `SmokeCheck`, `SmokeCheckResult`, `SmokeState` (Task 1).
- Produces:
  - `class SmokeCheckInput(BaseModel): plan, cfg, repo_path, endpoint`
  - `class SmokeCheckOutput(BaseModel): results: list[SmokeCheckResult]`
  - `class RollbackInput(BaseModel): plan, cfg, repo_path, to_version`
  - `async def smoke_check(inp: SmokeCheckInput) -> SmokeCheckOutput`
  - `async def deploy_rollback(inp: RollbackInput) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_smoke_check.py`:

```python
"""D-3 made executable: an unreachable service is `errored`, never a pass."""

from __future__ import annotations

import pytest

from sdlc.deploy.activities import (
    RollbackInput,
    SmokeCheckInput,
    deploy_rollback,
    smoke_check,
)
from sdlc.models import (
    DeployConfig,
    DeployPlan,
    SmokeCheck,
    SmokeState,
)


def _inp(tmp_path, checks, endpoint="http://127.0.0.1:1", **cfg_over):
    cfg = DeployConfig(adapter="script", readiness_timeout_s=1, **cfg_over)
    return SmokeCheckInput(
        plan=DeployPlan(environment="staging", version="v2", smoke_checks=checks),
        cfg=cfg,
        repo_path=str(tmp_path),
        endpoint=endpoint,
    )


@pytest.mark.asyncio
async def test_no_checks_yields_no_results(tmp_path):
    out = await smoke_check(_inp(tmp_path, []))
    assert out.results == []


@pytest.mark.asyncio
async def test_passing_command_check(tmp_path):
    out = await smoke_check(
        _inp(tmp_path, [SmokeCheck(name="ok", kind="command", command="exit 0")])
    )
    assert out.results[0].state is SmokeState.PASSED


@pytest.mark.asyncio
async def test_failing_command_check_is_failed_not_errored(tmp_path):
    """The assertion was evaluated and did not hold."""
    out = await smoke_check(
        _inp(tmp_path, [SmokeCheck(name="nope", kind="command", command="exit 1")])
    )
    assert out.results[0].state is SmokeState.FAILED
    assert out.results[0].detail


@pytest.mark.asyncio
async def test_unreachable_http_check_is_errored_not_failed(tmp_path):
    """The load-bearing case. Port 1 refuses instantly -- we could not
    evaluate the assertion at all, and that must not read as a pass."""
    out = await smoke_check(
        _inp(tmp_path, [SmokeCheck(name="health", kind="http", path="/health")])
    )
    r = out.results[0]
    assert r.state is SmokeState.ERRORED
    assert r.passed is False
    assert r.detail


@pytest.mark.asyncio
async def test_every_check_gets_a_result(tmp_path):
    """A failure early must not swallow the checks after it -- the human
    reading the report needs the whole picture."""
    out = await smoke_check(
        _inp(
            tmp_path,
            [
                SmokeCheck(name="a", kind="command", command="exit 1"),
                SmokeCheck(name="b", kind="command", command="exit 0"),
                SmokeCheck(name="c", kind="http", path="/x"),
            ],
        )
    )
    assert [r.name for r in out.results] == ["a", "b", "c"]
    assert [r.state for r in out.results] == [
        SmokeState.FAILED,
        SmokeState.PASSED,
        SmokeState.ERRORED,
    ]


@pytest.mark.asyncio
async def test_command_checks_see_the_deploy_environment(tmp_path):
    out = await smoke_check(
        _inp(
            tmp_path,
            [SmokeCheck(name="env", kind="command", command='test "$DEPLOY_VERSION" = "v2"')],
        )
    )
    assert out.results[0].state is SmokeState.PASSED


@pytest.mark.asyncio
async def test_rollback_raises_so_temporal_retries_it(tmp_path):
    """Rollback is the safety operation; a silent failure is unacceptable."""
    inp = RollbackInput(
        plan=DeployPlan(environment="staging", version="v2"),
        cfg=DeployConfig(adapter="script", commands={"rollback": "exit 1"}),
        repo_path=str(tmp_path),
        to_version="v1",
    )
    with pytest.raises(RuntimeError, match="rollback failed"):
        await deploy_rollback(inp)


@pytest.mark.asyncio
async def test_rollback_runs_with_the_prior_version_in_scope(tmp_path):
    out = tmp_path / "v.txt"
    inp = RollbackInput(
        plan=DeployPlan(environment="staging", version="v2"),
        cfg=DeployConfig(
            adapter="script",
            commands={"rollback": f'printf "%s" "$DEPLOY_VERSION" > "{out.as_posix()}"'},
        ),
        repo_path=str(tmp_path),
        to_version="v1",
    )
    await deploy_rollback(inp)
    assert out.read_text().strip() == "v1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_smoke_check.py -q`
Expected: FAIL — `ImportError: cannot import name 'smoke_check'`

- [ ] **Step 3: Add the activities**

Append to `src/sdlc/deploy/activities.py` (and extend the imports at the top with `import urllib.error`, `import urllib.request`, and `from ..models import SmokeCheck, SmokeCheckResult, SmokeState`):

```python
class SmokeCheckInput(BaseModel):
    plan: DeployPlan
    cfg: DeployConfig
    repo_path: str
    endpoint: str


class SmokeCheckOutput(BaseModel):
    # Wrapped rather than a bare list: activity payloads round-trip through
    # the pydantic data converter more predictably as a model.
    results: list[SmokeCheckResult] = []


class RollbackInput(BaseModel):
    plan: DeployPlan
    cfg: DeployConfig
    repo_path: str
    to_version: str


def _http_once(url: str, expect_status: int, timeout_s: int) -> SmokeCheckResult | None:
    """Returns None if the request could not be made at all (caller decides
    whether that is 'not ready yet' or 'errored')."""
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code  # a response IS an evaluation
    except Exception:
        return None  # no response: we learned nothing
    return SmokeCheckResult(
        name="",
        state=(SmokeState.PASSED if status == expect_status else SmokeState.FAILED),
        detail=("" if status == expect_status else f"expected {expect_status}, got {status}"),
    )


async def _await_readiness(url: str, timeout_s: int) -> None:
    """Poll until the endpoint answers at all, or the budget runs out. A
    container that just started is not yet a broken one."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        activity.heartbeat("awaiting readiness")
        if await asyncio.to_thread(_http_once, url, 200, 5) is not None:
            return
        await asyncio.sleep(1)


@activity.defn
async def smoke_check(inp: SmokeCheckInput) -> SmokeCheckOutput:
    """Run every check exactly once and return a result for each.

    NEVER raises on an assertion failure: the workflow decides what a failure
    means. Retrying a smoke check would mask the very signal being collected,
    which is why this activity is registered with maximum_attempts=1 and does
    its own readiness polling instead.
    """
    adapter = resolve(inp.cfg)
    env = adapter.env(inp.plan)
    http_checks = [c for c in inp.plan.smoke_checks if c.kind == "http"]
    if http_checks and inp.endpoint:
        await _await_readiness(
            inp.endpoint.rstrip("/") + "/" + http_checks[0].path.lstrip("/"),
            inp.cfg.readiness_timeout_s,
        )

    results: list[SmokeCheckResult] = []
    for check in inp.plan.smoke_checks:
        activity.heartbeat(check.name)
        if check.kind == "http":
            url = inp.endpoint.rstrip("/") + "/" + check.path.lstrip("/")
            outcome = await asyncio.to_thread(_http_once, url, check.expect_status, check.timeout_s)
            if outcome is None:
                results.append(
                    SmokeCheckResult(
                        name=check.name,
                        state=SmokeState.ERRORED,
                        detail=f"no response from {url} within {check.timeout_s}s",
                    )
                )
            else:
                results.append(outcome.model_copy(update={"name": check.name}))
            continue

        code, out = await _run(check.command, inp.repo_path, env, check.timeout_s)
        if code == 124:
            results.append(SmokeCheckResult(name=check.name, state=SmokeState.ERRORED, detail=out))
        elif code != 0:
            results.append(
                SmokeCheckResult(
                    name=check.name, state=SmokeState.FAILED, detail=f"exit {code}: {out[-500:]}"
                )
            )
        else:
            results.append(SmokeCheckResult(name=check.name, state=SmokeState.PASSED))
    return SmokeCheckOutput(results=results)


@activity.defn
async def deploy_rollback(inp: RollbackInput) -> None:
    """Restore `to_version`. Raises on failure so Temporal's retry policy
    gets its chance -- this is the safety operation, and a failed rollback is
    the worst outcome in the system."""
    adapter = resolve(inp.cfg)
    code, out = await _run(
        adapter.rollback_cmd(inp.plan, inp.to_version),
        inp.repo_path,
        adapter.env(inp.plan, version=inp.to_version),
        APPLY_TIMEOUT_S,
    )
    if code != 0:
        raise RuntimeError(f"rollback failed ({code}): {out[-2000:]}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_smoke_check.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/deploy/activities.py tests/test_smoke_check.py
git commit -m "feat: smoke_check and deploy_rollback activities

Smoke results are tri-state: a service we could not reach is errored, not
passed. Every check gets a result even after an earlier one fails."
```

---

### Task 6: `DeploymentWorkflow` + worker registration

**Files:**
- Create: `src/sdlc/workflows/deployment.py`
- Modify: `src/sdlc/worker.py` (imports; `workflows=` at `worker.py:82`; `activities=` at `worker.py:83`)
- Test: `tests/test_deployment_workflow.py` (create)

**Interfaces:**
- Consumes: all four activities (Tasks 4–5); `DeployPlan`, `DeployReport`, `DeployConfig` (Tasks 1–2).
- Produces:
  - `class DeploymentInput(BaseModel): plan, cfg, repo_path, attempt: int = 1`
  - `def needs_rollback(results: list[SmokeCheckResult]) -> bool` — pure, importable without Temporal
  - `class DeploymentWorkflow` with `@workflow.run async def run(self, inp: DeploymentInput) -> DeployReport`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deployment_workflow.py`:

```python
"""The child workflow's decision logic. The pure helper is tested directly;
the sequencing is tested through the parent in Task 7."""

from __future__ import annotations

import pathlib

from sdlc.models import SmokeCheckResult, SmokeState
from sdlc.workflows.deployment import DeploymentInput, needs_rollback


def _r(state, name="c"):
    return SmokeCheckResult(
        name=name, state=state, detail="" if state is SmokeState.PASSED else "why"
    )


def test_all_passed_needs_no_rollback():
    assert needs_rollback([_r(SmokeState.PASSED), _r(SmokeState.PASSED)]) is False


def test_no_checks_needs_no_rollback():
    """A plan with no smoke checks deploys. Weak, but honest -- and the
    planner owning the checks is where that gets fixed, not here."""
    assert needs_rollback([]) is False


def test_a_failed_check_triggers_rollback():
    assert needs_rollback([_r(SmokeState.PASSED), _r(SmokeState.FAILED)]) is True


def test_an_errored_check_triggers_rollback():
    """D-3: 'we could not tell' is not permission to ship."""
    assert needs_rollback([_r(SmokeState.ERRORED)]) is True


def test_attempt_defaults_to_one():
    inp = DeploymentInput.model_construct(attempt=1)
    assert inp.attempt == 1


SRC = pathlib.Path("src/sdlc/workflows/deployment.py")


def test_the_child_makes_no_model_call():
    """Invariant: DeploymentWorkflow is deterministic. An agent import here
    would be a reviewable regression."""
    src = SRC.read_text(encoding="utf-8")
    for forbidden in ("TemporalAgent", "pydantic_ai", "resolve_role_model"):
        assert forbidden not in src, forbidden


def test_the_child_holds_no_gate():
    """D-6: HITL stays in FeatureWorkflow, where the signals land."""
    src = SRC.read_text(encoding="utf-8")
    assert "_gate" not in src
    assert "signal" not in src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deployment_workflow.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.workflows.deployment'`

- [ ] **Step 3: Write the workflow**

Create `src/sdlc/workflows/deployment.py`:

```python
"""DeploymentWorkflow (E-67) -- DAG stage 13's apply -> smoke -> rollback.

Deterministic by construction: no model call, no gate. It sequences four
activities and returns a DeployReport. The HITL `deploy_failed` gate lives in
FeatureWorkflow (D-6), because Temporal signals are addressed to a workflow
id and operators know their run's id, not a child's.

This is also the seam E-70 attaches to: an ObservationWorkflow starts here
with ParentClosePolicy.ABANDON, so a multi-day observation window outlives
the feature run instead of pinning it open.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..deploy.activities import (
        DeployActivityInput,
        RollbackInput,
        SmokeCheckInput,
        deploy_apply,
        deploy_current_version,
        deploy_rollback,
        smoke_check,
    )
    from ..models import (
        DeployConfig,
        DeployPlan,
        DeployReport,
        SmokeCheckResult,
    )

# Read-only and idempotent -- retrying is free.
VERSION_ACT = dict(
    start_to_close_timeout=timedelta(minutes=2), retry_policy=RetryPolicy(maximum_attempts=3)
)
# Build failures are deterministic and will not improve; the second attempt
# exists for registry/network blips.
APPLY_ACT = dict(
    start_to_close_timeout=timedelta(hours=1),
    heartbeat_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=2),
)
# ONE attempt on purpose: retrying a smoke check would mask the signal being
# collected. Readiness polling is the activity's own job.
SMOKE_ACT = dict(
    start_to_close_timeout=timedelta(minutes=15),
    heartbeat_timeout=timedelta(minutes=2),
    retry_policy=RetryPolicy(maximum_attempts=1),
)
# The safety operation, retried hardest.
ROLLBACK_ACT = dict(
    start_to_close_timeout=timedelta(hours=1),
    retry_policy=RetryPolicy(maximum_attempts=5, initial_interval=timedelta(seconds=2)),
)


class DeploymentInput(BaseModel):
    plan: DeployPlan
    cfg: DeployConfig
    repo_path: str
    attempt: int = 1


def needs_rollback(results: list[SmokeCheckResult]) -> bool:
    """Any check that is not PASSED. `errored` counts -- 'we could not tell'
    is not permission to ship (D-3)."""
    return any(not r.passed for r in results)


@workflow.defn
class DeploymentWorkflow:
    @workflow.run
    async def run(self, inp: DeploymentInput) -> DeployReport:
        act_in = DeployActivityInput(plan=inp.plan, cfg=inp.cfg, repo_path=inp.repo_path)

        # BEFORE anything changes, so a rollback target exists even if apply
        # blows up. None means first-ever deploy: nothing to restore.
        previous = (
            await workflow.execute_activity(deploy_current_version, act_in, **VERSION_ACT)
        ).version

        def _report(**over) -> DeployReport:
            base = dict(
                deployed=False,
                environment=inp.plan.environment,
                version=inp.plan.version,
                adapter=inp.cfg.adapter,
            )
            base.update(over)
            return DeployReport(**base)

        async def _rollback(reason: str) -> DeployReport:
            if previous is None:
                # A first deploy that fails smoke leaves a broken service up.
                # Saying so beats pretending a rollback happened.
                return _report(
                    rolled_back=False,
                    rollback_reason=f"no previous version to restore; {reason}",
                    checks=checks,
                )
            if not inp.plan.rollback.auto:
                return _report(
                    rolled_back=False,
                    rollback_reason=f"auto-rollback disabled; {reason}",
                    checks=checks,
                )
            try:
                await workflow.execute_activity(
                    deploy_rollback,
                    RollbackInput(
                        plan=inp.plan, cfg=inp.cfg, repo_path=inp.repo_path, to_version=previous
                    ),
                    **ROLLBACK_ACT,
                )
            except Exception as e:
                # The worst outcome in the system: the environment is now in
                # an unknown state. The parent turns this into deploy-broken:.
                return _report(
                    rolled_back=False,
                    rollback_reason=f"rollback exhausted: {e}; {reason}",
                    checks=checks,
                )
            return _report(
                rolled_back=True, rolled_back_to=previous, rollback_reason=reason, checks=checks
            )

        checks: list[SmokeCheckResult] = []

        try:
            applied = await workflow.execute_activity(deploy_apply, act_in, **APPLY_ACT)
        except Exception as e:
            # A partially-applied stack is exactly why rollback runs on apply
            # failure too, not only on smoke failure.
            return await _rollback(f"apply failed: {e}")

        checks = (
            await workflow.execute_activity(
                smoke_check,
                SmokeCheckInput(
                    plan=inp.plan, cfg=inp.cfg, repo_path=inp.repo_path, endpoint=applied.endpoint
                ),
                **SMOKE_ACT,
            )
        ).results

        if needs_rollback(checks):
            failed = ", ".join(f"{r.name}={r.state.value}" for r in checks if not r.passed)
            return await _rollback(f"smoke checks not passed: {failed}")

        return _report(deployed=True, endpoint=applied.endpoint, checks=checks)
```

- [ ] **Step 4: Register with the worker**

In `src/sdlc/worker.py`, add to the imports (near `from .workflows.feature import FeatureWorkflow` at `worker.py:54`):

```python
from .deploy.activities import (
    deploy_apply,
    deploy_current_version,
    deploy_rollback,
    smoke_check,
)
from .workflows.deployment import DeploymentWorkflow
```

Change `workflows=` (`worker.py:82`):

```python
workflows = ([FeatureWorkflow, BenchmarkWorkflow, ReflectWorkflow, DeploymentWorkflow],)
```

And add to the `activities=[...]` list (`worker.py:83`):

```python
(
    deploy_current_version,
    deploy_apply,
    smoke_check,
    deploy_rollback,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_deployment_workflow.py -q`
Expected: PASS (7 tests)

- [ ] **Step 6: Verify the worker still imports**

Run: `python -c "import sdlc.worker"`
Expected: no output, exit 0. (`tests/conftest.py` sets dummy API keys; if running outside pytest, export `ANTHROPIC_API_KEY=x OPENAI_API_KEY=x EXA_API_KEY=x` first.)

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/workflows/deployment.py src/sdlc/worker.py \
        tests/test_deployment_workflow.py
git commit -m "feat: deterministic DeploymentWorkflow child, registered on the worker"
```

---

### Task 7: Parent wiring and the `deploy_failed` gate

**Files:**
- Modify: `src/sdlc/workflows/feature.py:2309-2329` (the deploy stage)
- Modify: `src/sdlc/activities.py:1031-1047` (delete `DeployInput` / `deploy`)
- Test: `tests/test_deploy_stage.py` (create)

**Interfaces:**
- Consumes: `DeploymentWorkflow`, `DeploymentInput` (Task 6); `DeployReport` (Task 1); `cfg.deploy` (Task 2).
- Produces: `FeatureWorkflow.run` return values `deployed:`, `rolled-back:`, `deploy-rejected:`, `deploy-broken:`, `merged-not-deployed:`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deploy_stage.py`:

```python
"""Stage 13 wiring. The rollback SEQUENCING is proven here with mocked
activities (D-8); the compose adapter's mechanics are proven by the
docker-marked test in Task 9."""

from __future__ import annotations

import pathlib

import pytest

from sdlc.models import (
    DeployReport,
    GateDecision,
    GateOutcome,
    SmokeCheckResult,
    SmokeState,
)
from sdlc.workflows.feature import _deploy_result

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def _report(**over) -> DeployReport:
    base = dict(
        deployed=False,
        environment="staging",
        version="v1",
        adapter="compose",
        rolled_back=True,
        rolled_back_to="v0",
        rollback_reason="smoke checks not passed: health=failed",
    )
    base.update(over)
    return DeployReport(**base)


def _decision(outcome) -> GateDecision:
    return GateDecision(gate="deploy_failed", round=1, outcome=outcome, decided_by="human")


def test_success_returns_deployed():
    r = DeployReport(deployed=True, environment="staging", version="v1", adapter="compose")
    assert _deploy_result(r, None, "PR") == "deployed:PR"


def test_acknowledged_rollback_returns_rolled_back():
    assert _deploy_result(_report(), _decision(GateOutcome.APPROVE), "PR") == "rolled-back:PR"


def test_rejection_is_terminal_and_distinct():
    assert _deploy_result(_report(), _decision(GateOutcome.REJECT), "PR") == "deploy-rejected:PR"


def test_a_failed_rollback_is_never_reported_as_rolled_back():
    """The load-bearing assertion. Claiming a rollback that did not happen
    is the worst lie this system could tell: the environment is live and in
    an unknown state."""
    broken = _report(
        rolled_back=False, rolled_back_to=None, rollback_reason="rollback exhausted: timeout"
    )
    assert _deploy_result(broken, _decision(GateOutcome.APPROVE), "PR") == "deploy-broken:PR"
    assert _deploy_result(broken, _decision(GateOutcome.REJECT), "PR") == "deploy-broken:PR"


def test_no_previous_version_is_also_broken_not_rolled_back():
    """First-ever deploy that failed smoke: nothing was restored."""
    first = _report(
        rolled_back=False,
        rolled_back_to=None,
        rollback_reason="no previous version to restore; smoke checks not passed: health=failed",
    )
    assert _deploy_result(first, _decision(GateOutcome.APPROVE), "PR") == "deploy-broken:PR"


def test_the_old_hardcoded_deploy_is_gone():
    src = SRC.read_text(encoding="utf-8")
    assert "make deploy ENV=staging" not in src
    assert "DeployInput" not in src


def test_the_stage_is_gated_on_config():
    src = SRC.read_text(encoding="utf-8")
    assert "cfg.deploy.enabled" in src


def test_the_child_id_is_derived_not_generated():
    """Determinism: replay must produce the same child id."""
    src = SRC.read_text(encoding="utf-8")
    assert "-deploy-" in src
    assert "uuid" not in src.split("6. DEPLOY")[1][:2000]


def test_deploy_activity_is_deleted_from_activities():
    src = pathlib.Path("src/sdlc/activities.py").read_text(encoding="utf-8")
    assert "async def deploy(" not in src
    assert "class DeployInput" not in src
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deploy_stage.py -q`
Expected: FAIL — `ImportError: cannot import name '_deploy_result'`

- [ ] **Step 3: Add the pure result mapper**

In `src/sdlc/workflows/feature.py`, near the other module-level helpers (after `_long_act`, around line 200):

```python
def _deploy_result(report: DeployReport, decision: GateDecision | None, pr_url: str) -> str:
    """Map a DeployReport plus the deploy_failed gate decision onto the run's
    terminal string. Pure, so the mapping is testable without Temporal.

    `decision` is None only when the report says deployed.

    A report whose rollback did NOT happen can never return `rolled-back:` --
    the environment is live and in an unknown state, and flattening that into
    an ordinary failure hides the one outcome needing a human immediately.
    """
    if report.deployed:
        return f"deployed:{pr_url}"
    if not report.rolled_back:
        return f"deploy-broken:{pr_url}"
    if decision is not None and decision.outcome is GateOutcome.REJECT:
        return f"deploy-rejected:{pr_url}"
    return f"rolled-back:{pr_url}"
```

Add `DeployReport` to the `..models` import block and `DeploymentInput, DeploymentWorkflow` to the workflow-safe imports at the top of the file:

```python
    from .deployment import DeploymentInput, DeploymentWorkflow
```

- [ ] **Step 4: Replace the deploy stage**

In `src/sdlc/workflows/feature.py`, replace lines 2309-2329 (from `# 6. DEPLOY gate → deploy` to `return f"deployed:{pr_url}"`) with:

```python
# 6. DEPLOY gate → DeploymentWorkflow child (E-67/FR-1104)
_started = workflow.now()
gate = await self._gate("deploy", cfg)
_ended = workflow.now()
await self._record(
    cfg,
    self._stage_record(
        cfg,
        stage="deploy",
        role="devops",
        started=_started,
        ended=_ended,
        quality_score=None,
        judge="llm_judge",
        outcome=(BenchmarkOutcome.PASS if gate.approved else BenchmarkOutcome.REVISED),
        model=resolve_role_model(cfg, "devops"),
    ),
)
if not gate.approved or not cfg.deploy.enabled:
    return f"merged-not-deployed:{pr_url}"

plan = self._deploy_plan(idea, arch)
attempt = 1
while True:
    report = await workflow.execute_child_workflow(
        DeploymentWorkflow.run,
        DeploymentInput(plan=plan, cfg=cfg.deploy, repo_path=repo_path, attempt=attempt),
        # Derived, never generated: replay must produce the same id,
        # and a retry round stays identifiable in the Temporal UI.
        id=f"{workflow.info().workflow_id}-deploy-{attempt}",
        task_queue=workflow.info().task_queue,
    )
    if report.deployed:
        self._status = "deployed"
        return _deploy_result(report, None, pr_url)

    # The gate opens even when the rollback itself failed -- that is
    # the case a human most needs to see.
    decision = await self._gate(
        "deploy_failed",
        cfg,
        round=attempt,
        context=GateContext(
            # ABSOLUTE: the human is not waving a check through --
            # the rollback already happened. They are deciding what
            # to do next.
            checks=[
                CheckResult(
                    name=c.name,
                    passed=c.passed,
                    classification=CheckClass.ABSOLUTE,
                    detail=c.detail,
                )
                for c in report.checks
            ],
            verdict=report.rollback_reason,
        ),
        default_policy=GatePolicy.HARD,
    )
    if decision.outcome is GateOutcome.REVISE and attempt < cfg.max_gate_rounds:
        attempt += 1
        continue
    self._status = "deploy_failed"
    return _deploy_result(report, decision, pr_url)
```

- [ ] **Step 5: Add the plan builder**

Still in `feature.py`, as a method on `FeatureWorkflow` near the other stage helpers:

```python
def _deploy_plan(self, idea, arch) -> DeployPlan:
    """The frozen DeployPlan for this run.

    TRANSITIONAL: devops_planner authoring this at the planning stage and
    the plan gate freezing it (spec D-2) is the next increment. Until
    then the run deploys with a single liveness check, which is weak but
    honest -- and `frozen=True` keeps the contract's shape intact so the
    planner can start filling it without a second code path.
    """
    return DeployPlan(
        environment="staging",
        version=workflow.info().workflow_id,
        smoke_checks=[SmokeCheck(name="liveness", kind="http", path="/health")],
    )
```

Add `DeployPlan, SmokeCheck` to the `..models` import block. `CheckResult`, `CheckClass`, `GateContext` and `GatePolicy` are already imported in `feature.py` (lines 41, 70, 81) — no import change needed for those.

- [ ] **Step 6: Delete the old activity**

In `src/sdlc/activities.py`, delete `class DeployInput` (lines 1031-1035) and `async def deploy` (lines 1038-1047). Remove `deploy` from `worker.py`'s `activities=[...]` list and from its import block, and remove `deploy, DeployInput` from `feature.py`'s activity imports.

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_deploy_stage.py -q`
Expected: PASS (9 tests)

- [ ] **Step 8: Create the deploy activity fakes**

`tests/test_e2e_greenfield.py:104` and `:131` assert `result.startswith("deployed:")`. That is ROADMAP `:93`'s **demonstrated SC-1 exit criterion** — letting it fall back to `merged-not-deployed:` would quietly retire a proven criterion, which is not an acceptable way to keep a suite green. Instead the e2e run keeps deploying, against fakes.

Create `tests/fakes/fake_deploy.py`:

```python
"""Fake deploy activities. The workflow's sequencing is what these exercise;
the real adapter mechanics are proven by the docker-marked integration test.

Behaviour is driven by module-level state so a test can script a run without
threading config through FeatureWorkflow's whole call chain."""

from __future__ import annotations

from dataclasses import dataclass, field

from temporalio import activity

from sdlc.deploy.activities import (
    ApplyResult,
    CurrentVersionResult,
    DeployActivityInput,
    RollbackInput,
    SmokeCheckInput,
    SmokeCheckOutput,
)
from sdlc.models import SmokeCheckResult, SmokeState


@dataclass
class DeployScript:
    """What the fakes should do. `smoke_states` is consumed one entry per
    apply, so a REVISE retry can succeed where attempt 1 failed."""

    previous_version: str | None = "v0"
    apply_fails: bool = False
    rollback_fails: bool = False
    smoke_states: list[SmokeState] = field(default_factory=lambda: [SmokeState.PASSED])
    applies: int = 0
    rollbacks: int = 0


SCRIPT = DeployScript()


def reset(**over) -> DeployScript:
    global SCRIPT
    SCRIPT = DeployScript(**over)
    return SCRIPT


@activity.defn(name="deploy_current_version")
async def fake_current_version(inp: DeployActivityInput) -> CurrentVersionResult:
    return CurrentVersionResult(version=SCRIPT.previous_version)


@activity.defn(name="deploy_apply")
async def fake_apply(inp: DeployActivityInput) -> ApplyResult:
    SCRIPT.applies += 1
    if SCRIPT.apply_fails:
        raise RuntimeError("deploy failed (1): fake")
    return ApplyResult(endpoint="http://fake")


@activity.defn(name="smoke_check")
async def fake_smoke(inp: SmokeCheckInput) -> SmokeCheckOutput:
    idx = min(SCRIPT.applies - 1, len(SCRIPT.smoke_states) - 1)
    state = SCRIPT.smoke_states[idx]
    return SmokeCheckOutput(
        results=[
            SmokeCheckResult(
                name="liveness",
                state=state,
                detail="" if state is SmokeState.PASSED else f"fake {state.value}",
            )
        ]
    )


@activity.defn(name="deploy_rollback")
async def fake_rollback(inp: RollbackInput) -> None:
    SCRIPT.rollbacks += 1
    if SCRIPT.rollback_fails:
        raise RuntimeError("rollback failed (1): fake")


DEPLOY_FAKES = [fake_current_version, fake_apply, fake_smoke, fake_rollback]
```

- [ ] **Step 9: Keep the e2e greenfield run deploying**

In `tests/test_e2e_greenfield.py`, import the fakes and register them, and enable the stage on the config:

```python
from tests.fakes.fake_deploy import DEPLOY_FAKES, reset as reset_deploy
```

In each test, before starting the workflow: `reset_deploy()` and `cfg.deploy.enabled = True`. Add `DeploymentWorkflow` to the Worker's `workflows=[...]` and `*DEPLOY_FAKES` to its `activities=[...]`. Both `deployed:` assertions stay exactly as they are.

- [ ] **Step 10: Run the full fast suite plus the temporal suite**

Run: `python -m pytest -q`
Expected: PASS

Run: `python -m pytest -m temporal -q`
Expected: PASS, with `tests/test_e2e_greenfield.py` still reaching `deployed:`.

- [ ] **Step 11: Commit**

```bash
git add src/sdlc/workflows/feature.py src/sdlc/activities.py \
        src/sdlc/worker.py tests/test_deploy_stage.py \
        tests/fakes/fake_deploy.py tests/test_e2e_greenfield.py
git commit -m "feat: stage 13 runs DeploymentWorkflow behind a deploy_failed gate

Replaces the hardcoded make deploy shell-out. A report whose rollback did
not happen returns deploy-broken:, never rolled-back: -- the environment is
live and in an unknown state, and that needs a human immediately.

deploy.enabled defaults to False, so runs that previously shelled out now
return merged-not-deployed:. The e2e greenfield run opts in against fakes so
SC-1's demonstrated deployed: exit criterion is preserved."
```

---

### Task 8: Workflow integration tests

**Files:**
- Test: `tests/test_deploy_workflow_paths.py` (create)

**Interfaces:**
- Consumes: `DEPLOY_FAKES`, `reset` (Task 7); `DeploymentWorkflow` (Task 6).
- Produces: nothing consumed by later tasks.

This is spec §8's six-case matrix — the auto-rollback path proven end-to-end through the real `FeatureWorkflow` with the deploy activities mocked (D-8). Case 3 is the load-bearing one.

- [ ] **Step 1: Write the tests**

Create `tests/test_deploy_workflow_paths.py`:

```python
"""Spec section 8: the six stage-13 paths, driven through the real
FeatureWorkflow with mocked deploy activities. No Docker, no fake adapter --
the adapters themselves are never involved."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.activities import evaluate_gate
from sdlc.models import (
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    SmokeState,
)
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import (
    AGENT_SPECS,
    QUESTION_IDS,
    e2e_config,
    greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES
from tests.fakes.fake_deploy import DEPLOY_FAKES, reset

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]


async def _wait_for_status(handle, target, timeout_s=15.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


def _cfg(**deploy_over):
    """Every gate OFF so the run reaches stage 13 unattended; tests that need
    a human decision re-arm the one gate they care about."""
    cfg = e2e_config()
    cfg.gates = {name: GateConfig(policy=GatePolicy.OFF) for name in cfg.gates}
    cfg.default_gate_policy = GatePolicy.OFF
    cfg.deploy.enabled = True
    for k, v in deploy_over.items():
        setattr(cfg.deploy, k, v)
    return cfg


async def _run(cfg, tmp_path, monkeypatch, tag, driver=None) -> str:
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=tag,
            workflows=[FeatureWorkflow, DeploymentWorkflow],
            activities=[
                evaluate_gate,
                export_run_artifacts,
                *GIT_FAKES,
                *DEPLOY_FAKES,
                *fake_agent_activities(AGENT_SPECS),
            ],
            plugins=[PydanticAIPlugin()],
        ):
            handle = await env.client.start_workflow(
                FeatureWorkflow.run,
                args=[greenfield_idea(), cfg],
                id=f"{tag}-{uuid.uuid4()}",
                task_queue=tag,
            )
            if driver is not None:
                with env.auto_time_skipping_disabled():
                    await driver(handle)
            return await handle.result()


async def test_1_all_checks_pass_deploys(tmp_path, monkeypatch):
    script = reset(smoke_states=[SmokeState.PASSED])
    result = await _run(_cfg(), tmp_path, monkeypatch, "d1")
    assert result.startswith("deployed:"), result
    assert script.rollbacks == 0


async def test_2_failed_check_rolls_back_and_gates(tmp_path, monkeypatch):
    script = reset(smoke_states=[SmokeState.FAILED])
    result = await _run(_cfg(), tmp_path, monkeypatch, "d2")
    # deploy_failed resolves through default_gate_policy OFF => APPROVE
    assert result.startswith("rolled-back:"), result
    assert script.rollbacks == 1


async def test_3_errored_check_rolls_back_too(tmp_path, monkeypatch):
    """The load-bearing case (D-3). A service we could not reach must take
    the same path as one we proved broken -- most deploy tooling passes this
    silently."""
    script = reset(smoke_states=[SmokeState.ERRORED])
    result = await _run(_cfg(), tmp_path, monkeypatch, "d3")
    assert result.startswith("rolled-back:"), result
    assert script.rollbacks == 1


async def test_4_revise_retries_with_a_second_child(tmp_path, monkeypatch):
    """Attempt 1 fails smoke, the human says retry, attempt 2 passes."""
    script = reset(smoke_states=[SmokeState.FAILED, SmokeState.PASSED])
    cfg = _cfg()
    cfg.gates["deploy_failed"] = GateConfig(policy=GatePolicy.HARD)
    cfg.max_gate_rounds = 2

    async def driver(handle):
        await _wait_for_status(handle, "awaiting:deploy_failed")
        await handle.signal(
            FeatureWorkflow.submit_gate_decision,
            GateDecision(
                gate="deploy_failed",
                round=1,
                outcome=GateOutcome.REVISE,
                decided_by="human",
                guidance="retry it",
            ),
        )

    result = await _run(cfg, tmp_path, monkeypatch, "d4", driver)
    assert result.startswith("deployed:"), result
    assert script.applies == 2


async def test_5_exhausted_rollback_is_deploy_broken(tmp_path, monkeypatch):
    """Never rolled-back: -- nothing was actually restored."""
    reset(smoke_states=[SmokeState.FAILED], rollback_fails=True)
    result = await _run(_cfg(), tmp_path, monkeypatch, "d5")
    assert result.startswith("deploy-broken:"), result


async def test_6_disabled_deploy_starts_no_child(tmp_path, monkeypatch):
    script = reset()
    cfg = _cfg()
    cfg.deploy.enabled = False
    result = await _run(cfg, tmp_path, monkeypatch, "d6")
    assert result.startswith("merged-not-deployed:"), result
    assert script.applies == 0


async def test_apply_failure_also_rolls_back(tmp_path, monkeypatch):
    """Spec section 7: a partially-applied stack is why rollback runs on
    apply failure, not only on smoke failure."""
    script = reset(apply_fails=True)
    result = await _run(_cfg(), tmp_path, monkeypatch, "d7")
    assert result.startswith("rolled-back:"), result
    assert script.rollbacks == 1


async def test_first_ever_deploy_cannot_roll_back(tmp_path, monkeypatch):
    """No previous version: the report says so and the run is deploy-broken,
    because nothing was restored."""
    script = reset(previous_version=None, smoke_states=[SmokeState.FAILED])
    result = await _run(_cfg(), tmp_path, monkeypatch, "d8")
    assert result.startswith("deploy-broken:"), result
    assert script.rollbacks == 0
```

- [ ] **Step 2: Run the tests**

Run: `python -m pytest tests/test_deploy_workflow_paths.py -m temporal -q`
Expected: PASS (8 tests). Each spawns its own ephemeral Temporal dev-server, so expect this to take a minute or two.

> If a test hangs at `awaiting:deploy_failed`, the gate name in `feature.py` does not match the one the test signals. The status string is `f"awaiting:{name}"`, set by `_gate` (`feature.py:1127`).

- [ ] **Step 3: Confirm the default run is unaffected**

Run: `python -m pytest -q`
Expected: PASS, and these 8 tests are not collected (the `temporal` marker is excluded by `addopts`).

- [ ] **Step 4: Commit**

```bash
git add tests/test_deploy_workflow_paths.py
git commit -m "test: the six stage-13 paths through FeatureWorkflow

Covers auto-rollback sequencing with mocked deploy activities: an errored
check takes the same path as a failed one, a failed rollback never reports
as rolled-back, and REVISE starts a second child."
```

---

### Task 9: Compose integration test

**Files:**
- Modify: `pyproject.toml:34-39` (the `docker` marker)
- Create: `tests/fixtures/deploy_target/docker-compose.yml`
- Create: `tests/fixtures/deploy_target/Dockerfile`
- Create: `tests/fixtures/deploy_target/app.py`
- Test: `tests/test_deploy_compose_integration.py` (create)

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add the marker**

In `pyproject.toml`, update `addopts` (line 34) and `markers` (lines 35-39):

```toml
addopts = "-q -m 'not slow and not temporal and not docker'"
markers = [
    "slow: builds a venv or otherwise takes >10s",
    "temporal: spawns an ephemeral Temporal dev-server via WorkflowEnvironment",
    "live: spawns a real harness CLI and spends tokens; skipped unless SDLC_LIVE_TESTS=1",
    "docker: requires a running Docker daemon; builds and runs real containers",
]
```

- [ ] **Step 2: Create the target service**

`tests/fixtures/deploy_target/app.py`:

```python
"""A trivial target the compose adapter can deploy. VERSION comes from the
image tag, so a rollback is observable from outside: the endpoint reports
which version is serving. HEALTHY=0 makes a version that fails its smoke
check without failing its build."""

import os

from fastapi import FastAPI, Response

app = FastAPI()
VERSION = os.environ.get("APP_VERSION", "unset")
HEALTHY = os.environ.get("HEALTHY", "1") == "1"


@app.get("/health")
def health(response: Response):
    if not HEALTHY:
        response.status_code = 500
    return {"version": VERSION, "healthy": HEALTHY}
```

`tests/fixtures/deploy_target/Dockerfile`:

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn
COPY app.py /app/app.py
WORKDIR /app
ARG APP_VERSION=unset
ENV APP_VERSION=$APP_VERSION
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

`tests/fixtures/deploy_target/docker-compose.yml`:

```yaml
services:
  target:
    build:
      context: .
      args:
        APP_VERSION: ${IMAGE_TAG:-unset}
    image: sdlc-deploy-target:${IMAGE_TAG:-unset}
    environment:
      HEALTHY: ${HEALTHY:-1}
    ports:
      - "18080:8000"
```

- [ ] **Step 3: Write the test**

Create `tests/test_deploy_compose_integration.py`:

```python
"""The only test proving the compose adapter's ROLLBACK MECHANICS. Everything
else proves the sequencing around them (D-8)."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import urllib.request

import pytest

from sdlc.deploy.activities import (
    DeployActivityInput,
    RollbackInput,
    SmokeCheckInput,
    deploy_apply,
    deploy_current_version,
    deploy_rollback,
    smoke_check,
)
from sdlc.models import (
    DeployConfig,
    DeployPlan,
    SmokeCheck,
    SmokeState,
)

TARGET = pathlib.Path(__file__).parent / "fixtures" / "deploy_target"
BASE_URL = "http://localhost:18080"

pytestmark = [
    pytest.mark.docker,
    pytest.mark.asyncio,
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker not on PATH"),
]


def _cfg() -> DeployConfig:
    return DeployConfig(adapter="compose", base_url=BASE_URL, readiness_timeout_s=90)


def _plan(version: str) -> DeployPlan:
    return DeployPlan(
        environment="staging",
        version=version,
        smoke_checks=[
            SmokeCheck(name="health", kind="http", path="/health", expect_status=200, timeout_s=10)
        ],
    )


def _serving_version() -> str:
    with urllib.request.urlopen(f"{BASE_URL}/health", timeout=10) as r:
        return json.load(r)["version"]


@pytest.fixture
def compose_down():
    yield
    subprocess.run(
        ["docker", "compose", "down", "-v", "--remove-orphans"],
        cwd=TARGET,
        check=False,
        capture_output=True,
    )


async def test_deploy_smoke_and_real_rollback(compose_down, monkeypatch):
    """Ship v1 (healthy), ship v2 (broken), roll back, assert v1 serves."""
    cfg, repo = _cfg(), str(TARGET)

    # --- v1: a good deploy passes its smoke check -------------------------
    await deploy_apply(DeployActivityInput(plan=_plan("v1"), cfg=cfg, repo_path=repo))
    out = await smoke_check(
        SmokeCheckInput(plan=_plan("v1"), cfg=cfg, repo_path=repo, endpoint=BASE_URL)
    )
    assert [r.state for r in out.results] == [SmokeState.PASSED]
    assert _serving_version() == "v1"

    # --- the adapter can now see what is running --------------------------
    current = await deploy_current_version(
        DeployActivityInput(plan=_plan("v2"), cfg=cfg, repo_path=repo)
    )
    assert current.version is not None

    # --- v2: builds fine, fails its smoke check ---------------------------
    monkeypatch.setenv("HEALTHY", "0")
    await deploy_apply(DeployActivityInput(plan=_plan("v2"), cfg=cfg, repo_path=repo))
    out = await smoke_check(
        SmokeCheckInput(plan=_plan("v2"), cfg=cfg, repo_path=repo, endpoint=BASE_URL)
    )
    assert out.results[0].state is SmokeState.FAILED

    # --- rollback restores the prior version, observably ------------------
    monkeypatch.setenv("HEALTHY", "1")
    await deploy_rollback(RollbackInput(plan=_plan("v2"), cfg=cfg, repo_path=repo, to_version="v1"))
    assert _serving_version() == "v1"


async def test_unreachable_service_errors_rather_than_passing(compose_down):
    """Nothing is running: every http check must be ERRORED, never PASSED."""
    cfg = DeployConfig(adapter="compose", base_url="http://localhost:18081", readiness_timeout_s=2)
    out = await smoke_check(
        SmokeCheckInput(
            plan=_plan("v1"), cfg=cfg, repo_path=str(TARGET), endpoint="http://localhost:18081"
        )
    )
    assert out.results[0].state is SmokeState.ERRORED
```

- [ ] **Step 4: Verify the default run still excludes it**

Run: `python -m pytest -q --collect-only | tail -3`
Expected: the compose integration tests are **not** collected.

- [ ] **Step 5: Run the integration test explicitly**

Run: `python -m pytest -m docker -q`
Expected: PASS (2 tests, a few minutes on first run while the image builds). Skipped if Docker is unavailable.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/fixtures/deploy_target/ \
        tests/test_deploy_compose_integration.py
git commit -m "test: real compose deploy, smoke failure and rollback

Adds a docker marker, excluded from the default run. Ships v1, ships a
broken v2, rolls back, and asserts v1 is serving again."
```

---

### Task 10: Benchmark opt-in

**Files:**
- Modify: `src/sdlc/benchmarks/models.py:152` (add `deploy_enabled` next to `research_enabled`)
- Modify: `src/sdlc/benchmarks/workflow.py:81` (set it in `_cell_config`)
- Test: `tests/test_deploy_benchmark_optin.py` (create)

**Interfaces:**
- Consumes: `PipelineConfig.deploy` (Task 2).
- Produces: `CaseSpec.deploy_enabled`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deploy_benchmark_optin.py`:

```python
"""Per-case config, no fake adapter. A case opts into stage 13 explicitly --
today no benchmark case reaches it at all."""

from __future__ import annotations

from sdlc.benchmarks.models import CaseSpec


def test_cases_do_not_deploy_by_default():
    assert CaseSpec.model_fields["deploy_enabled"].default is False


def test_a_case_can_opt_in():
    assert CaseSpec.model_fields["deploy_enabled"].annotation is bool
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_deploy_benchmark_optin.py -q`
Expected: FAIL — `KeyError: 'deploy_enabled'`

- [ ] **Step 3: Add the field**

In `src/sdlc/benchmarks/models.py`, directly after `research_enabled: bool = False` (line 152):

```python
    # E-67: run DAG stage 13 for this case. Default False -- a deploying case
    # needs a real target and a Docker daemon on the runner, which most cases
    # neither have nor want.
    deploy_enabled: bool = False
```

In `src/sdlc/benchmarks/workflow.py`, after `cfg.research_enabled = spec.research_enabled` (line 81):

```python
    cfg.deploy.enabled = spec.deploy_enabled
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_deploy_benchmark_optin.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full fast suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/benchmarks/models.py src/sdlc/benchmarks/workflow.py \
        tests/test_deploy_benchmark_optin.py
git commit -m "feat: CaseSpec.deploy_enabled opts a benchmark case into stage 13"
```

---

### Task 11: Roadmap and docs

**Files:**
- Modify: `ROADMAP.md:129` (stage 13 row), `:234` (FR-1104), `:963-969` (E-67/E-68), `:319` (ADR-19)
- Modify: `README.md` (deploy config note)

- [ ] **Step 1: Update the ROADMAP stage-13 row**

Replace line 129:

```markdown
- [x] ✅ **13 · deploy** — `DeployPlan`/`DeployReport` split (E-67), deterministic `DeploymentWorkflow` child owning apply → smoke → rollback, `deploy_failed` gate in the parent. Off by default (`PipelineConfig.deploy.enabled`). *Remaining: `devops_planner` does not yet author the plan — `FeatureWorkflow._deploy_plan` builds a single-liveness-check plan (see its docstring).*
```

- [ ] **Step 2: Mark FR-1104, E-67 and E-68**

Change `- [ ] **FR-1104**` (line 234) to `- [x] **FR-1104**`. Change `- [ ] **E-67` and `- [ ] **E-68` to `- [x]`, appending to each: `Delivered on `feat/deploy-contract`; spec `docs/superpowers/specs/2026-08-06-deploy-contract-design.md`.`

Leave **FR-1105** and **ADR-19** at `[ ]` with a note — analytics-source adapters (E-69) are still open, so neither is fully closed:

```markdown
- [ ] ⚠️ **ADR-19** Deployment targets and analytics sources are adapters, not substrate. **Deployment half done** (E-67/E-68: `src/sdlc/deploy/adapters.py`, compose + script). Analytics half open (E-69). Unresolved consequence: **OQ-9**.
```

- [ ] **Step 3: Add a README note**

Under **Run**, after the Docker Compose paragraph:

```markdown
**Deploy (stage 13).** Off by default. Enable per project with
`PipelineConfig.deploy` — `adapter: compose` (reference) or `script`
(`make deploy` / `make rollback` / `make version`). The stage applies a
frozen `DeployPlan`, runs its smoke checks, and auto-rolls-back on any check
that is not `passed`, then opens a `deploy_failed` gate. A check that could
not be evaluated is `errored` and never counts as a pass.
```

- [ ] **Step 4: Verify the roadmap has no stale claim**

Run: `grep -n "make deploy ENV=staging" ROADMAP.md README.md ARCHITECTURE.md`
Expected: no matches outside the historical E-67 description. Fix any that remain.

- [ ] **Step 5: Commit**

```bash
git add ROADMAP.md README.md
git commit -m "docs: mark E-67/E-68 delivered; note the devops_planner gap"
```

---

## Verification

Before opening a PR, confirm each of these and paste the actual output:

- [ ] `python -m pytest -q` — the default fast suite, Docker-free
- [ ] `python -m pytest -m temporal -q` — workflow integration
- [ ] `python -m pytest -m docker -q` — real compose deploy and rollback
- [ ] `python -c "import sdlc.worker"` — worker boots with the new registrations
- [ ] `grep -rn "make deploy ENV=staging" src/` returns nothing

## Known gaps at the end of this plan

State these plainly in the PR description; do not let them read as done.

1. **`devops_planner` does not author the `DeployPlan`.** Spec D-2 puts authoring at the planning stage with a freeze at the plan gate. This plan builds the contract, the freeze check, and the whole execution path, but `FeatureWorkflow._deploy_plan` still constructs a single-liveness-check plan in code. The planner integration and the plan-gate freeze are the next increment.
2. **The `deploy_failed` gate is not in `PipelineConfig.gates` defaults.** It resolves through `default_gate_policy` with an explicit `GatePolicy.HARD` fallback. Adding it to the defaults dict is a one-line follow-up once its timeout semantics are decided.
3. **E-70 is not started.** The seam is documented in `deployment.py`'s module docstring, and nothing in this plan closes it off.
