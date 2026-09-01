# tests/test_assessment_worker_registration.py
"""P2-D1: an activity the workflow calls but the worker never registered.

The e2e tests build their own `acts` lists, so a missing production
registration is invisible to them: the workflow degrades through
run_or_degrade and reports not_collected on every deployed run while the
suite stays green. This test compares the two lists directly.
"""

from __future__ import annotations

import inspect
import re


def _registered_activity_names() -> set[str]:
    from sdlc import worker

    src = inspect.getsource(worker)
    m = re.search(r"activities=\[(.*?)^\s*\],", src, re.S | re.M)
    assert m, "could not find the activities=[...] literal in worker.py"
    return set(re.findall(r"\w+", m.group(1)))


def _called_activity_names() -> set[str]:
    from sdlc.workflows import assessment

    src = inspect.getsource(assessment)
    return set(re.findall(r"execute_activity\(\s*(\w+)", src)) | set(
        re.findall(r"run_or_degrade\(\s*(\w+)", src)
    )


def test_the_workflow_calls_at_least_the_activities_we_know_about():
    """A guard on the guard: if the regexes stop matching, the real check
    below would pass vacuously."""
    called = _called_activity_names()
    assert {"discover_context", "assess_risk"} <= called


def test_every_activity_the_assessment_workflow_calls_is_registered():
    missing = sorted(_called_activity_names() - _registered_activity_names())
    assert not missing, (
        f"{missing} are called by AssessmentWorkflow but absent from "
        f"worker.py's activities list -- on a real worker each would fail "
        f"to start and degrade to its fallback"
    )
