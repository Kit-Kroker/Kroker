"""Held-out oracle grade (E-31): run a hidden suite against produced code
through the E-30 ToolchainAdapter, graded as fraction passing.

This module holds the pure grading logic (grade_from_junit / held_out_ok /
language_match) and the grade_oracle Temporal activity (Task 4). The pure
functions never do I/O so they unit-test without a Temporal environment or a
git repo; the activity confines all git/shell/FS work.
"""
from __future__ import annotations

import defusedxml.ElementTree as DET


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
