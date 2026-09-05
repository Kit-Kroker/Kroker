"""FR-1105/ADR-19. The adapter object is PURE -- command strings and identity
only, never a subprocess. Same rule and same shape as toolchain/adapters.py."""

from __future__ import annotations

from sdlc.core.models import (
    DeployConfig,
)
from sdlc.deploy.adapters import (
    ADAPTERS,
    ComposeAdapter,
    DeployKind,
    ScriptAdapter,
    resolve,
)
from sdlc.stages.deploy.models import (
    DeployPlan,
    FeatureFlag,
)


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
