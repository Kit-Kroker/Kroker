from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.models import ImplementationPlan


def build(model: str, instructions: str,
          model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="planner_agent",       # Temporal activity name â NEVER rename
        output_type=ImplementationPlan,
        model_settings=model_settings,
        system_prompt=instructions,
    )
