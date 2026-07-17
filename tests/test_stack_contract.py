from sdlc.agents.roles import _STAGE_PROMPTS
from sdlc.models import QAReport, ValidationContract
from sdlc.workflows.feature import (
    DEFAULT_LINT_CMD, DEFAULT_TEST_CMD, _contract_shell_cmd,
    _contract_stack_directive, _should_resume_session,
)

PLAN_PROMPT = _STAGE_PROMPTS["plan"]
QA_PROMPT = _STAGE_PROMPTS["qa"]


def test_plan_prompt_requires_stack_on_contract():
    assert "stack" in PLAN_PROMPT.lower()


def test_qa_prompt_requires_stack_mismatch_judgment():
    assert "stack_mismatch" in QA_PROMPT


def test_validation_contract_has_stack_field_defaulting_empty():
    c = ValidationContract(task_id="t1", assertions=["a"])
    assert c.stack == ""


def test_qa_report_has_stack_mismatch_field_defaulting_false():
    assert QAReport(tests_passed=True).stack_mismatch is False


def test_stack_directive_empty_when_no_contract():
    assert _contract_stack_directive(None) == ""


def test_stack_directive_empty_when_contract_has_no_stack():
    c = ValidationContract(task_id="t1", assertions=["a"], stack="")
    assert _contract_stack_directive(c) == ""


def test_stack_directive_surfaces_stack_as_mandatory():
    c = ValidationContract(task_id="t1", assertions=["a"],
                           stack="TypeScript/Node.js monorepo, npm workspaces")
    directive = _contract_stack_directive(c)
    assert "MANDATORY STACK" in directive
    assert "TypeScript/Node.js monorepo, npm workspaces" in directive


def test_resumes_when_stack_ok_and_under_budget():
    qa = QAReport(tests_passed=False, stack_mismatch=False)
    assert _should_resume_session(qa, resumes=0, max_resumes=3,
                                  near_ceiling=False) is True


def test_no_resume_when_over_budget():
    qa = QAReport(tests_passed=False, stack_mismatch=False)
    assert _should_resume_session(qa, resumes=3, max_resumes=3,
                                  near_ceiling=False) is False


def test_no_resume_when_near_context_ceiling():
    qa = QAReport(tests_passed=False, stack_mismatch=False)
    assert _should_resume_session(qa, resumes=0, max_resumes=3,
                                  near_ceiling=True) is False


def test_plan_prompt_requires_lint_commands_and_self_contained_install():
    assert "lint_commands" in PLAN_PROMPT
    assert "npm install" in PLAN_PROMPT


def test_validation_contract_has_lint_commands_field_defaulting_empty():
    c = ValidationContract(task_id="t1", assertions=["a"])
    assert c.lint_commands == []


def test_contract_shell_cmd_uses_contract_commands_when_present():
    cmd = _contract_shell_cmd(["npm install", "npm test"], DEFAULT_TEST_CMD)
    assert cmd == "npm install && npm test"


def test_contract_shell_cmd_falls_back_to_default_when_empty():
    assert _contract_shell_cmd([], DEFAULT_TEST_CMD) == DEFAULT_TEST_CMD
    assert _contract_shell_cmd(None, DEFAULT_LINT_CMD) == DEFAULT_LINT_CMD


def test_no_resume_on_stack_mismatch_even_under_budget():
    """A session that already committed to the wrong stack is a worse
    starting point than a fresh one — never resume it, regardless of
    remaining resume budget or context headroom."""
    qa = QAReport(tests_passed=False, stack_mismatch=True)
    assert _should_resume_session(qa, resumes=0, max_resumes=3,
                                  near_ceiling=False) is False
