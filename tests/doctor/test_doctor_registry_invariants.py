"""F2 doctor: structural guarantees over the whole CHECKS registry.

These enforce the two properties no individual check's tests can: that every
check is PROVEN able to fire (spec section 3 rule 2 -- a check that cannot
fail is a defect wearing a green tick), and that a doctor run writes nothing
(the zero side-effect budget; SG-2).
"""

import inspect
from pathlib import Path

import pytest

from sdlc.doctor import checks
from sdlc.doctor.models import CheckResult, Status

_TEST_DIR = Path(__file__).parent


def test_every_check_has_a_test_that_drives_it_to_a_non_pass_outcome():
    """A check with no test is not proven able to fire. This asserts the two
    halves it can cheaply prove: every check function is named somewhere in
    the check test corpus, and that corpus exercises all three non-PASS
    outcomes. It does NOT pair each name to its own non-PASS assertion --
    that pairing is enforced by review, and held today (every one of the
    twelve has at least one test driving it to a non-PASS outcome)."""
    corpus = "\n".join(
        p.read_text(encoding="utf-8") for p in _TEST_DIR.glob("test_doctor_checks_*.py")
    )
    for check in checks.CHECKS:
        fn_name = check.fn.__name__
        assert fn_name in corpus, f"{fn_name} has no test at all"
    for token in ("Status.FAIL", "Status.WARN", "Status.SKIP"):
        assert token in corpus


@pytest.mark.parametrize("check", checks.CHECKS, ids=lambda c: c.name)
def test_every_check_is_a_zero_argument_callable(check):
    """run_checks calls each with no arguments. A check that needs a
    parameter must give it a default (check_temporal's connect seam does)."""
    sig = inspect.signature(check.fn)
    required = [
        p
        for p in sig.parameters.values()
        if p.default is inspect.Parameter.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
    ]
    assert required == [], f"{check.fn.__name__} requires {[p.name for p in required]}"


@pytest.mark.parametrize("check", checks.CHECKS, ids=lambda c: c.name)
def test_is_async_flag_matches_the_function(check):
    """A mismatch would make run_checks either await a plain value or return
    an un-awaited coroutine as a result."""
    assert inspect.iscoroutinefunction(check.fn) is check.is_async


def _registry_without_temporal():
    """CHECKS with the Temporal row replaced by a stub, so a full-run test
    needs no server. Substituting the REGISTRY, not the module attribute:
    CHECKS holds bound function references captured at import, so
    monkeypatch.setattr(checks, "check_temporal", ...) would not reach it."""
    stub = checks.Check(
        "temporal", lambda: CheckResult.skip("temporal", "not probed in this test"), False
    )
    return tuple(stub if c.name == "temporal" else c for c in checks.CHECKS)


@pytest.mark.asyncio
async def test_a_full_run_returns_a_result_per_check_and_raises_nothing(monkeypatch):
    """SG-3: a check owns its own failure modes. Point every check at a
    hostile environment -- nothing on PATH, no registry above cwd -- and
    confirm each still returns a CheckResult instead of raising."""
    monkeypatch.setattr(checks.shutil, "which", lambda c: None)
    registry = _registry_without_temporal()
    results = await checks.run_checks(registry)
    assert len(results) == len(checks.CHECKS)
    assert all(isinstance(r, CheckResult) for r in results)
    assert all(isinstance(r.status, Status) for r in results)


@pytest.mark.asyncio
async def test_a_full_run_creates_no_files(monkeypatch, tmp_path):
    """SG-2, the zero side-effect budget. Run every check with cwd and the
    board path pointed inside an empty directory, and assert it is still
    empty afterwards.

    tmp_path is chosen as cwd deliberately: it has no pyproject.toml above
    it, so the registry, policy and .env.example discovery walks all fail --
    which is a hostile environment for the checks AND removes any chance of
    the assertion tripping on a file the real checkout owns."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "nested" / "board.sqlite3"))
    await checks.run_checks(_registry_without_temporal())
    assert list(tmp_path.iterdir()) == []
