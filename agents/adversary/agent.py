from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.stages.review.models import ReviewReport


def build(model: str, instructions: str, model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="adversary_agent",  # Temporal activity name -- NEVER rename
        output_type=ReviewReport,
        model_settings=model_settings,
        system_prompt=instructions,
    )
