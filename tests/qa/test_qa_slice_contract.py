import inspect
import pathlib
from unittest.mock import MagicMock

import pytest

from sdlc.core.models import PipelineConfig
from sdlc.stages import qa
from sdlc.stages.qa.models import QAReport


@pytest.mark.clause("QA-1.5")
def test_slice_exports_step_and_activities():
    assert callable(qa.step)
    assert {a.__temporal_activity_definition.name for a in qa.ACTIVITIES} >= {
        "run_test_suite",
        "run_lint",
        "security_scan",
    }


@pytest.mark.clause("QA-1.1")
def test_qa_never_calls_a_gate():
    # B0 cited feature.py:2026 and :2287 as qa's justification for
    # StageContext.gate. They are the coding path's tool-approval gate and the
    # loop-level task gate; qa calls neither.
    src = pathlib.Path("src/sdlc/stages/qa/step.py").read_text(encoding="utf-8")
    assert "ctx.gate" not in src


@pytest.mark.clause("QA-1.1")
def test_qa_step_is_pure_over_its_inputs():
    params = inspect.signature(qa.step).parameters
    assert list(params)[0] == "ctx"
    assert "qa_agent" in params


@pytest.mark.clause("QA-1.2")
@pytest.mark.asyncio
async def test_qa_step_clean_context_execution():
    class _StubCtx:
        def __init__(self) -> None:
            self.role_called = False

        async def run_role(self, cfg, role, model, agent, prompt, into=None):
            self.role_called = True
            assert role == "qa"
            assert "Frozen contract assertions:" in prompt
            assert "assertion-1" in prompt
            assert "Diff stat:" in prompt
            assert "Diff:" in prompt
            res = MagicMock()
            res.output = QAReport(tests_passed=True, issues=[])
            return res

    ctx = _StubCtx()
    cfg = PipelineConfig()
    task = MagicMock()
    task.role = "dev"
    task.acceptance_criteria = ["assertion-1"]
    contract = MagicMock()
    contract.assertions = ["assertion-1"]
    diff = {"stat": "file.py | 2 +-", "patch": "--- a\n+++ b"}
    qa_raw = QAReport(tests_passed=True, issues=[])

    result = await qa.step(
        ctx,
        cfg=cfg,
        task=task,
        contract=contract,
        diff=diff,
        worktree="/fake",
        qa_agent=MagicMock(),
        qa_raw=qa_raw,
    )
    assert ctx.role_called is True
    assert result.tests_passed is True
