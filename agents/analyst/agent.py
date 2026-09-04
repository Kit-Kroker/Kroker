from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.stages.analyze.models import AnalysisReport


def build(model: str, instructions: str, model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="analyst_agent",  # Temporal activity name -- NEVER rename
        output_type=AnalysisReport,
        model_settings=model_settings,
        system_prompt=instructions,
    )
