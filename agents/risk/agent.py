from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.assessment.risk.models import RiskProposal


def build(model: str, instructions: str,
          model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="risk_agent",          # Temporal activity name -- NEVER rename
        output_type=RiskProposal,
        model_settings=model_settings,
        system_prompt=instructions,
    )
