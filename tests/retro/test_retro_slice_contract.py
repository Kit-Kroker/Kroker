import inspect
import pathlib
from unittest.mock import patch

import pytest

from sdlc.core.models import ArtifactRef, MemoryConfig, PipelineConfig, RunSummary
from sdlc.memory.models import MemoryKind
from sdlc.observability.summary import build_run_summary
from sdlc.observability.trace import RunEvent, RunEventKind
from sdlc.stages import retro


@pytest.mark.clause("RETRO-1.5")
def test_slice_exports_step_and_activities():
    assert callable(retro.step)
    assert isinstance(retro.ACTIVITIES, list)
    assert len(retro.ACTIVITIES) == 0


@pytest.mark.clause("RETRO-1.1")
def test_retro_step_signature_and_no_workflow_dependencies():
    params = inspect.signature(retro.step).parameters
    param_names = list(params)
    assert param_names[0] == "ctx"
    for expected in ("cfg", "summary", "session_refs", "trace"):
        assert expected in param_names, f"missing expected param {expected}"

    src = pathlib.Path("src/sdlc/stages/retro/step.py").read_text(encoding="utf-8")
    assert "agents.roles" not in src
    assert "@workflow.signal" not in src
    assert "@workflow.query" not in src
    assert "@workflow.defn" not in src


def _make_summary(
    run_id: str = "run-1", outcome: str = "deployed:v1", memory_enabled: bool = True
) -> RunSummary:
    ev = RunEvent(seq=1, kind=RunEventKind.STAGE_STARTED, at="2026-09-04T12:00:00Z", stage="intake")
    return build_run_summary(
        run_id=run_id,
        mode="greenfield",
        outcome=outcome,
        trace=[ev],
        memory_enabled=memory_enabled,
        memory_watermark="wm-1" if memory_enabled else None,
    )


@pytest.mark.clause("RETRO-1.2")
@pytest.mark.asyncio
async def test_retro_step_emits_run_finished_and_retains_summary():
    class _StubCtx:
        def __init__(self) -> None:
            self.emitted: list[tuple] = []
            self.retained: list[tuple] = []

        def emit(self, kind: RunEventKind, **kwargs) -> None:
            self.emitted.append((kind, kwargs))

        async def retain(self, cfg, kind, bank, text, metadata) -> None:
            self.retained.append((kind, bank, text, metadata))

    ctx = _StubCtx()
    cfg = PipelineConfig(memory=MemoryConfig(enabled=True, project_bank="bank-test"))
    summary = _make_summary("run-1", "deployed:v1", memory_enabled=True)
    session_refs: list[ArtifactRef] = []
    trace: list[RunEvent] = [
        RunEvent(seq=1, kind=RunEventKind.STAGE_STARTED, at="2026-09-04T12:00:00Z", stage="intake")
    ]

    with patch("temporalio.workflow.execute_activity"):
        await retro.step(ctx, cfg=cfg, summary=summary, session_refs=session_refs, trace=trace)

    kinds = [kind for kind, _ in ctx.emitted]
    assert RunEventKind.RUN_FINISHED in kinds
    assert RunEventKind.MEMORY_RETAINED in kinds
    assert len(ctx.retained) == 1
    assert ctx.retained[0][0] == MemoryKind.RUN_SUMMARY
    assert ctx.retained[0][1] == "bank-test"


@pytest.mark.clause("RETRO-1.3")
@pytest.mark.asyncio
async def test_retro_step_with_memory_disabled_skips_retention():
    class _StubCtx:
        def __init__(self) -> None:
            self.emitted: list[tuple] = []
            self.retained: list[tuple] = []

        def emit(self, kind: RunEventKind, **kwargs) -> None:
            self.emitted.append((kind, kwargs))

        async def retain(self, cfg, kind, bank, text, metadata) -> None:
            self.retained.append((kind, bank, text, metadata))

    ctx = _StubCtx()
    cfg = PipelineConfig(memory=MemoryConfig(enabled=False))
    summary = _make_summary("run-2", "rejected:budget", memory_enabled=False)

    with patch("temporalio.workflow.execute_activity"):
        await retro.step(ctx, cfg=cfg, summary=summary, session_refs=[], trace=[])

    kinds = [kind for kind, _ in ctx.emitted]
    assert RunEventKind.RUN_FINISHED in kinds
    assert RunEventKind.MEMORY_RETAINED not in kinds
    assert len(ctx.retained) == 0


@pytest.mark.clause("RETRO-1.4")
@pytest.mark.asyncio
async def test_retro_step_never_raises_on_activity_failure():
    class _FailingCtx:
        def emit(self, kind: RunEventKind, **kwargs) -> None:
            raise RuntimeError("emit exploded")

        async def retain(self, *args, **kwargs) -> None:
            raise RuntimeError("retain exploded")

    ctx = _FailingCtx()
    cfg = PipelineConfig()
    summary = _make_summary("run-3", "deployed:v1", memory_enabled=False)

    # Best-effort contract: step MUST never raise
    await retro.step(ctx, cfg=cfg, summary=summary, session_refs=[], trace=[])
