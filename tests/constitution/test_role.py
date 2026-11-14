# tests/constitution/test_role.py
"""FR-112 Task 5: the constitution drafter is an OPTIONAL, KNOWN registry
role -- a proposer whose own capabilities (read-only FileSystem + RepoContext)
append AFTER the loader-supplied ones (003 contract)."""

from dataclasses import dataclass

import pytest
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.settings import ModelSettings
from pydantic_ai_harness import FileSystem, RepoContext

from agents.constitution.agent import build
from sdlc.agents import loader, roles
from sdlc.stages.constitution.deps import ConstitutionDeps
from sdlc.stages.constitution.models import DraftOutput
from sdlc.stages.constitution.stage import DraftInput
from sdlc.stages.constitution.stage import _draft_constitution_impl as draft_constitution


@dataclass
class _Marker(AbstractCapability):
    """A stand-in for the loader-supplied capability prefix (durability,
    resolver, guard). Its POSITION in the built agent's flattened capability
    list is the 003 contract under test: loader caps stay first, the role's
    own append after."""

    description: str = "marker for the loader-supplied prefix"


def test_constitution_is_optional_not_required():
    assert "constitution" in loader.OPTIONAL_ROLES
    assert "constitution" not in loader.PROPOSER_ROLES
    assert "constitution" not in loader.REQUIRED_ROLES


def test_constitution_is_a_known_directory():
    """KNOWN_ROLES gates RECOGNITION: the unknown-directory check must keep
    biting on agents/constitution/."""
    assert "constitution" in loader.KNOWN_ROLES


def test_optional_role_boot():
    """The shipped registry loads WITH the role present, kind=proposer (kind
    is a closed Literal), and a prompt + model resolved from its folder."""
    cfg = loader.load_registry()["constitution"]
    assert cfg.kind == "proposer"
    assert cfg.model is not None
    assert cfg.instructions  # agents/constitution/instructions.md


def test_t_constitution_is_built_and_registered():
    assert roles.t_constitution is not None
    assert roles.t_constitution in roles.ALL_TEMPORAL_AGENTS
    assert roles.t_constitution.name == "constitution_agent"  # Temporal activity name


def test_read_only_and_secret_denial():
    """build() appends its own capabilities AFTER the loader's: a read-only
    FileSystem exposing exactly the four read tools, then RepoContext at
    defaults (home_dir None -- no walk-up past the workspace)."""
    agent = build("test", "charter", ModelSettings(), capabilities=[_Marker()])
    caps = list(agent._root_capability.capabilities)
    kinds = [type(c).__name__ for c in caps]
    marker = kinds.index("_Marker")
    fs = kinds.index("FileSystem")
    rc = kinds.index("RepoContext")
    assert marker < fs < rc, f"loader caps must stay first, got {kinds}"

    filesystem = caps[fs]
    assert isinstance(filesystem, FileSystem)
    assert filesystem.read_only is True
    assert list(filesystem.tools) == ["read_file", "search_files", "find_files", "list_directory"]

    repo_context = caps[rc]
    assert isinstance(repo_context, RepoContext)
    assert repo_context.home_dir is None  # no walk-up past the workspace


def test_output_is_the_draft_not_the_frozen_artifact():
    """Controller ruling: ids/digest are code-assigned downstream (freeze,
    Task 2), so the agent proposes DraftOutput over ConstitutionDeps
    (planner/research precedent). FR-202: construction stays at the runtime
    default -- the registry is the one source of the retry budget."""
    agent = build("test", "charter", ModelSettings())
    assert agent._output_type is DraftOutput
    assert agent._deps_type is ConstitutionDeps
    assert agent._max_output_retries == 1


def test_output_retry_budget_lives_in_the_registry():
    """FR-202: agents/constitution/agent.yaml carries `validation_retries: 3`
    (planner/research precedent), so the roles registry reads 3 for the role
    and the run site forwards `retries={"output": 3}`."""
    assert roles.OUTPUT_RETRIES["constitution"] == 3


class _RecordingAgent:
    """Stands in for the registry agent at the impl's `_agent` seam (the
    test_stage.py `_Recorder` shape): records the kwargs run() received."""

    def __init__(self) -> None:
        self.kwargs: dict = {}

    async def run(self, prompt, **kw):
        self.kwargs = dict(kw)

        class _Result:
            output = DraftOutput()

        return _Result()


@pytest.fixture
def _runs_root(monkeypatch, tmp_path):
    """The greenfield scratch dir resolves under $SDLC_RUNS_ROOT -- keep the
    scratch out of the checkout (the research suite's convention)."""
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))


@pytest.mark.asyncio
async def test_run_site_forwards_the_registry_output_retries(_runs_root):
    """FR-202: the drafter's run site forwards the registry budget per call
    as `retries={"output": 3}` -- the `_agent` seam records it."""
    inp = DraftInput(
        idea_json='{"goal": "ship the constitution stage"}',
        repo_path=None,
        deps=ConstitutionDeps(run_id="r1", mode="greenfield"),
        model="test-model",
    )
    rec = _RecordingAgent()
    await draft_constitution(inp, _agent=rec)
    assert (rec.kwargs or {}).get("retries") == {"output": 3}
