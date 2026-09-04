from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.stages.plan.models import ImplementationPlan


def build(model: str, instructions: str, model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="devops_agent",  # Temporal activity name -- NEVER rename
        output_type=ImplementationPlan,  # devops tasks reuse the task shape
        model_settings=model_settings,
        system_prompt=instructions,
    )
