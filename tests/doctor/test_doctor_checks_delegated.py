"""F2 doctor: the five checks that delegate to an upstream validator
(spec section 5 rows 1, 2, 3, 11, 12; rulings 1 and 2).

Each test fakes the UPSTREAM function, not the rule. Doctor owns no second
copy of any rule (spec section 3), so there is nothing else to test here:
the only behaviour doctor adds is turning a raise into a CheckResult and
turning silence into SKIP rather than PASS.
"""

import pytest

from sdlc.doctor import checks
from sdlc.doctor.models import Status

# --- row 1: agents registry -------------------------------------------------


def test_registry_ok_reports_pass_with_the_role_count(monkeypatch):
    monkeypatch.setattr(checks, "load_registry", lambda: {"dev": object(), "qa": object()})
    monkeypatch.setattr(checks, "validate_registry", lambda roles: None)
    r = checks.check_agents_registry()
    assert r.status is Status.PASS
    assert "2 roles" in r.detail


def test_registry_error_reports_fail_and_says_it_is_the_first_error_only(monkeypatch):
    """validate_registry raises on its FIRST structural error by design, so
    doctor's accumulate-everything promise does not hold inside this one row.
    The detail must say so (spec section 4)."""
    from sdlc.agents.loader import RegistryError

    def _boom():
        raise RegistryError("role 'reviewer': missing instructions.md")

    monkeypatch.setattr(checks, "load_registry", _boom)
    r = checks.check_agents_registry()
    assert r.status is Status.FAIL
    assert "missing instructions.md" in r.detail
    assert "first error" in r.detail


# --- row 2: crew CLIs -------------------------------------------------------


def test_crew_clis_ok_reports_pass(monkeypatch):
    monkeypatch.setattr(checks, "validate_crew_clis", lambda: None)
    monkeypatch.setattr(checks, "_crew_layouts_present", lambda: True)
    assert checks.check_crew_clis().status is Status.PASS


def test_crew_clis_error_reports_fail(monkeypatch):
    from sdlc.crew.loader import CrewConfigError

    def _boom():
        raise CrewConfigError("layout 'code' role 'dev' needs 'opencode'")

    monkeypatch.setattr(checks, "_crew_layouts_present", lambda: True)
    monkeypatch.setattr(checks, "validate_crew_clis", _boom)
    r = checks.check_crew_clis()
    assert r.status is Status.FAIL
    assert "opencode" in r.detail


def test_crew_clis_with_no_crew_assets_reports_skip_not_pass(monkeypatch):
    """validate_crew_clis returns early and silently when the checkout has no
    crew/layouts (crew/loader.py:210-211). Rendering that silence as PASS
    would claim doctor verified something it never looked at."""
    monkeypatch.setattr(checks, "_crew_layouts_present", lambda: False)
    r = checks.check_crew_clis()
    assert r.status is Status.SKIP
    assert "no crew" in r.detail.lower()


# --- row 3: harness drift ---------------------------------------------------


def test_harness_drift_none_reports_pass(monkeypatch):
    monkeypatch.setattr(checks, "check_harness_versions", lambda: [])
    monkeypatch.setattr(checks, "_pinned_harness_clis_on_path", lambda: ["claude", "opencode"])
    r = checks.check_harness_drift()
    assert r.status is Status.PASS


def test_harness_drift_reports_warn_carrying_every_finding(monkeypatch):
    monkeypatch.setattr(
        checks,
        "check_harness_versions",
        lambda: ["harness version drift: opencode is 1.19.0, pinned 1.18.4"],
    )
    monkeypatch.setattr(checks, "_pinned_harness_clis_on_path", lambda: ["opencode"])
    r = checks.check_harness_drift()
    assert r.status is Status.WARN
    assert "1.18.4" in r.detail


def test_harness_drift_with_no_pinned_cli_on_path_reports_skip(monkeypatch):
    """check_harness_versions skips an absent or unpinned CLI silently
    (harness/registry.py:33-37). Every leg quiet means SKIP, never PASS."""
    monkeypatch.setattr(checks, "check_harness_versions", lambda: [])
    monkeypatch.setattr(checks, "_pinned_harness_clis_on_path", lambda: [])
    r = checks.check_harness_drift()
    assert r.status is Status.SKIP
    assert "not on PATH" in r.detail


# --- rows 11 and 12: policy assets ------------------------------------------


def test_containment_policy_ok_reports_pass_with_the_rule_count(monkeypatch):
    class _P:
        version = 1
        rules = [object(), object()]

    monkeypatch.setattr(checks, "load_policy", lambda: _P())
    r = checks.check_containment_policy()
    assert r.status is Status.PASS
    assert "2 rules" in r.detail


def test_containment_policy_error_reports_warn_not_fail(monkeypatch):
    """RULING 2: WARN, not FAIL. containment_enabled defaults False
    (core/models.py:377), so a malformed asset is named without blocking an
    operator whose setup is otherwise sound."""
    from sdlc.harness.containment import ContainmentError

    def _boom():
        raise ContainmentError("duplicate rule id 'egress-allowlist'")

    monkeypatch.setattr(checks, "load_policy", _boom)
    r = checks.check_containment_policy()
    assert r.status is Status.WARN
    assert "duplicate rule id" in r.detail


def test_notify_routes_ok_reports_pass(monkeypatch):
    class _R:
        version = 1

    monkeypatch.setattr(checks, "load_routes", lambda: _R())
    assert checks.check_notify_routes().status is Status.PASS


def test_notify_routes_error_reports_warn_not_fail(monkeypatch):
    from sdlc.notify.routes import NotifyConfigError

    def _boom():
        raise NotifyConfigError("unknown notifier 'slak' at gates.merge.primary")

    monkeypatch.setattr(checks, "load_routes", _boom)
    r = checks.check_notify_routes()
    assert r.status is Status.WARN
    assert "slak" in r.detail


@pytest.mark.parametrize(
    "fn",
    [
        "check_agents_registry",
        "check_crew_clis",
        "check_harness_drift",
        "check_containment_policy",
        "check_notify_routes",
    ],
)
def test_no_delegated_check_raises_on_an_unexpected_exception(monkeypatch, fn):
    """A check owns its own failure modes. If an upstream validator raises
    something the check did not anticipate, the check still returns a result
    -- run_doctor must never need a rescue wrapper (SG-3)."""
    for name in (
        "load_registry",
        "validate_crew_clis",
        "check_harness_versions",
        "load_policy",
        "load_routes",
    ):
        monkeypatch.setattr(
            checks, name, lambda *a, **k: (_ for _ in ()).throw(OSError("disk gone"))
        )
    monkeypatch.setattr(checks, "_crew_layouts_present", lambda: True)
    monkeypatch.setattr(checks, "_pinned_harness_clis_on_path", lambda: ["claude"])
    result = getattr(checks, fn)()
    assert result.status in (Status.WARN, Status.FAIL)
    assert "disk gone" in result.detail
