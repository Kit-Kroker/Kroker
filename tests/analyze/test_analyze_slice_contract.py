import inspect
import pathlib
from unittest.mock import MagicMock

import pytest

from sdlc.core.models import PipelineConfig
from sdlc.memory.models import MemoryKind
from sdlc.stages import analyze
from sdlc.stages.analyze.models import AnalysisReport, CriterionTrace
from sdlc.stages.plan.models import DevTask


@pytest.mark.clause("ANALYZE-1.5")
def test_slice_exports_step_and_activities():
    assert callable(analyze.step)
    assert isinstance(analyze.ACTIVITIES, list)
    assert len(analyze.ACTIVITIES) == 0


@pytest.mark.clause("ANALYZE-1.1")
def test_analyze_step_signature_and_no_workflow_dependencies():
    params = inspect.signature(analyze.step).parameters
    param_names = list(params)
    assert param_names[0] == "ctx"
    assert "analyst_agent" in param_names
    assert "cfg" in param_names

    src = pathlib.Path("src/sdlc/stages/analyze/step.py").read_text(encoding="utf-8")
    assert "agents.roles" not in src
    assert "@workflow.signal" not in src
    assert "@workflow.query" not in src
    assert "@workflow.defn" not in src


@pytest.mark.clause("ANALYZE-1.2")
@pytest.mark.clause("ANALYZE-1.3")
@pytest.mark.asyncio
async def test_analyze_step_clean_context_execution():
    class _StubCtx:
        def __init__(self) -> None:
            self.role_called = False
            self.retained: list[tuple] = []
            self.records: list = []

        def stage(self, status: str, trace: str | None = None) -> None:
            pass

        async def run_role(self, cfg, role, model, agent, prompt, into=None):
            self.role_called = True
            assert role == "analyst"
            assert "Acceptance criteria" in prompt
            assert "criterion-1" in prompt
            res = MagicMock()
            res.output = AnalysisReport(
                traceability=[
                    CriterionTrace(task_id="t1", criterion="criterion-1", tests=["test_c1"])
                ],
                summary="all traced",
            )
            return res

        async def record(self, cfg, record) -> None:
            self.records.append(record)

        async def retain(self, cfg, kind, bank, text, metadata) -> None:
            self.retained.append((kind, bank, text, metadata))

    ctx = _StubCtx()
    cfg = PipelineConfig()
    task = DevTask(
        id="t1", title="Task 1", description="Task description", acceptance_criteria=["criterion-1"]
    )
    diff = {"stat": "file.py | 2 +-", "patch": "--- a\n+++ b"}

    res = await analyze.step(
        ctx,
        cfg=cfg,
        tasks=[task],
        diff=diff,
        integration_wt="/fake/wt",
        analyst_agent=MagicMock(),
    )

    assert ctx.role_called is True
    assert isinstance(res, AnalysisReport)
    assert res.summary == "all traced"
    assert len(ctx.records) == 1
    # Untraced is empty, so no GOTCHA retained
    assert not any(kind == MemoryKind.GOTCHA for kind, *_ in ctx.retained)


@pytest.mark.clause("ANALYZE-1.4")
@pytest.mark.asyncio
async def test_analyze_step_retains_gotcha_when_criteria_untraced():
    class _StubCtx:
        def __init__(self) -> None:
            self.retained: list[tuple] = []

        def stage(self, status: str, trace: str | None = None) -> None:
            pass

        async def run_role(self, cfg, role, model, agent, prompt, into=None):
            res = MagicMock()
            # Returns empty traceability, leaving criterion-1 untraced
            res.output = AnalysisReport(traceability=[], summary="untraced")
            return res

        async def record(self, cfg, record) -> None:
            pass

        async def retain(self, cfg, kind, bank, text, metadata) -> None:
            self.retained.append((kind, bank, text, metadata))

    ctx = _StubCtx()
    cfg = PipelineConfig()
    task = DevTask(
        id="t1", title="Task 1", description="Task description", acceptance_criteria=["criterion-1"]
    )
    diff = {"stat": "file.py | 2 +-", "patch": "--- a\n+++ b"}

    await analyze.step(
        ctx,
        cfg=cfg,
        tasks=[task],
        diff=diff,
        integration_wt="/fake/wt",
        analyst_agent=MagicMock(),
    )

    # GOTCHA must be retained when criteria are untraced
    gotchas = [text for kind, _, text, _ in ctx.retained if kind == MemoryKind.GOTCHA]
    assert len(gotchas) == 1
    assert "t1: criterion-1" in gotchas[0]
