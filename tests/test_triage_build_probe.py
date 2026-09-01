"""The probe's decision table is pure and tested without a subprocess; the
one end-to-end test builds a real venv and is marked slow.
"""

import subprocess

import pytest

from sdlc.measurement import CollectionState
from sdlc.triage.models import M_BUILDABLE, M_RUNNABLE
from sdlc.triage.signals import build_probe as bp
from sdlc.triage.signals.build_probe import StepOutcome

TIMEOUT = StepOutcome(code=-1, output="command timed out after 600s")
OK = StepOutcome(code=0, output="")
FAIL = StepOutcome(code=1, output="ERROR: could not resolve dependency")


def _rules(r):
    return {f.rule for f in r.findings}


def test_no_toolchain_marker_is_a_finding_not_an_error():
    r = bp.interpret(toolchain_found=False, install=None, build=None, test=None, test_verdict=None)
    assert _rules(r) == {"no_toolchain_marker"}
    assert r.collected.state is CollectionState.MEASURED
    for key in (M_BUILDABLE, M_RUNNABLE):
        assert r.metrics[key].state is CollectionState.NOT_COLLECTED
        assert "marker" in r.metrics[key].reason


def test_green_install_and_tests_is_measured_one_on_both():
    r = bp.interpret(True, install=OK, build=None, test=OK, test_verdict="ran")
    assert r.metrics[M_BUILDABLE].value == 1.0
    assert r.metrics[M_RUNNABLE].value == 1.0
    assert r.findings == []


def test_failing_tests_still_count_as_runnable():
    # exit 1 = tests ran and failed. Runnable is about whether the suite
    # executes, not whether it passes.
    r = bp.interpret(
        True,
        install=OK,
        build=None,
        test=StepOutcome(code=1, output="2 failed"),
        test_verdict="ran",
    )
    assert r.metrics[M_RUNNABLE].value == 1.0


def test_install_failure_is_measured_zero_and_a_finding():
    r = bp.interpret(True, install=FAIL, build=None, test=None, test_verdict=None)
    assert r.metrics[M_BUILDABLE].value == 0.0
    assert "install_failed" in _rules(r)


def test_install_failure_leaves_runnable_not_collected():
    # Running a suite whose deps are absent measures the failed install a
    # second time, not runnability.
    r = bp.interpret(True, install=FAIL, build=None, test=None, test_verdict=None)
    m = r.metrics[M_RUNNABLE]
    assert m.state is CollectionState.NOT_COLLECTED
    assert "install failed" in m.reason


def test_install_timeout_is_not_collected_not_a_measured_failure():
    r = bp.interpret(True, install=TIMEOUT, build=None, test=None, test_verdict=None)
    m = r.metrics[M_BUILDABLE]
    assert m.state is CollectionState.NOT_COLLECTED
    assert "timed out" in m.reason
    assert "install_failed" not in _rules(r)


def test_install_timeout_runnable_reason_says_timed_out_not_failed():
    # The runnable reason exists to say precisely why runnability was not
    # measured; a timeout must read as a timeout, not as an install failure.
    r = bp.interpret(True, install=TIMEOUT, build=None, test=None, test_verdict=None)
    m = r.metrics[M_RUNNABLE]
    assert m.state is CollectionState.NOT_COLLECTED
    assert "timed out" in m.reason
    assert "failed" not in m.reason


def test_build_failure_makes_buildable_zero():
    r = bp.interpret(True, install=OK, build=FAIL, test=None, test_verdict=None)
    assert r.metrics[M_BUILDABLE].value == 0.0
    assert "build_failed" in _rules(r)


def test_no_tests_collected_leaves_runnable_not_collected():
    r = bp.interpret(
        True,
        install=OK,
        build=None,
        test=StepOutcome(code=5, output="no tests ran"),
        test_verdict="no_tests",
    )
    m = r.metrics[M_RUNNABLE]
    assert m.state is CollectionState.NOT_COLLECTED
    assert "no tests" in m.reason
    # baseline owns the no_tests FINDING; the probe must not double-report it.
    assert "no_tests" not in _rules(r)


def test_suite_that_cannot_be_collected_is_measured_zero():
    r = bp.interpret(
        True,
        install=OK,
        build=None,
        test=StepOutcome(code=3, output="INTERNALERROR"),
        test_verdict="failed_to_run",
    )
    assert r.metrics[M_RUNNABLE].value == 0.0
    assert "tests_failed_to_run" in _rules(r)


def test_test_timeout_is_not_collected():
    r = bp.interpret(True, install=OK, build=None, test=TIMEOUT, test_verdict=None)
    assert r.metrics[M_RUNNABLE].state is CollectionState.NOT_COLLECTED


def test_no_install_command_leaves_buildable_not_collected():
    r = bp.interpret(True, install=None, build=None, test=OK, test_verdict="ran")
    m = r.metrics[M_BUILDABLE]
    assert m.state is CollectionState.NOT_COLLECTED
    assert "install command" in m.reason


def test_finding_output_is_capped():
    huge = StepOutcome(code=1, output="x" * 100_000)
    r = bp.interpret(True, install=huge, build=None, test=None, test_verdict=None)
    f = next(f for f in r.findings if f.rule == "install_failed")
    assert len(f.detail) <= bp.MAX_DETAIL_CHARS + 200


# ---- end to end --------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
async def test_probe_runs_a_real_repo_end_to_end(tmp_path):
    from sdlc.triage.activities import TriageProbeInput, triage_build_probe

    def _run(args, cwd):
        return subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            encoding="utf-8",
            check=True,
            stdin=subprocess.DEVNULL,
        )

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "probe-fixture"\nversion = "0.1.0"\n'
        'requires-python = ">=3.11"\n\n'
        # Explicit module declaration: modern setuptools' auto-discovery
        # refuses the build when it sees two ambiguous top-level modules
        # (app + test_app). Declaring the module keeps the fixture buildable,
        # which is the happy-path assumption this end-to-end test exercises.
        '[tool.setuptools]\npy-modules = ["app"]\n',
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text(
        "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n", encoding="utf-8"
    )
    _run(["git", "init", "-q"], tmp_path)
    _run(["git", "config", "user.email", "t@example.com"], tmp_path)
    _run(["git", "config", "user.name", "T"], tmp_path)
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "one"], tmp_path)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        check=True,
        stdin=subprocess.DEVNULL,
    ).stdout.strip()

    r = await triage_build_probe(TriageProbeInput(repo_dir=str(tmp_path), commit_sha=sha))

    assert r.metrics[M_BUILDABLE].value == 1.0
    assert r.metrics[M_RUNNABLE].value == 1.0
    # D8: the probe must not have written into the repository under audit.
    assert not (tmp_path / ".sdlc-venv").exists()
    assert not list(tmp_path.glob("*.egg-info"))
