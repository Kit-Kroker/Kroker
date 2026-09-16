"""Chaos + edge-case characterization for the E-74 Task 9 payload models.

RED until the task lands: ``NodeFailure`` / ``BuildResult`` / ``AnalyzeResult``
/ ``PullRequest`` do not exist yet (per-test ImportError keeps the file
collectable), and ``NodeTypeSpec`` rejects ``budget_after`` as an unknown
field (extra_forbidden) while the default-value probe hits an AttributeError.

Pins the edge behaviour the task specifies:
- NodeFailure: the three required fields, every one of them enforced
  (extras follow the core-envelope convention, like GateDecision: no
  extra='forbid' anywhere in core/models.py, so none is tested here)
- BuildResult: an empty task_results list is legal, instances keep identity
  and order, non-TaskResult junk is rejected
- AnalyzeResult: the get_task_diff dict shape round-trips, empty
  collections are legal, a missing report and a non-dict diff are rejected
- PullRequest: the url is a plain str (the merge node may emit a benchmark
  skip string), non-strings rejected
- NodeTypeSpec.budget_after: defaults to "none", accepts exactly
  none/continuing/exiting, rejects any other literal
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.graph.node_types import NodePort, NodeTypeSpec
from sdlc.stages.analyze.models import AnalysisReport
from sdlc.workflows.models import TaskResult


def _report(**kw) -> AnalysisReport:
    base = {"traceability": [], "summary": "s", "confidence": 0.5}
    return AnalysisReport(**{**base, **kw})


def _task_result(**kw) -> TaskResult:
    base = {"task_id": "t1", "status": "done", "attempts": 1, "branch": "b"}
    return TaskResult(**{**base, **kw})


def _spec(**kw) -> NodeTypeSpec:
    base = {
        "type": "chaos.stage",
        "kind": "stage",
        "role": None,
        "canonical_stage": None,
        "ports": (NodePort(name="o", direction="out", payload=None),),
    }
    return NodeTypeSpec(**{**base, **kw})


# ---- NodeFailure (sdlc.core.models) -----------------------------------------


def test_node_failure_required_fields_roundtrip():
    from sdlc.core.models import NodeFailure

    failure = NodeFailure(activation_id="code#1", error_type="ApplicationError", message="boom")
    assert (failure.activation_id, failure.error_type, failure.message) == (
        "code#1",
        "ApplicationError",
        "boom",
    )


@pytest.mark.parametrize("missing", ["activation_id", "error_type", "message"])
def test_node_failure_requires_every_field(missing):
    from sdlc.core.models import NodeFailure

    fields = {"activation_id": "a#1", "error_type": "ApplicationError", "message": "boom"}
    del fields[missing]

    with pytest.raises(ValidationError, match=missing):
        NodeFailure(**fields)


# ---- BuildResult (sdlc.workflows.models) ------------------------------------


def test_build_result_allows_empty_task_results():
    from sdlc.workflows.models import BuildResult

    assert BuildResult(task_results=[]).task_results == []


def test_build_result_keeps_task_result_identity_and_order():
    from sdlc.workflows.models import BuildResult

    first = _task_result(task_id="t1")
    second = _task_result(task_id="t2", status="failed", attempts=2)

    result = BuildResult(task_results=[first, second])

    assert result.task_results == [first, second]
    assert result.task_results[0] is first


def test_build_result_rejects_non_task_result_items():
    from sdlc.workflows.models import BuildResult

    with pytest.raises(ValidationError):
        BuildResult(task_results=[42])


# ---- AnalyzeResult (sdlc.workflows.models) ----------------------------------


def test_analyze_result_accepts_the_get_task_diff_shape():
    from sdlc.workflows.models import AnalyzeResult

    diff = {"stat": " a | 1 +", "patch": "diff", "files": ["a.py"], "renames": [["b.py", "c.py"]]}

    result = AnalyzeResult(report=_report(), untraced=["x.py"], integration_diff=diff)

    assert result.integration_diff["renames"] == [["b.py", "c.py"]]
    assert result.untraced == ["x.py"]


def test_analyze_result_allows_empty_collections():
    from sdlc.workflows.models import AnalyzeResult

    result = AnalyzeResult(report=_report(), untraced=[], integration_diff={})

    assert (result.untraced, result.integration_diff) == ([], {})


def test_analyze_result_requires_the_report():
    from sdlc.workflows.models import AnalyzeResult

    with pytest.raises(ValidationError, match="report"):
        AnalyzeResult(untraced=[], integration_diff={})


def test_analyze_result_rejects_a_non_dict_diff():
    from sdlc.workflows.models import AnalyzeResult

    with pytest.raises(ValidationError, match="integration_diff"):
        AnalyzeResult(report=_report(), untraced=[], integration_diff=["not-a-dict"])


# ---- PullRequest (sdlc.workflows.models) ------------------------------------


def test_pull_request_keeps_the_url_string():
    from sdlc.workflows.models import PullRequest

    # the url may also be a benchmark skip string: it stays an unconstrained str
    assert PullRequest(url="https://example.test/pr/1").url.endswith("/pr/1")
    assert PullRequest(url="skipped: nothing to merge").url.startswith("skipped")


def test_pull_request_rejects_non_string_urls():
    from sdlc.workflows.models import PullRequest

    with pytest.raises(ValidationError, match="url"):
        PullRequest(url=42)


# ---- NodeTypeSpec.budget_after (sdlc.graph.node_types) -----------------------


def test_budget_after_defaults_to_none():
    assert _spec().budget_after == "none"


@pytest.mark.parametrize("value", ["none", "continuing", "exiting"])
def test_budget_after_accepts_the_three_literals(value):
    assert _spec(budget_after=value).budget_after == value


def test_budget_after_rejects_invalid_literals():
    with pytest.raises(ValidationError, match="Input should be 'none', 'continuing' or 'exiting'"):
        _spec(budget_after="always")
