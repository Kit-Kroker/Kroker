"""The QA report is judged against a rubric in its OWN record, leaving the
deterministic stage="code" record's contract score untouched."""
import inspect

from sdlc.workflows import feature


def test_qa_report_is_judged():
    src = inspect.getsource(feature.FeatureWorkflow._dev_task)
    assert '"qa"' in src
    assert "qa.model_dump_json()" in src
    assert 'stage="qa"' in src


def test_code_record_keeps_its_deterministic_contract_score():
    """Finding 4: the qa record is ADDITIVE. If the code record stopped
    carrying judge="contract", an LLM opinion has replaced a deterministic
    signal -- the exact regression this task must not cause."""
    src = inspect.getsource(feature.FeatureWorkflow._dev_task)
    # Anchor on the code-stage BenchmarkRecord specifically (role=task.role),
    # not the E-32 FIX_ATTEMPT emit which also carries stage="code".
    start = src.index('stage="code", role=task.role')
    block = src[start:start + 400]
    assert 'judge="contract"' in block


def test_qa_record_is_separate_from_the_code_record():
    src = inspect.getsource(feature.FeatureWorkflow._dev_task)
    assert src.count("self._record(") >= 2
