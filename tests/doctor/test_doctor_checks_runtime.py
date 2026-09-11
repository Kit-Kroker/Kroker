"""F2 doctor: Temporal, the board db, and derived provider keys
(spec section 5 rows 8-10, section 7; RULING 3)."""

import asyncio

import pytest

from sdlc.doctor import checks
from sdlc.doctor.models import Status


class _Role:
    def __init__(self, kind, model=None, provider=None):
        self.kind = kind
        self.model = model
        self.provider = provider


# --- row 8: Temporal --------------------------------------------------------


@pytest.mark.asyncio
async def test_temporal_reachable_reports_pass(monkeypatch):
    async def _connect(target, **kw):
        return object()

    monkeypatch.setenv("TEMPORAL_HOST", "localhost:7233")
    r = await checks.check_temporal(connect=_connect)
    assert r.status is Status.PASS
    assert "localhost:7233" in r.detail


@pytest.mark.asyncio
async def test_temporal_unreachable_reports_fail(monkeypatch):
    async def _connect(target, **kw):
        raise RuntimeError("connection refused")

    monkeypatch.setenv("TEMPORAL_HOST", "localhost:7233")
    r = await checks.check_temporal(connect=_connect)
    assert r.status is Status.FAIL
    assert "connection refused" in r.detail


@pytest.mark.asyncio
async def test_temporal_hang_times_out_rather_than_blocking(monkeypatch):
    """Client.connect takes no timeout parameter, so the probe wraps it in
    asyncio.wait_for. Without that a doctor run against a black-holed host
    never returns."""

    async def _connect(target, **kw):
        await asyncio.sleep(30)

    monkeypatch.setattr(checks, "_TEMPORAL_TIMEOUT_S", 0.05)
    r = await checks.check_temporal(connect=_connect)
    assert r.status is Status.FAIL
    assert "timed out" in r.detail


# --- row 9: board db (RULING 3) ---------------------------------------------


def test_stock_default_reports_pass_with_the_resolved_absolute_path(monkeypatch, tmp_path):
    """RULING 3: silence on the stock default. SDLC_BOARD_DB unset resolves to
    the relative runs/board.sqlite3; warning there would fire on every install
    and make --strict exit 1 out of the box."""
    monkeypatch.delenv("SDLC_BOARD_DB", raising=False)
    monkeypatch.chdir(tmp_path)
    r = checks.check_board_db()
    assert r.status is Status.PASS
    # startswith on the resolved prefix, not detail.split()[0]: a temp path
    # containing a space would break the split, and on Windows it often does.
    assert r.detail.startswith(str((tmp_path / "runs" / "board.sqlite3").resolve()))


def test_explicitly_relative_path_reports_warn(monkeypatch, tmp_path):
    """The hazard bites when an operator CHOSE a path and missed that it is
    cwd-relative: two launch directories, two databases, no error."""
    monkeypatch.setenv("SDLC_BOARD_DB", "data/board.sqlite3")
    monkeypatch.chdir(tmp_path)
    r = checks.check_board_db()
    assert r.status is Status.WARN
    assert "relative" in r.detail.lower()
    assert "SDLC_BOARD_DB" in r.detail


def test_explicitly_absolute_path_reports_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    assert checks.check_board_db().status is Status.PASS


def test_unwritable_parent_reports_fail(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "nested" / "board.sqlite3"))
    monkeypatch.setattr(checks.os, "access", lambda p, mode: False)
    r = checks.check_board_db()
    assert r.status is Status.FAIL
    assert "not writable" in r.detail


def test_board_check_never_creates_anything(monkeypatch, tmp_path):
    """SG-2. board.schema.connect() makes the parent directory AND the sqlite
    file (board/schema.py:162-174). Doctor must not go near it."""
    target = tmp_path / "nested" / "deep" / "board.sqlite3"
    monkeypatch.setenv("SDLC_BOARD_DB", str(target))
    checks.check_board_db()
    assert not target.exists()
    assert not target.parent.exists()


# --- row 10: derived provider keys ------------------------------------------


def test_derives_anthropic_key_from_a_proposer_role(monkeypatch):
    monkeypatch.setattr(
        checks, "load_registry", lambda: {"qa": _Role("proposer", model="anthropic:glm-5.2")}
    )
    monkeypatch.setattr(checks, "parse_env_example", lambda: {})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real")
    r = checks.check_provider_keys()
    assert r.status is Status.PASS
    assert "ANTHROPIC_API_KEY" in r.detail


def test_missing_derived_key_reports_fail(monkeypatch):
    monkeypatch.setattr(
        checks, "load_registry", lambda: {"qa": _Role("proposer", model="anthropic:glm-5.2")}
    )
    monkeypatch.setattr(checks, "parse_env_example", lambda: {})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = checks.check_provider_keys()
    assert r.status is Status.FAIL
    assert "ANTHROPIC_API_KEY" in r.detail


def test_placeholder_derived_key_reports_fail(monkeypatch):
    monkeypatch.setattr(
        checks, "load_registry", lambda: {"qa": _Role("proposer", model="anthropic:glm-5.2")}
    )
    monkeypatch.setattr(
        checks, "parse_env_example", lambda: {"ANTHROPIC_API_KEY": "your-zai-api-key"}
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "your-zai-api-key")
    assert checks.check_provider_keys().status is Status.FAIL


def test_research_role_derives_its_provider_key(monkeypatch):
    monkeypatch.setattr(
        checks,
        "load_registry",
        lambda: {"research": _Role("research", model="anthropic:glm-5.2", provider="exa")},
    )
    monkeypatch.setattr(checks, "parse_env_example", lambda: {})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real")
    monkeypatch.setenv("EXA_API_KEY", "exa-real")
    r = checks.check_provider_keys()
    assert r.status is Status.PASS
    assert "EXA_API_KEY" in r.detail


def test_harness_roles_derive_no_key(monkeypatch):
    """A harness role's model is resolved by the coding CLI, which
    authenticates out of band -- opencode.json carries no credentials and
    build_agents skips harness roles (agents/loader.py:447). Demanding an env
    var for them would be a check that can only fire falsely."""
    monkeypatch.setattr(
        checks,
        "load_registry",
        lambda: {"dev": _Role("harness", model="zai-coding-plan/glm-5.2")},
    )
    monkeypatch.setattr(checks, "parse_env_example", lambda: {})
    r = checks.check_provider_keys()
    assert r.status is Status.SKIP
    assert "no proposer role" in r.detail


def test_unmapped_family_reports_skip_naming_it_rather_than_guessing(monkeypatch):
    monkeypatch.setattr(
        checks, "load_registry", lambda: {"qa": _Role("proposer", model="mistral:large")}
    )
    monkeypatch.setattr(checks, "parse_env_example", lambda: {})
    r = checks.check_provider_keys()
    assert r.status is Status.SKIP
    assert "mistral" in r.detail


def test_registry_failure_reports_skip_rather_than_a_second_fail(monkeypatch):
    """Row 1 already reports a broken registry. Row 10 must not repeat it."""
    from sdlc.agents.loader import RegistryError

    def _boom():
        raise RegistryError("missing role")

    monkeypatch.setattr(checks, "load_registry", _boom)
    r = checks.check_provider_keys()
    assert r.status is Status.SKIP
    assert "registry" in r.detail.lower()


# --- the registry -----------------------------------------------------------


def test_checks_registry_has_twelve_entries():
    """RULING 4: twelve checks ship."""
    assert len(checks.CHECKS) == 12


def test_registry_names_are_unique():
    names = [c.name for c in checks.CHECKS]
    assert len(names) == len(set(names))
