import importlib.util
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.models import ResearchBrief
from sdlc.research.deps import ResearchDeps

from pydantic_ai_harness import CodeMode
def _import_exa_wrapper():
    path = str(Path(__file__).parent / "exa_wrapper.py")
    spec = importlib.util.spec_from_file_location("_sdlc_exa_wrapper", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "get_wrapped_exa_search")


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

    """
    capabilities = []
    if provider == "exa":
        get_wrapped_exa_search = _import_exa_wrapper()
        capabilities = [
            CodeMode(),
            get_wrapped_exa_search()(include_deep_search=True)
        ]
        
    agent = Agent(
        model,
        name="research_agent",              # Temporal activity name — NEVER rename
        deps_type=ResearchDeps,
        output_type=ResearchBrief,
        model_settings=model_settings,
        system_prompt=instructions,
        capabilities=capabilities
    )
    for path in tool_paths:
        if "web_search" in path or "fetch_page" in path:
            continue
        agent.tool(_import_tool(path))      # @agent.tool: each takes RunContext
    return agent
