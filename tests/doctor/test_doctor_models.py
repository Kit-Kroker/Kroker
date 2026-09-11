"""F2 doctor: the result model and the exit-code rule (spec section 4)."""

from sdlc.doctor.models import CheckResult, Status, exit_code


def test_constructors_set_their_status():
    assert CheckResult.ok("git", "found").status is Status.PASS
    assert CheckResult.warn("board db", "relative").status is Status.WARN
    assert CheckResult.fail("gh", "not on PATH").status is Status.FAIL
    assert CheckResult.skip("crew CLIs", "no crew assets").status is Status.SKIP


def test_result_carries_name_and_detail():
    r = CheckResult.fail("gh", "not on PATH")
    assert r.name == "gh"
    assert r.detail == "not on PATH"


def test_clean_run_exits_zero():
    results = [CheckResult.ok("a", ""), CheckResult.skip("b", "off")]
    assert exit_code(results, strict=False) == 0
    assert exit_code(results, strict=True) == 0


def test_a_fail_exits_one_in_both_modes():
    results = [CheckResult.ok("a", ""), CheckResult.fail("b", "broken")]
    assert exit_code(results, strict=False) == 1
    assert exit_code(results, strict=True) == 1


def test_a_warn_exits_zero_unless_strict():
    results = [CheckResult.ok("a", ""), CheckResult.warn("b", "hazard")]
    assert exit_code(results, strict=False) == 0
    assert exit_code(results, strict=True) == 1


def test_skip_never_affects_the_exit_code():
    """SKIP means 'not required here', so it is not a finding to act on."""
    results = [CheckResult.skip("a", "off"), CheckResult.skip("b", "off")]
    assert exit_code(results, strict=True) == 0
