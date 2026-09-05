"""The QA report is judged against a rubric in its OWN record, leaving the
deterministic stage="code" record's contract score untouched."""

import inspect
import pathlib
import re

import pytest

from sdlc.workflows import feature

CODE_STEP_PY = pathlib.Path("src/sdlc/stages/code/step.py")


def _src() -> str:
    src = inspect.getsource(feature.FeatureWorkflow._dev_task)
    if CODE_STEP_PY.exists():
        src += "\n" + CODE_STEP_PY.read_text(encoding="utf-8")
    return src


def test_qa_report_is_judged():
    src = _src()
    assert '"qa"' in src
    assert "qa.model_dump_json()" in src
    assert 'stage="qa"' in src


def test_code_record_keeps_its_deterministic_contract_score():
    """Finding 4: the qa record is ADDITIVE. If the code record stopped
    carrying judge="contract", an LLM opinion has replaced a deterministic
    signal -- the exact regression this task must not cause."""
    src = _src()
    # Anchor on the code-stage BenchmarkRecord specifically (role=task.role),
    # not the E-32 FIX_ATTEMPT emit which also carries stage="code".
    m = re.search(r'stage="code",\s*role=task\.role', src)
    assert m
    block = src[m.start() : m.start() + 400]
    assert 'judge="contract"' in block


def test_qa_record_is_separate_from_the_code_record():
    src = _src()
    assert (src.count("self._record(") + src.count("ctx.record(")) >= 2


@pytest.mark.clause("QA-1.3")
def test_pass_gate_uses_qa_raw_not_the_llm_qa_report():
    """The label judge="contract" is a lie unless the boolean it's attached
    to is actually ground truth: qa_raw.tests_passed comes straight from the
    test-runner subprocess's exit code, while `qa.tests_passed` is the LLM
    QA agent's OWN retyped guess at the same fact and can disagree with it
    (observed live: bench-cat-cafe-monitoring run 1785148730, task T08 was
    recorded PASS by the LLM's self-report while its own worktree collected
    zero tests). `task_passed` -- the value threaded into the code record,
    the qa record, and the actual retry/completion decision -- must be
    derived from qa_raw.tests_passed, never qa.tests_passed."""
    src = _src()
    def_idx = src.index("task_passed = ")
    definition = src[def_idx : src.index("\n", def_idx)]
    assert "qa_raw.tests_passed" in definition
    assert "qa.tests_passed" not in definition
    # every use of the gate elsewhere in the method must be the shared
    # variable, not a re-derived (and rebindable) qa.tests_passed check --
    # scan code lines only, so this doesn't false-positive on the comment
    # directly above `task_passed`'s own definition that names the field
    # it's deliberately avoiding.
    code_lines = [ln for ln in src.splitlines() if not ln.strip().startswith("#")]
    assert "qa.tests_passed" not in "\n".join(code_lines)
