"""agent.py per role — eve's agent.ts, in Python.

Two invariants, both easy to break and expensive to notice:
  * agent NAMES are Temporal activity names ("never rename after deploying to
    production"), and role name != agent name for two roles.
  * dynamic imports must not run before validation, or the registry spec's
    finding 3 comes back through a new door.
"""
import pytest

from sdlc.agents.loader import RegistryError, build_agents, load_registry
from sdlc.agents.roles import MODEL_SETTINGS
from tests.conftest import _AGENT_PY, write_registry_dir

# roles.py at HEAD, verified. NOT derived from the role name: 'qa' builds
# qa_analyst_agent and 'devops_planner' builds devops_agent. 'research' is the
# optional role (Task 6); its agent_name follows the same <role>_agent pattern.
PRE_MIGRATION_AGENT_NAMES = {
    "clarify": "clarify_agent",
    "architect": "architect_agent",
    "planner": "planner_agent",
    "qa": "qa_analyst_agent",
    "reviewer": "reviewer_agent",
    "analyst": "analyst_agent",
    "merge_verdict": "merge_verdict_agent",
    "devops_planner": "devops_agent",
    "research": "research_agent",
    "deep_review": "deep_review_agent",
    "handoff": "handoff_agent",
    "adversary": "adversary_agent",
    "discover": "discover_agent",
    "risk": "risk_agent",
}


def test_agent_names_did_not_move():
    """A renamed agent is a renamed Temporal activity — a production break no
    other test in this suite would surface."""
    agents = build_agents(load_registry(), MODEL_SETTINGS)
    assert {r: a.name for r, a in agents.items()} == PRE_MIGRATION_AGENT_NAMES


def test_harness_roles_build_no_agent():
    agents = build_agents(load_registry(), MODEL_SETTINGS)
    for role in ("dev", "test", "devops"):
        assert role not in agents


def test_proposer_missing_agent_py_rejected(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.py").unlink()
    with pytest.raises(RegistryError, match="reviewer"):
        load_registry(root)


def test_agent_py_without_build_rejected(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.py").write_bytes(b"x = 1\n")
    roles = load_registry(root)          # structural check is at build time
    with pytest.raises(RegistryError, match="build"):
        build_agents(roles, MODEL_SETTINGS, agents_dir=root)


def test_duplicate_agent_names_rejected(tmp_path):
    """Only reachable now that construction is distributed across files."""
    root = write_registry_dir(tmp_path / "agents")
    (root / "analyst" / "agent.py").write_bytes(
        _AGENT_PY.format(name="reviewer_agent").encode())   # steals the name
    roles = load_registry(root)
    with pytest.raises(RegistryError, match="reviewer_agent"):
        build_agents(roles, MODEL_SETTINGS, agents_dir=root)


def test_validation_precedes_import(tmp_path):
    """An ADR-6-violating tree whose agent.py would explode on import must
    fail with RegistryError from validation, not with the import error.
    Asserts the ORDERING, not just the outcome — if build_agents ever creeps
    inside load_registry, this is what catches it."""
    root = write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.yaml").write_bytes(
        b"kind: proposer\nmodel: zai-coding-plan/other\n")     # dev's family
    for role in ("clarify", "architect"):
        (root / role / "agent.py").write_bytes(
            b"raise RuntimeError('this module must never be imported')\n")
    with pytest.raises(RegistryError, match="family"):
        load_registry(root)
