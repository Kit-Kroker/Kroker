import importlib.util
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.models import ResearchBrief
from sdlc.research.deps import ResearchDeps


def _import_tool(path: str):
    """Import one agents/research/tools/<name>.py by PATH under a private
    module name and return its <name> function (== the file stem)."""
    stem = Path(path).stem
    spec = importlib.util.spec_from_file_location(f"_sdlc_tool_{stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, stem)


def build(model: str, instructions: str, model_settings: ModelSettings,
          tool_paths: list[str], provider: str) -> Agent:
    """The research role: a proposer with four plain tools. Uniquely among
    roles it receives tool_paths and provider — supplied by build_agents AFTER
    the whole registry validated (validation precedes import).

    (Amended 2026-07-17: the original design used CodeMode to collapse the
    tool fan-out into one run_code activity with a shared in-process budget
    counter. Task 1's spike proved CodeMode untestable via TestModel under
    TemporalAgent, so the human-authorised fallback ships plain sequential
    tools. The shared-counter guarantee is a Task 8 concern.)"""
    agent = Agent(
        model,
        name="research_agent",              # Temporal activity name — NEVER rename
        deps_type=ResearchDeps,
        output_type=ResearchBrief,
        model_settings=model_settings,
        system_prompt=instructions,
    )
    for path in tool_paths:
        agent.tool(_import_tool(path))      # @agent.tool: each takes RunContext
    return agent
