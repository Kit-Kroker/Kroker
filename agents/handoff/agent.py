from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.stages.code.models import HandoffSummary


def build(model: str, instructions: str, model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="handoff_agent",  # Temporal activity name -- NEVER rename
        output_type=HandoffSummary,
        model_settings=model_settings,
        system_prompt=instructions,
    )
