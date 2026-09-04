from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.stages.qa.models import QAReport


def build(model: str, instructions: str, model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="qa_analyst_agent",  # Temporal activity name -- NEVER rename
        output_type=QAReport,
        model_settings=model_settings,
        system_prompt=instructions,
    )
