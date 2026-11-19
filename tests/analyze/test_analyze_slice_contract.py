import inspect
import pathlib
from unittest.mock import MagicMock

import pytest

from sdlc.core.models import PipelineConfig
from sdlc.memory.models import MemoryKind
from sdlc.stages import analyze
from sdlc.stages.analyze.models import AnalysisReport, CriterionTrace
from sdlc.stages.plan.models import DevTask
from sdlc.vcs.git import DiffInput
from sdlc.vcs.models import CodeArtifact


@pytest.mark.clause("ANALYZE-1.5")
def test_slice_exports_step_and_activities():
    assert callable(analyze.step)
    assert isinstance(analyze.ACTIVITIES, list)
    assert len(analyze.ACTIVITIES) == 1
    assert analyze.ACTIVITIES == [analyze.build_trace_inventory]


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
    diff = CodeArtifact(stat="file.py | 2 +-")

    res = await analyze.step(
        ctx,
        cfg=cfg,
        tasks=[task],
        diff=diff,
        patch="--- a\n+++ b",
        integration_wt="/fake/wt",
        analyst_agent=MagicMock(),
    )

    assert ctx.role_called is True
    assert isinstance(res, analyze.AnalyzeOutcome)
    assert res.report.summary == "all traced"
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
    diff = CodeArtifact(stat="file.py | 2 +-")

    await analyze.step(
        ctx,
        cfg=cfg,
        tasks=[task],
        diff=diff,
        patch="--- a\n+++ b",
        integration_wt="/fake/wt",
        analyst_agent=MagicMock(),
    )

    # GOTCHA must be retained when criteria are untraced
    gotchas = [text for kind, _, text, _ in ctx.retained if kind == MemoryKind.GOTCHA]
    assert len(gotchas) == 1
    assert "t1: criterion-1" in gotchas[0]


@pytest.mark.asyncio
async def test_analyze_step_self_fetch_uses_integration_label_and_load_diff(monkeypatch):
    """FR-702: with no ``diff=`` the fallback self-fetches ONCE under the
    ``integration`` label and materializes the patch text through ONE
    load_diff read-back — the patch never rides the artifact inline."""
    import importlib

    from sdlc.artifacts.read import LoadDiffInput, LoadSessionResult
    from sdlc.core.models import ArtifactRef

    step_mod = importlib.import_module("sdlc.stages.analyze.step")
    seen: dict = {}
    ref = ArtifactRef(kind="diff", uri="file:///store/diffs/integration.patch", sha256="0" * 64)

    async def fake_get_task_diff(inp: DiffInput) -> CodeArtifact:
        seen["diff_input"] = inp
        return CodeArtifact(files=["a.py"], stat="a.py | 1 +", patch_ref=ref)

    async def fake_load_diff(inp: LoadDiffInput) -> LoadSessionResult:
        seen["load_input"] = inp
        return LoadSessionResult(text="++dry patch++", truncated=False)

    monkeypatch.setattr(step_mod, "get_task_diff", fake_get_task_diff)
    monkeypatch.setattr(step_mod, "load_diff", fake_load_diff)

    class _PromptCtx:
        def stage(self, *a, **k):
            pass

        async def run_role(self, cfg, role, model, agent, prompt, into=None):
            seen["prompt"] = prompt
            return MagicMock(
                output=AnalysisReport(
                    traceability=[
                        CriterionTrace(task_id="t1", criterion="criterion-1", tests=["test_c1"])
                    ],
                    summary="all traced",
                )
            )

        async def record(self, cfg, record) -> None:
            pass

        async def retain(self, *a, **k):
            pass

    await step_mod.step(
        _PromptCtx(),
        cfg=PipelineConfig(),
        tasks=[
            DevTask(
                id="t1",
                title="Task 1",
                description="Task description",
                acceptance_criteria=["criterion-1"],
            )
        ],
        integration_wt="/fake/wt",
        base_branch="main",
        analyst_agent=MagicMock(),
    )

    # one fetch, labeled for the integration diff, against the base branch
    assert seen["diff_input"].label == "integration"
    assert seen["diff_input"].worktree == "/fake/wt"
    assert seen["diff_input"].branch_point == "main"
    # one read-back of the stored patch, and both land in the prompt
    assert seen["load_input"].ref is ref
    assert "a.py | 1 +" in seen["prompt"]
    assert "++dry patch++" in seen["prompt"]


@pytest.mark.asyncio
async def test_analyze_step_without_worktree_skips_the_self_fetch(monkeypatch):
    """No worktree -> no self-fetch: the diff stays absent and the prompt
    carries an empty stat/patch rather than a doomed activity call."""
    import importlib

    step_mod = importlib.import_module("sdlc.stages.analyze.step")

    async def boom(inp):
        raise AssertionError("no worktree: get_task_diff must not be scheduled")

    monkeypatch.setattr(step_mod, "get_task_diff", boom)

    class _PromptCtx:
        def stage(self, *a, **k):
            pass

        async def run_role(self, cfg, role, model, agent, prompt, into=None):
            return MagicMock(output=AnalysisReport(traceability=[], summary="nothing traced"))

        async def record(self, cfg, record) -> None:
            pass

        async def retain(self, *a, **k):
            pass

    await step_mod.step(
        _PromptCtx(),
        cfg=PipelineConfig(),
        tasks=[
            DevTask(
                id="t1",
                title="Task 1",
                description="Task description",
                acceptance_criteria=["criterion-1"],
            )
        ],
        integration_wt="",
        analyst_agent=MagicMock(),
    )
