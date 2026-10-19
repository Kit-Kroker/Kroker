import importlib.util
from collections.abc import Sequence
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.settings import ModelSettings
from pydantic_ai_harness import CodeMode

from sdlc.stages.research.deps import ResearchDeps
from sdlc.stages.research.models import ResearchBrief


def _import_exa_wrapper():
    path = str(Path(__file__).parent / "exa_wrapper.py")
    spec = importlib.util.spec_from_file_location("_sdlc_exa_wrapper", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.get_wrapped_exa_search


def _import_tool(path: str):
    """Import one agents/research/tools/<name>.py by PATH under a private
    module name and return its <name> function (== the file stem)."""
    stem = Path(path).stem
    spec = importlib.util.spec_from_file_location(f"_sdlc_tool_{stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, stem)


def build(
    model: str,
    instructions: str,
    model_settings: ModelSettings,
    tool_paths: list[str],
    provider: str,
    *,
    capabilities: Sequence[AbstractCapability] = (),
) -> Agent:
    """The research role: a proposer with four plain tools. Uniquely among
    roles it receives tool_paths and provider — supplied by build_agents AFTER
    the whole registry validated (validation precedes import).

    """
    # Loader-supplied capabilities (durability) stay FIRST/outermost; this
    # role's own (CodeMode, exa) append after them (003 contract).
    own_capabilities: list[AbstractCapability] = []
    if provider == "exa":
        get_wrapped_exa_search = _import_exa_wrapper()
        own_capabilities = [
            CodeMode(),
            get_wrapped_exa_search()(include_deep_search=True),
        ]

    agent = Agent(
        model,
        name="research_agent",  # Temporal activity name — NEVER rename
        deps_type=ResearchDeps,
        output_type=ResearchBrief,
        model_settings=model_settings,
        system_prompt=instructions,
        capabilities=[*capabilities, *own_capabilities],
        # pydantic_ai's default output-retry budget is 1. The
        # research-partial-salvage assessment measured a live
        # "Exceeded maximum output retries (1)": one malformed final
        # brief killed the whole sub-question attempt, which then
        # restarted from scratch and burned its remaining request
        # budget. On a retry pydantic_ai re-prompts with the exact
        # validation error — a far stronger correction signal than the
        # original prompt — so a budget of 1 spends its only retry on
        # the first, uncorrected attempt and gives the self-correction
        # loop no room. Scoped to `output` only (same shape and value
        # as the planner's agents/planner/agent.py:40): tool-result
        # retries aren't this role's failure mode, and the retry must
        # also leave room for a future "conclude on the last request"
        # mechanism, where a schema retry on the forced turn becomes
        # request N+1 and dies at a budget of 1.
        retries={"output": 3},
    )
    for path in tool_paths:
        if "web_search" in path or "fetch_page" in path:
            continue
        agent.tool(_import_tool(path))  # @agent.tool: each takes RunContext
    return agent
