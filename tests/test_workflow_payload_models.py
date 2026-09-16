"""E-74 §4.4: graph payload models accept the real activity output shapes."""

from __future__ import annotations

from sdlc.core.models import NodeFailure
from sdlc.stages.analyze.models import AnalysisReport
from sdlc.workflows.models import AnalyzeResult, BuildResult, PullRequest, TaskResult


def test_analyze_result_accepts_get_task_diff_shape():
    diff = {"stat": " a | 1 +", "patch": "diff", "files": ["a.py"], "renames": [["b.py", "c.py"]]}
    r = AnalyzeResult(
        report=AnalysisReport(traceability=[], summary="s", confidence=0.5),
        untraced=[],
        integration_diff=diff,
    )
    assert r.integration_diff["renames"] == [["b.py", "c.py"]]


def test_build_result_keeps_task_result_instances():
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b")
    assert BuildResult(task_results=[tr]).task_results[0] is tr


def test_node_failure_and_pull_request_shapes():
    assert (
        NodeFailure(activation_id="a#1", error_type="ApplicationError", message="boom").message
        == "boom"
    )
    assert PullRequest(url="https://example.test/pr/1").url.endswith("/1")
