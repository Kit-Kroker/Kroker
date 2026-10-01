from collections.abc import Sequence

from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.settings import ModelSettings

from sdlc.stages.merge.models import MergeVerdict


def build(
    model: str,
    instructions: str,
    model_settings: ModelSettings,
    *,
    capabilities: Sequence[AbstractCapability] = (),
) -> Agent:
    return Agent(
        model,
        name="merge_verdict_agent",  # Temporal activity name -- NEVER rename
        output_type=MergeVerdict,
        model_settings=model_settings,
        capabilities=list(capabilities),
        system_prompt=instructions,
    )
