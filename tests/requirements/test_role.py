# tests/requirements/test_role.py
"""FR-113 Task 3: the product (requirements) drafter is an OPTIONAL, KNOWN
registry role -- a proposer whose own capabilities (read-only FileSystem +
RepoContext) append AFTER the loader-supplied ones (003 contract)."""

from dataclasses import dataclass

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.settings import ModelSettings
from pydantic_ai_harness import FileSystem, RepoContext

from agents.product.agent import build
from sdlc.agents import loader, roles
from sdlc.stages.requirements.deps import RequirementsDeps
from sdlc.stages.requirements.models import DraftOutput


@dataclass
class _Marker(AbstractCapability):
    """A stand-in for the loader-supplied capability prefix (durability,
    resolver, guard). Its POSITION in the built agent's flattened capability
    list is the 003 contract under test: loader caps stay first, the role's
    own append after."""

    description: str = "marker for the loader-supplied prefix"


def test_product_is_optional_not_required():
    assert "product" in loader.OPTIONAL_ROLES
    assert "product" not in loader.PROPOSER_ROLES
    assert "product" not in loader.REQUIRED_ROLES


def test_role_boot():
    """The shipped registry loads WITH the role present and wired to the
    requirements STAGE: kind proposer (a closed Literal), STAGE_ROLES maps
    the stage key to the role, and STAGE_MODELS/PROMPT_SHAS -- both derived
    from STAGE_ROLES ∩ REGISTRY -- carry the 'requirements' key."""
    assert "product" in loader.KNOWN_ROLES
    cfg = loader.load_registry()["product"]
    assert cfg.kind == "proposer"
    assert cfg.model is not None
    assert cfg.instructions  # agents/product/instructions.md
    assert roles.STAGE_ROLES["requirements"] == "product"
    assert "requirements" in roles.PROMPT_SHAS
    assert roles.STAGE_MODELS["requirements"] == cfg.model


def test_t_product_is_built_and_registered():
    assert roles.t_product is not None
    assert roles.t_product in roles.ALL_TEMPORAL_AGENTS
    assert roles.t_product.name == "product_agent"  # Temporal activity name


def test_capabilities_read_only():
    """build() appends its own capabilities AFTER the loader's: a read-only
    FileSystem exposing exactly the four read tools, then RepoContext pinned
    to no walk-up (home_dir None)."""
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
    Task 2), so the agent proposes DraftOutput over RequirementsDeps and
    retries malformed output 3 times (planner/research/constitution
    precedent)."""
    agent = build("test", "charter", ModelSettings())
    assert agent._output_type is DraftOutput
    assert agent._deps_type is RequirementsDeps
    assert agent._max_output_retries == 3
