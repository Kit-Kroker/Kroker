"""_head_run's coverage-unavailable retry, across adapter languages (FR-915).

The retry must fire not only on pytest's usage error (the coverage plugin
absent) but on the shell's language-neutral command-not-found exits: a Go
repo whose `gocover-cobertura` converter is missing dies at the command's
`&&` tail AFTER the JUnit pipe has already landed, and the honest move is
the same -- re-run without coverage, never grade the suite failed-to-run.
"""

import pathlib

import pytest

from sdlc.stages.merge import scoping
from sdlc.toolchain.adapters import GoToolchain, PythonToolchain

# go-junit-report shape: the classname IS the package's import path, which
# GoToolchain.node_id passes through unmangled.
GO_JUNIT = """<?xml version="1.0" encoding="UTF-8"?><testsuites>
<testsuite name="example.com/m/a" tests="1" failures="0" errors="0" skipped="0">
<testcase classname="example.com/m/a" name="TestAlpha" time="0.01"/>
</testsuite>
</testsuites>"""

# pytest legacy shape: file attribute plus dotted classname, rebuilt by the
# ABC default into the collected id shape.
PY_JUNIT = """<?xml version="1.0" encoding="UTF-8"?><testsuites>
<testsuite name="tests.test_a" tests="1" failures="0" errors="0" skipped="0">
<testcase classname="tests.test_a" name="test_a" file="tests/test_a.py" line="3"/>
</testsuite>
</testsuites>"""


def _fake_shell(monkeypatch, exits: list[int], junit_body: str) -> list[str]:
    """_bounded_shell fake: recorded commands, exits handed back in order.

    The JUnit pipe lands on EVERY call -- a failing `&&` tail runs after the
    redirect already succeeded, which is exactly the degraded situation the
    retry exists for.
    """
    calls: list[str] = []

    async def fake(cmd, cwd, timeout_s, env=None):
        calls.append(cmd)
        pathlib.Path(cwd, scoping.JUNIT).write_text(junit_body, encoding="utf-8")
        return exits.pop(0), "suite output"

    monkeypatch.setattr(scoping, "_bounded_shell", fake)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter", "code", "cov_marker", "junit", "expected"),
    [
        # POSIX sh reports command-not-found as 127; cmd.exe as 9009. Either
        # way the missing binary is the coverage converter, not the runner.
        (GoToolchain(), 127, "gocover-cobertura", GO_JUNIT, {"example.com/m/a::TestAlpha": True}),
        (GoToolchain(), 9009, "gocover-cobertura", GO_JUNIT, {"example.com/m/a::TestAlpha": True}),
        # The legacy pytest path: usage error 4 (coverage plugin unavailable)
        # must keep retrying exactly as before.
        (PythonToolchain(), 4, "--cov", PY_JUNIT, {"tests/test_a.py::test_a": True}),
    ],
)
async def test_coverage_unavailable_retries_without_coverage_and_grades(
    tmp_path, monkeypatch, adapter, code, cov_marker, junit, expected
):
    calls = _fake_shell(monkeypatch, [code, 0], junit)
    res = await scoping._head_run(adapter, str(tmp_path), None, 30)
    # The suite is graded from the JUnit report, not the converter's exit.
    assert res == (expected, "suite output")
    assert len(calls) == 2
    assert cov_marker in calls[0]
    assert cov_marker not in calls[1]  # the retry asked for coverage=False


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [127, 9009])
async def test_command_not_found_on_both_runs_stays_not_collected(tmp_path, monkeypatch, code):
    # If the RUNNER itself is missing (not just the converter), the retry
    # fails the same way and _head_run returns its error string -- which
    # scoped_tests turns into NOT_COLLECTED. FR-915's safe direction
    # survives the retry; it never manufactures a pass.
    _fake_shell(monkeypatch, [code, code], GO_JUNIT)
    res = await scoping._head_run(GoToolchain(), str(tmp_path), None, 30)
    assert isinstance(res, str) and "failed to run" in res
