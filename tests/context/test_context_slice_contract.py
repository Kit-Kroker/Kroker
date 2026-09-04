"""Context stage slice contract test (spec A §3.3)."""

from __future__ import annotations

import inspect
import pathlib
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.context.models import CodebaseMap
from sdlc.core.models import IdeaBrief, PipelineConfig, ProjectMode
from sdlc.measurement import Measurement
from sdlc.stages import context
from sdlc.stages.context.activities import (
    DeltaCheckInput,
    check_brownfield_delta,
    classify_repo,
)
from sdlc.stages.context.models import BrownfieldDelta


@pytest.mark.clause("CONTEXT-1.1")
def test_slice_exports_step_and_activities():
    assert callable(context.step)
    assert callable(context.build_map)
    assert isinstance(context.ACTIVITIES, list)
    assert classify_repo in context.ACTIVITIES
    assert check_brownfield_delta in context.ACTIVITIES
    assert callable(context.prompt_digest)

    params = inspect.signature(context.step).parameters
    param_names = list(params)
    assert param_names[0] == "ctx"
    assert "cfg" in param_names
    assert "idea" in param_names
    assert "repo_path" in param_names
    assert "commit_sha" in param_names

    src = pathlib.Path("src/sdlc/stages/context/step.py").read_text(encoding="utf-8")
    assert "@workflow.defn" not in src
    assert "@workflow.signal" not in src
    assert "@workflow.query" not in src


@pytest.mark.clause("CONTEXT-1.2")
@pytest.mark.asyncio
async def test_context_greenfield_bypasses_mapping():
    class _StubCtx:
        def __init__(self) -> None:
            self.stages: list[tuple[str, ...]] = []

        def stage(self, status: str, trace: str | None = None) -> None:
            self.stages.append((status, trace))

    ctx = _StubCtx()
    cfg = PipelineConfig()
    idea = IdeaBrief(
        title="Greenfield feature",
        description="Fresh app",
        mode=ProjectMode.GREENFIELD,
        repo_url="/repo/test",
    )

    res = await context.step(
        ctx,
        cfg=cfg,
        idea=idea,
        repo_path="/repo/test",
        commit_sha="abcdef123456",
    )
    assert res is None
    assert len(ctx.stages) == 0


@pytest.mark.clause("CONTEXT-1.3")
@pytest.mark.asyncio
async def test_context_brownfield_builds_and_projects_map():
    class _StubCtx:
        def __init__(self) -> None:
            self.stages: list[tuple[str, ...]] = []

        def stage(self, status: str, trace: str | None = None) -> None:
            self.stages.append((status, trace))

    ctx = _StubCtx()
    cfg = PipelineConfig()
    idea = IdeaBrief(
        title="Brownfield feature",
        description="Modify existing app",
        mode=ProjectMode.BROWNFIELD,
        repo_url="/repo/test",
    )

    dummy_map = CodebaseMap(
        tree_hash="thash123",
        commit_sha="csha123",
        modules_collected=Measurement.measured(1.0),
        contracts_collected=Measurement.measured(1.0),
        hot_spots_collected=Measurement.measured(1.0),
        collected=Measurement.measured(1.0),
    )

    with patch("sdlc.stages.context.step.build_map", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = dummy_map
        res = await context.step(
            ctx,
            cfg=cfg,
            idea=idea,
            repo_path="/repo/test",
            commit_sha="csha123",
        )

    assert isinstance(res, CodebaseMap)
    assert res.tree_hash == "thash123"
    assert ("mapping", "context") in ctx.stages


@pytest.mark.clause("CONTEXT-1.4")
@pytest.mark.asyncio
async def test_context_fails_closed_when_unmeasured():
    class _StubCtx:
        def __init__(self) -> None:
            self.stages: list[tuple[str, ...]] = []

        def stage(self, status: str, trace: str | None = None) -> None:
            self.stages.append((status, trace))

    ctx = _StubCtx()
    cfg = PipelineConfig()
    idea = IdeaBrief(
        title="Brownfield feature",
        description="Modify existing app",
        mode=ProjectMode.BROWNFIELD,
        repo_url="/repo/test",
    )

    dummy_unmeasured_map = CodebaseMap(
        tree_hash="thash123",
        commit_sha="csha123",
        modules_collected=Measurement.not_collected("scan timed out"),
        contracts_collected=Measurement.not_collected("scan timed out"),
        hot_spots_collected=Measurement.not_collected("scan timed out"),
        collected=Measurement.not_collected("scan timed out"),
    )

    with patch("sdlc.stages.context.step.build_map", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = dummy_unmeasured_map
        res = await context.step(
            ctx,
            cfg=cfg,
            idea=idea,
            repo_path="/repo/test",
            commit_sha="csha123",
        )

    assert isinstance(res, str)
    assert res.startswith("rejected:context")
    assert "scan timed out" in res


@pytest.mark.clause("CONTEXT-1.5")
@pytest.mark.asyncio
async def test_context_activities_and_delta_verification():
    delta = BrownfieldDelta(added=["new_file.py"], modified=[], removed=[])
    inp = DeltaCheckInput(repo_dir="/nonexistent/path", commit_sha="abcdef123456", delta=delta)
    result = await check_brownfield_delta(inp)
    assert result.name == "brownfield_delta_grounded"
    assert not result.passed
