from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from sdlc.stages.architecture.models import ArchitectureSpec
from sdlc.stages.research.deps import ResearchDeps
from sdlc.stages.research.models import ResearchBrief


def build(model: str, instructions: str, model_settings: ModelSettings) -> Agent:
    agent = Agent(
        model,
        name="architect_agent",  # Temporal activity name -- NEVER rename
        deps_type=ResearchDeps,
        output_type=ArchitectureSpec,
        model_settings=model_settings,
        system_prompt=instructions,
    )

    @agent.tool
    async def research(ctx: RunContext[ResearchDeps], question: str) -> ResearchBrief:
        """Consult grounded research on a sub-question. Draws down this run's
        shared research budget (SGR Routing: local vs. web)."""
        from sdlc.stages.research.toolset import research_subquery

        return await research_subquery(ctx.deps, question)

    return agent
