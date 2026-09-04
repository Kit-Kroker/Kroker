import inspect
import pathlib
from unittest.mock import patch

import pytest

from sdlc.context.models import RepoObservation
from sdlc.core.models import IdeaBrief, PipelineConfig, ProjectMode
from sdlc.observability.trace import RunEventKind
from sdlc.stages import intake


@pytest.mark.clause("INTAKE-1.5")
def test_slice_exports_step_and_activities():
    assert callable(intake.step)
    assert isinstance(intake.ACTIVITIES, list)
    assert len(intake.ACTIVITIES) == 0


@pytest.mark.clause("INTAKE-1.1")
def test_intake_step_signature_and_no_workflow_dependencies():
    params = inspect.signature(intake.step).parameters
    param_names = list(params)
    assert param_names[0] == "ctx"
    assert "cfg" in param_names
    assert "idea" in param_names

    src = pathlib.Path("src/sdlc/stages/intake/step.py").read_text(encoding="utf-8")
    assert "agents.roles" not in src
    assert "@workflow.signal" not in src
    assert "@workflow.query" not in src
    assert "@workflow.defn" not in src


@pytest.mark.clause("INTAKE-1.2")
@pytest.mark.asyncio
async def test_intake_step_probes_and_passes_greenfield():
    class _StubCtx:
        def __init__(self) -> None:
            self.staged: str | None = None
            self.emitted: list[tuple] = []

        def stage(self, name: str, trace: str | None = None) -> None:
            self.staged = name

        def emit(self, kind: RunEventKind, **kwargs) -> None:
            self.emitted.append((kind, kwargs))

    ctx = _StubCtx()
    cfg = PipelineConfig()
    idea = IdeaBrief(
        title="New app",
        description="Build something new",
        mode=ProjectMode.GREENFIELD,
        repo_url="/repo/test",
    )

    with patch("temporalio.workflow.execute_activity") as mock_exec:
        mock_exec.return_value = RepoObservation(
            is_git_repo=True,
            base_branch_resolves=True,
            commit_sha="abcdef123456",
            source_file_count=0,
        )
        res = await intake.step(ctx, cfg=cfg, idea=idea)

    assert res is None
    assert ctx.staged == "intake"
    assert len(ctx.emitted) == 0


@pytest.mark.clause("INTAKE-1.3")
@pytest.mark.asyncio
async def test_intake_step_fails_closed_on_invalid_repo():
    class _StubCtx:
        def __init__(self) -> None:
            self.staged: str | None = None
            self.emitted: list[tuple] = []

        def stage(self, name: str, trace: str | None = None) -> None:
            self.staged = name

        def emit(self, kind: RunEventKind, **kwargs) -> None:
            self.emitted.append((kind, kwargs))

    ctx = _StubCtx()
    cfg = PipelineConfig()
    idea = IdeaBrief(
        title="Brownfield mod",
        description="Fix bug",
        mode=ProjectMode.BROWNFIELD,
        repo_url="/invalid/repo",
    )

    with patch("temporalio.workflow.execute_activity") as mock_exec:
        mock_exec.return_value = RepoObservation(
            is_git_repo=False,
            base_branch_resolves=False,
            reason="not a git repository",
        )
        res = await intake.step(ctx, cfg=cfg, idea=idea)

    assert res is not None
    assert res.startswith("rejected:intake")
    assert "not a git repository" in res


@pytest.mark.clause("INTAKE-1.4")
@pytest.mark.asyncio
async def test_intake_step_emits_warning():
    class _StubCtx:
        def __init__(self) -> None:
            self.staged: str | None = None
            self.emitted: list[tuple] = []

        def stage(self, name: str, trace: str | None = None) -> None:
            self.staged = name

        def emit(self, kind: RunEventKind, **kwargs) -> None:
            self.emitted.append((kind, kwargs))

    ctx = _StubCtx()
    cfg = PipelineConfig()
    idea = IdeaBrief(
        title="App",
        description="Greenfield with existing files",
        mode=ProjectMode.GREENFIELD,
        repo_url="/repo/with-files",
    )

    with patch("temporalio.workflow.execute_activity") as mock_exec:
        mock_exec.return_value = RepoObservation(
            is_git_repo=True,
            base_branch_resolves=True,
            commit_sha="abcdef123456",
            source_file_count=10,
        )
        res = await intake.step(ctx, cfg=cfg, idea=idea)

    assert res is None
    assert any(
        kind == RunEventKind.STAGE_ENDED and "warning" in kwargs for kind, kwargs in ctx.emitted
    )
