"""Held-out oracle grade (E-31): run a hidden suite against produced code
through the E-30 ToolchainAdapter, graded as fraction passing.

This module holds the pure grading logic (grade_from_junit / held_out_ok /
language_match) and the grade_oracle Temporal activity (Task 4). The pure
functions never do I/O so they unit-test without a Temporal environment or a
git repo; the activity confines all git/shell/FS work.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import defusedxml.ElementTree as DET
from temporalio import activity

from ..activities import _bounded_shell, _git
from ..toolchain.adapters import TOOLCHAINS, ToolchainKind, detect


def grade_from_junit(xml_text: str) -> tuple[float | None, int, int, str]:
    """Parse a JUnit XML report into (score, passed, graded_total, detail).

    graded_total = tests - skipped (a skip is neither a pass nor a fail, so
    it is dropped from the denominator). passed = graded_total - failures -
    errors, clamped to [0, graded_total]. Returns score=None (excluded from
    the composite, never a fabricated pass/fail) when the report is empty,
    unparseable, or has zero gradable tests -- mirroring measure_coverage's
    measured=False discipline. Parsed with defusedxml: the report is produced
    by untrusted code in the integration worktree."""
    if not xml_text.strip():
        return None, 0, 0, "no junit report"
    try:
        root = DET.fromstring(xml_text)
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        tests = fails = errs = skips = 0
        for s in suites:
            tests += int(s.get("tests", "0") or "0")
            fails += int(s.get("failures", "0") or "0")
            errs += int(s.get("errors", "0") or "0")
            skips += int(s.get("skipped", "0") or "0")
    except Exception:
        return None, 0, 0, "junit report unparseable"
    graded = tests - skips
    if graded <= 0:
        return None, 0, 0, "oracle produced no gradable tests"
    passed = max(0, min(graded, graded - fails - errs))
    return passed / graded, passed, graded, f"{passed}/{graded} oracle tests passed"


def held_out_ok(changed_files: list[str], oracle_dirname: str = "oracle") -> bool:
    """False iff the produced diff authored anything at/under the oracle dir.

    The oracle is copied in UNCOMMITTED at grade time, so any oracle path in
    the produced diff means the model itself wrote there -- a held-out breach
    the record must surface loudly."""
    prefix = oracle_dirname + "/"
    return not any(f == oracle_dirname or f.startswith(prefix)
                   for f in changed_files)


def language_match(manifest: str, detected: str | None) -> bool:
    """Manifest-declared language vs the marker-detected one (ADR-15)."""
    return detected == manifest


@dataclass
class OracleInput:
    case_id: str
    repo_url: str
    run_id: str            # child workflow id -> sdlc/<run_id>/integration
    language: str          # manifest-declared (CaseSpec.language)
    base_branch: str = "main"
    test_timeout_s: int = 600


@dataclass
class OracleGrade:
    score: float | None
    passed: int
    total: int
    language_manifest: str
    language_detected: str | None
    language_match: bool
    held_out_ok: bool
    detail: str


def _cases_dir() -> Path:
    """Root holding benchmarks/cases/<case>/oracle/. Honors SDLC_CASES_ROOT
    (read at call time) so tests point it at a temp dir, mirroring
    recorder._root / activities._worktrees_root."""
    return Path(os.environ.get(
        "SDLC_CASES_ROOT",
        str(Path(__file__).resolve().parents[3] / "benchmarks" / "cases")))


def _grade(score, passed, total, lang, detected, held, detail) -> OracleGrade:
    return OracleGrade(
        score=score, passed=passed, total=total, language_manifest=lang,
        language_detected=detected, language_match=language_match(lang, detected),
        held_out_ok=held, detail=detail)


@activity.defn
async def grade_oracle(inp: OracleInput) -> OracleGrade:
    """Run the case's held-out oracle against produced code through the
    E-30 adapter. Held out by construction: invoked only by BenchmarkWorkflow,
    strictly AFTER the child that produced the code. Fail-safe -- every failure
    returns score=None with a detail; never raises past this boundary."""
    lang = inp.language
    oracle_src = _cases_dir() / inp.case_id / "oracle"
    if not oracle_src.is_dir():
        return _grade(None, 0, 0, lang, None, True, "no oracle dir for case")
    try:
        adapter = TOOLCHAINS[ToolchainKind(lang)]
    except (ValueError, KeyError):
        return _grade(None, 0, 0, lang, None, True,
                      f"no toolchain adapter for {lang!r}")

    parent = tempfile.mkdtemp(prefix="oracle-")
    wt = os.path.join(parent, "wt")
    branch = f"sdlc/{inp.run_id}/integration"
    try:
        # Detached checkout of the produced head: --detach sidesteps git's
        # "already checked out" if the run's integration worktree still exists.
        add = _git(["worktree", "add", "--detach", wt, branch], inp.repo_url)
        if add.returncode != 0:
            return _grade(None, 0, 0, lang, None, True,
                          "no produced code (integration branch absent)")

        det = detect(wt)
        detected = det.kind.value if det else None

        diff = _git(["diff", "--name-only", f"{inp.base_branch}...HEAD"], wt)
        changed = [ln.strip() for ln in diff.stdout.splitlines() if ln.strip()]
        held = held_out_ok(changed)

        shutil.copytree(oracle_src, os.path.join(wt, "oracle"))
        report = os.path.join(wt, "oracle-report.xml")
        await _bounded_shell(adapter.oracle_test_cmd("oracle", report),
                             wt, inp.test_timeout_s)
        try:
            xml_text = Path(report).read_text(encoding="utf-8")
        except OSError:
            xml_text = ""
        score, passed, total, detail = grade_from_junit(xml_text)
        return _grade(score, passed, total, lang, detected, held, detail)
    except Exception as e:  # fail-safe: a broken grader never fails a cell
        return _grade(None, 0, 0, lang, None, True, f"grade_oracle error: {e}")
    finally:
        _git(["worktree", "remove", "--force", wt], inp.repo_url)
        shutil.rmtree(parent, ignore_errors=True)
