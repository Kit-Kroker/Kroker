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
from dataclasses import dataclass, field
from pathlib import Path

import defusedxml.ElementTree as DET
from temporalio import activity

from ..activities import _bounded_shell, _git
from ..toolchain.adapters import TOOLCHAINS, ToolchainKind, detect
from .judge import JudgeInput, _judge_sync
from .tasks import TaskGrade, grade_tasks, load_task_suite


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


def grade_testcases_from_junit(xml_text: str) -> dict[str, bool]:
    """Parse individual <testcase> elements into {"node_id": passed}.

    The key prefers pytest's own file::name node-id shape (using the
    `file` attribute pytest's junit-xml already emits per testcase), so a
    case author's tasks.yaml oracle_tests entries can read exactly like a
    pytest node-id (e.g. "test_crud.py::test_create_todo"). Falls back to
    classname::name, then bare name, for hand-written JUnit fixtures that
    omit `file`. A <skipped> testcase is dropped entirely -- neither pass
    nor fail, mirroring grade_from_junit's denominator discipline.
    Malformed/empty XML yields {} rather than raising."""
    if not xml_text.strip():
        return {}
    try:
        root = DET.fromstring(xml_text)
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    except Exception:
        return {}
    out: dict[str, bool] = {}
    for s in suites:
        for tc in s.iter("testcase"):
            if tc.find("skipped") is not None:
                continue
            name = tc.get("name", "")
            file_attr = tc.get("file")
            classname = tc.get("classname", "")
            if file_attr:
                key = f"{file_attr}::{name}"
            elif classname:
                key = f"{classname}::{name}"
            else:
                key = name
            failed = tc.find("failure") is not None or tc.find("error") is not None
            out[key] = not failed
    return out


DIFF_JUDGE_MAX_CHARS = 20_000


def _truncate_diff(text: str, max_chars: int = DIFF_JUDGE_MAX_CHARS) -> str:
    """Cap the diff sent to the judge so an oversized diff can't blow up
    token cost or make judge output unreliable -- keeps rubric grading a
    deterministic, boundable operation regardless of how large a produced
    diff gets. Short text passes through unchanged; long text is cut to
    ``max_chars`` with a clear marker noting how much was omitted."""
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n...[diff truncated, {omitted} chars omitted]"


def _safe_heartbeat() -> None:
    """activity.heartbeat() outside a real Temporal activity execution
    context (e.g. a plain-async-function test call) raises RuntimeError --
    swallow that so a liveness signal never breaks the fail-safe discipline
    that governs this module (a heartbeat call must never crash a grade)."""
    try:
        activity.heartbeat()
    except Exception:
        pass


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
    author_model: str = ""          # cell's dev model; only rubric tasks need it
    judge_model: str | None = None  # spec.judge_model; only rubric tasks need it


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
    task_grades: list[TaskGrade] = field(default_factory=list)


def _cases_dir() -> Path:
    """Root holding benchmarks/cases/<case>/oracle/. Honors SDLC_CASES_ROOT
    (read at call time) so tests point it at a temp dir, mirroring
    recorder._root / activities._worktrees_root."""
    return Path(os.environ.get(
        "SDLC_CASES_ROOT",
        str(Path(__file__).resolve().parents[3] / "benchmarks" / "cases")))


def _grade(score, passed, total, lang, detected, held, detail,
          task_grades: list[TaskGrade] | None = None) -> OracleGrade:
    return OracleGrade(
        score=score, passed=passed, total=total, language_manifest=lang,
        language_detected=detected, language_match=language_match(lang, detected),
        held_out_ok=held, detail=detail, task_grades=task_grades or [])


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
        task_grades: list[TaskGrade] = []
        try:
            suite = load_task_suite(inp.case_id)
            if suite is not None:
                testcase_results = grade_testcases_from_junit(xml_text)
                # pytest's `file` attribute is relative to its invocation
                # cwd (wt) and OS-native-separated, e.g. "oracle\test_x.py"
                # on Windows -- normalize to the bare, forward-slash,
                # oracle-dir-relative form (e.g. "test_x.py") so it matches
                # a case author's tasks.yaml oracle_tests node ids, which
                # are written relative to the oracle/ dir itself.
                testcase_results = {
                    k.replace("\\", "/").removeprefix("oracle/"): v
                    for k, v in testcase_results.items()
                }
                judge_scores: dict[str, float] = {}
                needs_diff = any(t.rubric for t in suite.tasks)
                full_diff = ""
                if needs_diff:
                    diff_res = _git(
                        ["diff", f"{inp.base_branch}...HEAD"], wt)
                    full_diff = _truncate_diff(diff_res.stdout)
                for t in suite.tasks:
                    if t.rubric:
                        # heartbeat before each blocking, synchronous judge
                        # call -- a case with many rubric tasks is a long
                        # un-heartbeated stretch inside a 20-min, 1-attempt
                        # activity otherwise, and a timeout would lose the
                        # whole cell's oracle grade, not just task grades.
                        _safe_heartbeat()
                        qs = _judge_sync(JudgeInput(
                            artifact_json=full_diff, rubric=t.rubric,
                            author_model=inp.author_model,
                            judge_model=inp.judge_model))
                        if qs.score is not None:
                            judge_scores[t.id] = qs.score
                task_grades = grade_tasks(suite, testcase_results, judge_scores)
        except Exception:
            # a broken tasks.yaml or judge call never fails the case-level
            # oracle grade -- it just contributes no task grades.
            task_grades = []
        return _grade(score, passed, total, lang, detected, held, detail,
                     task_grades=task_grades)
    except Exception as e:  # fail-safe: a broken grader never fails a cell
        return _grade(None, 0, 0, lang, None, True, f"grade_oracle error: {e}")
    finally:
        _git(["worktree", "remove", "--force", wt], inp.repo_url)
        shutil.rmtree(parent, ignore_errors=True)
