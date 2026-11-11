from collections.abc import Sequence

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.settings import ModelSettings
from pydantic_ai_harness import FileSystem, RepoContext

from sdlc.stages.constitution.deps import ConstitutionDeps
from sdlc.stages.constitution.models import DraftOutput


def build(
    model: str,
    instructions: str,
    model_settings: ModelSettings,
    *,
    capabilities: Sequence[AbstractCapability] = (),
) -> Agent:
    """The constitution drafter: reads the repo's instruction files and
    proposes governing principles (FR-112)."""
    # Loader-supplied capabilities (durability, resolver, guard) stay
    # FIRST/outermost; this role's own (read-only FileSystem, RepoContext)
    # append after them (003 contract). The FileSystem workspace arrives at
    # RUN time from the caller — attaching the capability here is the
    # correct half of that handshake.
    own_capabilities: list[AbstractCapability] = [
        FileSystem(
            read_only=True,
            tools=["read_file", "search_files", "find_files", "list_directory"],
        ),
        RepoContext(),  # defaults: home_dir=None — no walk-up past the workspace
    ]
    return Agent(
        model,
        name="constitution_agent",  # Temporal activity name — NEVER rename
        deps_type=ConstitutionDeps,
        # The agent proposes the DRAFT; freeze() (verify.py) assigns ids and
        # the digest — the model never names the artifact's ids.
        output_type=DraftOutput,
        model_settings=model_settings,
        system_prompt=instructions,
        capabilities=[*capabilities, *own_capabilities],
        # Same shape and value as the planner's and research's (agents/
        # planner/agent.py:40, agents/research/agent.py:79): a malformed
        # final draft re-prompts with the exact validation error, so a
        # budget of 1 spends its only retry on the uncorrected attempt;
        # 3 gives the self-correction loop room. Scoped to `output` only —
        # tool-result retries aren't this role's failure mode.
        retries={"output": 3},
    )
