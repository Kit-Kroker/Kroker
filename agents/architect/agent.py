from collections.abc import Sequence

from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.settings import ModelSettings

from sdlc.stages.architecture.models import ArchitectureSpec
from sdlc.stages.research.deps import ResearchDeps
from sdlc.stages.research.models import ResearchBrief


def build(
    model: str,
    instructions: str,
    model_settings: ModelSettings,
    *,
    capabilities: Sequence[AbstractCapability] = (),
) -> Agent:
    agent = Agent(
        model,
        name="architect_agent",  # Temporal activity name -- NEVER rename
        deps_type=ResearchDeps,
        output_type=ArchitectureSpec,
        model_settings=model_settings,
        capabilities=list(capabilities),
        system_prompt=instructions,
    )

    @agent.tool
    async def research(ctx: RunContext[ResearchDeps], question: str) -> ResearchBrief:
        """Consult grounded research on a sub-question. Draws down this run's
        shared research budget (SGR Routing: local vs. web)."""
        from sdlc.stages.research.toolset import research_subquery_reported, tool_return

        brief, report = await research_subquery_reported(ctx.deps, question)
        # A ToolReturn from a -> ResearchBrief tool is pydantic-ai's sanctioned
        # metadata channel; the annotation must stay a plain ResearchBrief (a
        # parameterized ToolReturn would change the tool schema the model sees).
        return tool_return(brief, report)  # type: ignore[return-value]

    return agent
