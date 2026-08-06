"""FR-901/FR-902: does this repository build, and does its suite run?

The pure decision table lives here; the subprocess work is in the activity.
Two rules run through every branch (spec §6):

  * a TIMEOUT is not_collected, never a measured failure -- a timeout is an
    absent measurement, not a negative result;
  * a failed install leaves `runnable` not_collected and skips the test step
    entirely, because running a suite whose dependencies are missing measures
    the failed install a second time.
"""
from __future__ import annotations

from dataclasses import dataclass

from ...measurement import Measurement
from ..models import (
    FixClass, M_BUILDABLE, M_RUNNABLE, SignalResult, TriageFinding,
)

SIGNAL_ID = "build_probe"
VERSION = 1

# Captured output is tail-capped before it enters the artifact: a failing
# `pip install` can emit megabytes, and the artifact is a report, not a log.
MAX_DETAIL_CHARS = 4000

TIMEOUT_CODE = -1          # _bounded_shell's sentinel


@dataclass
class StepOutcome:
    code: int
    output: str


def _tail(text: str) -> str:
    return text[-MAX_DETAIL_CHARS:]


def _finding(rule: str, severity: str, detail: str,
             fix_class: FixClass) -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class)


def interpret(toolchain_found: bool,
              install: StepOutcome | None,
              build: StepOutcome | None,
              test: StepOutcome | None,
              test_verdict: str | None) -> SignalResult:
    """The whole decision table, pure.

    `install`/`build`/`test` are None when the step did not run: no adapter
    command for it, or an earlier step made it meaningless. `test_verdict` is
    the adapter's classify_test_exit output, or None when the suite did not
    run or timed out.
    """
    findings: list[TriageFinding] = []

    if not toolchain_found:
        findings.append(_finding(
            "no_toolchain_marker", "high",
            "No recognized toolchain marker file at the repository root, so "
            "the build and the suite cannot be probed. Establishing a "
            "recognizable project layout is design work.",
            FixClass.STRUCTURAL))
        return SignalResult(
            signal=SIGNAL_ID, version=VERSION,
            collected=Measurement.measured(float(len(findings))),
            findings=findings,
            metrics={
                M_BUILDABLE: Measurement.not_collected(
                    "no toolchain marker resolved"),
                M_RUNNABLE: Measurement.not_collected(
                    "no toolchain marker resolved"),
            })

    # --- buildable -----------------------------------------------------
    install_ok = False
    if install is None:
        buildable = Measurement.not_collected(
            "adapter declares no install command for this marker")
    elif install.code == TIMEOUT_CODE:
        buildable = Measurement.not_collected(f"install: {install.output}")
    elif install.code != 0:
        buildable = Measurement.measured(0.0)
        findings.append(_finding(
            "install_failed", "critical",
            f"Dependency install failed (exit {install.code}). "
            f"{_tail(install.output)}",
            FixClass.JUDGEMENT))
    else:
        install_ok = True
        buildable = Measurement.measured(1.0)

    if install_ok and build is not None:
        if build.code == TIMEOUT_CODE:
            buildable = Measurement.not_collected(f"build: {build.output}")
        elif build.code != 0:
            buildable = Measurement.measured(0.0)
            findings.append(_finding(
                "build_failed", "critical",
                f"Build failed (exit {build.code}). {_tail(build.output)}",
                FixClass.JUDGEMENT))

    # --- runnable ------------------------------------------------------
    if install is not None and not install_ok:
        # Deliberate: the test step is skipped, not merely ignored.
        runnable = Measurement.not_collected(
            "install failed, so a test run would re-measure that rather than "
            "runnability")
    elif test is None:
        runnable = Measurement.not_collected(
            "adapter declares no test command")
    elif test.code == TIMEOUT_CODE:
        runnable = Measurement.not_collected(f"tests: {test.output}")
    elif test_verdict == "no_tests":
        # baseline owns the no_tests FINDING; reporting it here too would be
        # the two-implementations failure FR-902 forbids.
        runnable = Measurement.not_collected(
            "no tests were collected, so runnability was not measured")
    elif test_verdict == "failed_to_run":
        runnable = Measurement.measured(0.0)
        findings.append(_finding(
            "tests_failed_to_run", "high",
            f"The test suite could not be collected or crashed the runner "
            f"(exit {test.code}). {_tail(test.output)}",
            FixClass.JUDGEMENT))
    else:
        runnable = Measurement.measured(1.0)

    return SignalResult(
        signal=SIGNAL_ID, version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={M_BUILDABLE: buildable, M_RUNNABLE: runnable})
