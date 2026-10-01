from collections.abc import Sequence

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.settings import ModelSettings

from sdlc.stages.clarify.models import ClarifiedRequirements


def build(
    model: str,
    instructions: str,
    model_settings: ModelSettings,
    *,
    capabilities: Sequence[AbstractCapability] = (),
) -> Agent:
    return Agent(
        model,
        name="clarify_agent",  # Temporal activity name -- NEVER rename
        output_type=ClarifiedRequirements,
        model_settings=model_settings,
        capabilities=list(capabilities),
        system_prompt=instructions,
    )
