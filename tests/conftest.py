"""Shared test fixtures."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

# Importing sdlc.worker (transitively, from many test modules) pulls in
# pydantic_ai agents that read ANTHROPIC_API_KEY / OPENAI_API_KEY at import
# time, and the shipped research role (provider: exa) builds an ExaSearch
# client that reads EXA_API_KEY at construction time. conftest is imported
# before any test module, so set placeholders here at module load so
# collection-time agent construction succeeds. The autouse _llm_api_keys
# fixture below still monkeypatches per-test for hygiene.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy")
os.environ.setdefault("OPENAI_API_KEY", "test-dummy")
os.environ.setdefault("EXA_API_KEY", "test-dummy")


def run_git(args: list[str], cwd: str | Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True,
        capture_output=True, text=True,
    ).stdout


@pytest.fixture(autouse=True)
def _llm_api_keys(monkeypatch):
    """Importing ``sdlc.worker`` pulls in pydantic_ai agents that read
    ANTHROPIC_API_KEY / OPENAI_API_KEY at import time. Set placeholder
    values so deferred in-package imports inside tests never fail."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("EXA_API_KEY", "test-key")


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """A fresh git repo with one commit on `main`, plus a writable
    worktrees root so the activities never touch /var."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(["init", "-b", "main"], repo)
    run_git(["config", "user.email", "t@t.co"], repo)
    run_git(["config", "user.name", "sdlc-test"], repo)
    (repo / "README.md").write_text("seed\n")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-m", "seed"], repo)
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wt"))
    return str(repo)


_HARNESS_AGENT_YAML = (
    b"kind: harness\nharness: opencode\nmodel: zai-coding-plan/glm-5.2\n")
_PROPOSER_AGENT_YAML = b"kind: proposer\nmodel: anthropic:glm-5.2\n"

HARNESS_ROLE_NAMES = ("dev", "test", "devops")
PROPOSER_ROLE_NAMES = ("clarify", "architect", "planner", "qa", "reviewer",
                       "analyst", "merge_verdict", "devops_planner")

_AGENT_PY = (
    "from pydantic_ai import Agent\n"
    "def build(model, instructions, model_settings):\n"
    "    return Agent(model, name={name!r}, model_settings=model_settings,\n"
    "                 system_prompt=instructions)\n"
)

# Role -> agent name. Mirrors roles.py; NOT derived — 'qa' builds
# qa_analyst_agent, 'devops_planner' builds devops_agent.
_TEST_AGENT_NAMES = {
    "clarify": "clarify_agent", "architect": "architect_agent",
    "planner": "planner_agent", "qa": "qa_analyst_agent",
    "reviewer": "reviewer_agent", "analyst": "analyst_agent",
    "merge_verdict": "merge_verdict_agent", "devops_planner": "devops_agent",
}


def write_registry_dir(root, version=1):
    """Materialise a VALID agents/ tree. Tests perturb exactly one thing after
    calling this, so each assertion fails for the reason under test.

    Grows with the increment: Task 2 adds instructions.md, Task 3 adds
    agent.py. Keep it valid or every caller breaks at once.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "registry.yaml").write_bytes(f"version: {version}\n".encode())
    for name in HARNESS_ROLE_NAMES:
        d = root / name
        d.mkdir(exist_ok=True)
        (d / "agent.yaml").write_bytes(_HARNESS_AGENT_YAML)
    for name in PROPOSER_ROLE_NAMES:
        d = root / name
        d.mkdir(exist_ok=True)
        (d / "agent.yaml").write_bytes(_PROPOSER_AGENT_YAML)
        (d / "instructions.md").write_bytes(b"do the thing")   # Task 2
        (d / "agent.py").write_bytes(
            _AGENT_PY.format(name=_TEST_AGENT_NAMES[name]).encode())  # Task 3
    # Optional research role (2026-07-17-research-agent-grounded-briefs).
    # A VALID research tree: agent.yaml (kind=research, provider=fake),
    # instructions.md, agent.py, and one tool file. Tests perturb one thing.
    r = root / "research"
    r.mkdir(exist_ok=True)
    (r / "agent.yaml").write_bytes(
        b"kind: research\nmodel: anthropic:glm-5.2\nprovider: fake\n")
    (r / "instructions.md").write_bytes(b"research the question")
    (r / "agent.py").write_bytes(
        b"from pydantic_ai import Agent\n"
        b"def build(model, instructions, model_settings, tool_paths, provider):\n"
        b"    return Agent(model, name='research_agent',\n"
        b"                 model_settings=model_settings,\n"
        b"                 system_prompt=instructions)\n")
    (r / "tools").mkdir(exist_ok=True)
    (r / "tools" / "web_search.py").write_bytes(
        b"async def web_search(query: str, max_results: int = 5) -> list:\n"
        b"    return []\n")
    # Optional deep_review role (E-39): a plain proposer, non-dev family.
    dr = root / "deep_review"
    dr.mkdir(exist_ok=True)
    (dr / "agent.yaml").write_bytes(
        b"kind: proposer\nmodel: anthropic:glm-5.2\n")
    (dr / "instructions.md").write_bytes(b"deep review the transcript")
    (dr / "agent.py").write_bytes(
        b"from pydantic_ai import Agent\n"
        b"def build(model, instructions, model_settings):\n"
        b"    return Agent(model, name='deep_review_agent',\n"
        b"                 system_prompt=instructions)\n")
    # Optional handoff extractor (FR-805): a plain proposer. No ADR-6
    # constraint applies to it -- it is extraction, not review.
    ho = root / "handoff"
    ho.mkdir(exist_ok=True)
    (ho / "agent.yaml").write_bytes(
        b"kind: proposer\nmodel: anthropic:glm-5.2\n")
    (ho / "instructions.md").write_bytes(b"extract the handoff")
    (ho / "agent.py").write_bytes(
        b"from pydantic_ai import Agent\n"
        b"def build(model, instructions, model_settings):\n"
        b"    return Agent(model, name='handoff_agent',\n"
        b"                 system_prompt=instructions)\n")
    # Optional adversarial reviewer (spec part 2): a different MODEL ID from
    # dev/reviewer (both glm-5.2 here) so check_adversary_model passes.
    adv = root / "adversary"
    adv.mkdir(exist_ok=True)
    (adv / "agent.yaml").write_bytes(
        b"kind: proposer\nmodel: anthropic:claude-sonnet-4-6\n")
    (adv / "instructions.md").write_bytes(b"adversarially review the diff")
    (adv / "agent.py").write_bytes(
        b"from pydantic_ai import Agent\n"
        b"def build(model, instructions, model_settings):\n"
        b"    return Agent(model, name='adversary_agent',\n"
        b"                 system_prompt=instructions)\n")
    return root
