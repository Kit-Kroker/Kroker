"""'Thinking' role agents — Pydantic AI, wrapped in TemporalAgent.

These agents never touch the repo. They read artifacts (via tools if
needed) and emit typed pipeline contracts. Model requests and tool calls
are automatically offloaded to Temporal activities by TemporalAgent.

IMPORTANT: agent names and toolset ids become Temporal activity names.
Set them explicitly and never rename after deploying to production.
"""
from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalAgent
from pydantic_ai.settings import ModelSettings
from datetime import timedelta
import hashlib
import os
from temporalio.workflow import ActivityConfig

AGENT_ACTIVITY_CONFIG = ActivityConfig(start_to_close_timeout=timedelta(minutes=10))

from .loader import load_registry

from ..models import (
    AnalysisReport,
    ArchitectureSpec,
    ClarifiedRequirements,
    ImplementationPlan,
    MergeVerdict,
    QAReport,
    ReviewReport,
)

# The registry (FR-201) is the single source of every role's model. It is
# loaded AND validated here at import (loader.load_registry validates), so a
# registry violating ADR-6 cannot even import this module, let alone boot a
# worker. There is deliberately no fleet-wide default model constant: a role's
# model comes from its own registry entry or the registry is incomplete and
# fails closed.
REGISTRY = load_registry()


def _model(role: str) -> str:
    """The model this role declares. KeyError is unreachable — REQUIRED_ROLES
    is checked during load_registry above."""
    return REGISTRY[role].model

# Structured-output agents emit typed tool calls; Pydantic AI's 4096-token
# default truncates the tool-call arguments to {} on larger schemas (or when
# the model spends tokens on reasoning first). Override via SDLC_MODEL_MAX_TOKENS.
MODEL_SETTINGS = ModelSettings(max_tokens=int(
    os.environ.get("SDLC_MODEL_MAX_TOKENS", "64000")))

clarify_agent = Agent(
    _model("clarify"),
    name="clarify_agent",
    output_type=ClarifiedRequirements,
    model_settings=MODEL_SETTINGS,
    system_prompt=REGISTRY["clarify"].instructions,
)

architect_agent = Agent(
    _model("architect"),
    name="architect_agent",
    output_type=ArchitectureSpec,
    model_settings=MODEL_SETTINGS,
    system_prompt=REGISTRY["architect"].instructions,
)

planner_agent = Agent(
    _model("planner"),
    name="planner_agent",
    output_type=ImplementationPlan,
    model_settings=MODEL_SETTINGS,
    system_prompt=REGISTRY["planner"].instructions,
)

qa_analyst_agent = Agent(
    _model("qa"),
    name="qa_analyst_agent",
    output_type=QAReport,
    model_settings=MODEL_SETTINGS,
    system_prompt=REGISTRY["qa"].instructions,
)

reviewer_agent = Agent(
    _model("reviewer"),
    name="reviewer_agent",
    output_type=ReviewReport,
    model_settings=MODEL_SETTINGS,
    system_prompt=REGISTRY["reviewer"].instructions,
)

analyst_agent = Agent(
    _model("analyst"),
    name="analyst_agent",
    output_type=AnalysisReport,
    model_settings=MODEL_SETTINGS,
    system_prompt=REGISTRY["analyst"].instructions,
)

merge_verdict_agent = Agent(
    _model("merge_verdict"),
    name="merge_verdict_agent",
    output_type=MergeVerdict,
    model_settings=MODEL_SETTINGS,
    system_prompt=REGISTRY["merge_verdict"].instructions,
)

devops_agent = Agent(
    _model("devops_planner"),
    name="devops_agent",
    output_type=ImplementationPlan,  # devops tasks reuse the task shape
    model_settings=MODEL_SETTINGS,
    system_prompt=REGISTRY["devops_planner"].instructions,
)

# Stage name -> registry role. Stage names (feature.py's pipeline vocabulary)
# and role names (the registry's) genuinely differ — 'plan'/'planner',
# 'review'/'reviewer', 'analyze'/'analyst', 'devops'/'devops_planner'. This
# table is the ONE place that divergence is reconciled.
STAGE_ROLES: dict[str, str] = {
    "clarify": "clarify",
    "architect": "architect",
    "plan": "planner",
    "devops": "devops_planner",
    "review": "reviewer",
    "analyze": "analyst",
    "qa": "qa",
    "merge_verdict": "merge_verdict",
}

# Both maps are keyed by stage and looked up together in _cached_stage. Keep
# their keyspaces identical (tests/test_stage_models.py asserts it).
STAGE_MODELS: dict[str, str] = {
    stage: _model(role) for stage, role in STAGE_ROLES.items()
}

# Prompt text now lives in agents/<role>/instructions.md (E-2). The hash is
# over the same bytes it was over when the text was a Python constant --
# tests/test_prompt_migration.py pins every value.
_STAGE_PROMPTS: dict[str, str] = {
    stage: REGISTRY[role].instructions for stage, role in STAGE_ROLES.items()
}

PROMPT_SHAS: dict[str, str] = {
    stage: hashlib.sha256(prompt.encode()).hexdigest()
    for stage, prompt in _STAGE_PROMPTS.items()
}

# Temporal-wrapped versions used inside workflows.
t_clarify = TemporalAgent(clarify_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_architect = TemporalAgent(architect_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_planner = TemporalAgent(planner_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_qa = TemporalAgent(qa_analyst_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_reviewer = TemporalAgent(reviewer_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_analyst = TemporalAgent(analyst_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_merge_verdict = TemporalAgent(merge_verdict_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_devops = TemporalAgent(devops_agent, activity_config=AGENT_ACTIVITY_CONFIG)

ALL_TEMPORAL_AGENTS = [t_clarify, t_architect, t_planner, t_qa,
                       t_reviewer, t_analyst, t_merge_verdict, t_devops]
