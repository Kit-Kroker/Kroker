from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.models import ImplementationPlan


def build(model: str, instructions: str, model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="planner_agent",  # Temporal activity name -- NEVER rename
        output_type=ImplementationPlan,
        model_settings=model_settings,
        system_prompt=instructions,
        # pydantic_ai's own default output-retry budget is 1. Confirmed
        # empirically against a live run (anthropic:glm-5.2 via z.ai):
        # ImplementationPlan.tasks is a long array of near-identical DevTask
        # objects, and the model twice in a row filled the first task's
        # `description` correctly, then dropped it on every task after --
        # the classic "pattern-completion" degradation on repeated
        # structured output. On the SECOND attempt pydantic_ai re-prompts
        # with the exact validation error (missing fields, by task index),
        # which is a much stronger correction signal than the original
        # prompt; a budget of 1 spends it on the very first, uncorrected
        # attempt and gives the self-correction loop no room to run. Scoped
        # to `output` only -- tool-call retries aren't the failure mode
        # here, and this run's live evidence doesn't say every proposer
        # role degrades the same way.
        retries={"output": 3},
    )
