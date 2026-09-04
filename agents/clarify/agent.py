from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.stages.clarify.models import ClarifiedRequirements


def build(model: str, instructions: str, model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="clarify_agent",  # Temporal activity name -- NEVER rename
        output_type=ClarifiedRequirements,
        model_settings=model_settings,
        system_prompt=instructions,
    )
