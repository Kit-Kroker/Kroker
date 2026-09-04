"""Pure FR-106 enforcement: the workflow, not the LLM, decides traceability."""

from sdlc.stages.analyze.models import (
    AnalysisReport,
    CriterionTrace,
)
from sdlc.workflows.feature import untraced_criteria


def test_full_mapping_leaves_nothing_untraced():
    auth = [("t1", "GET /hello returns 200"), ("t1", "returns json")]
    report = AnalysisReport(
        traceability=[
            CriterionTrace(
                task_id="t1", criterion="GET /hello returns 200", tests=["test_hello_200"]
            ),
            CriterionTrace(task_id="t1", criterion="returns json", tests=["test_hello_json"]),
        ]
    )
    assert untraced_criteria(auth, report) == []


def test_criterion_mapped_to_zero_tests_is_untraced():
    auth = [("t1", "c1")]
    report = AnalysisReport(traceability=[CriterionTrace(task_id="t1", criterion="c1", tests=[])])
    assert untraced_criteria(auth, report) == ["t1: c1"]


def test_omitted_criterion_is_untraced_even_if_report_looks_clean():
    # Analyst "forgets" c2 entirely — enforcement must still flag it.
    auth = [("t1", "c1"), ("t1", "c2")]
    report = AnalysisReport(
        traceability=[CriterionTrace(task_id="t1", criterion="c1", tests=["test_c1"])]
    )
    assert untraced_criteria(auth, report) == ["t1: c2"]


def test_mapping_for_wrong_task_does_not_count():
    auth = [("t2", "c1")]
    report = AnalysisReport(
        traceability=[CriterionTrace(task_id="t1", criterion="c1", tests=["test_c1"])]
    )
    assert untraced_criteria(auth, report) == ["t2: c1"]
