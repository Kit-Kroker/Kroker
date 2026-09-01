from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.assessment.discover.map import DiscoverProposal


def build(model: str, instructions: str, model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="discover_agent",  # Temporal activity name -- NEVER rename
        output_type=DiscoverProposal,
        model_settings=model_settings,
        system_prompt=instructions,
    )
