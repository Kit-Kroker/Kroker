# tests/constitution/test_role.py
"""FR-112 Task 5: the constitution drafter is an OPTIONAL, KNOWN registry
role -- a proposer whose own capabilities (read-only FileSystem + RepoContext)
append AFTER the loader-supplied ones (003 contract)."""

from dataclasses import dataclass

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.settings import ModelSettings
from pydantic_ai_harness import FileSystem, RepoContext

from agents.constitution.agent import build
from sdlc.agents import loader, roles
from sdlc.stages.constitution.deps import ConstitutionDeps
from sdlc.stages.constitution.models import DraftOutput


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
    Task 2), so the agent proposes DraftOutput over ConstitutionDeps and
    retries malformed output 3 times (planner/research precedent)."""
    agent = build("test", "charter", ModelSettings())
    assert agent._output_type is DraftOutput
    assert agent._deps_type is ConstitutionDeps
    assert agent._max_output_retries == 3
