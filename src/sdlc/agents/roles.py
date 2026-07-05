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

from ..models import (
    ArchitectureSpec,
    ClarifiedRequirements,
    ImplementationPlan,
    MergeVerdict,
    QAReport,
)

MODEL = "anthropic:glm-5.2"

# Structured-output agents emit typed tool calls; Pydantic AI's 4096-token
# default truncates the tool-call arguments to {} on larger schemas (or when
# the model spends tokens on reasoning first). Override via SDLC_MODEL_MAX_TOKENS.
MODEL_SETTINGS = ModelSettings(max_tokens=int(
    os.environ.get("SDLC_MODEL_MAX_TOKENS", "64000")))

CLARIFY_PROMPT = (
    "You are a requirements analyst. Given a feature idea, extract "
    "functional and non-functional requirements, define what is out of "
    "scope, and list ONLY the open questions whose answers materially "
    "change the design (Definition-of-Ready style). For each question "
    "include a suggested answer so the human can approve or override."
)
ARCHITECT_PROMPT = (
    "You are a software architect. Produce an architecture spec with "
    "explicit, numbered decisions and rationale. In BROWNFIELD mode, "
    "ground every decision in the provided codebase map and list the "
    "affected modules as a delta (added / modified / removed). In "
    "GREENFIELD mode, decide stack, project structure and key ADRs. "
    "Prefer boring technology; flag risks explicitly. "
    "Set confidence to a calibrated 0.0-1.0 self-assessment of how "
    "confident you are this spec is correct and complete — reserve high "
    "confidence for genuinely low-risk, well-understood designs."
)
PLAN_PROMPT = (
    "You are a tech lead. Decompose the approved architecture into "
    "small, independently mergeable dev tasks with acceptance criteria "
    "and dependency edges. For EVERY task, compile its acceptance "
    "criteria into a ValidationContract: concrete, checkable assertions "
    "and test commands, written before any code exists — correctness "
    "will be judged against this contract, not the implementation. "
    "Declare 'overlaps': modules any two tasks both touch (overlapping "
    "tasks will be serialized). Each task must be completable by a "
    "coding agent in one focused session. Include dedicated 'test' "
    "tasks and 'devops' tasks (CI, infra, deploy config) where needed. "
    "Set confidence to a calibrated 0.0-1.0 self-assessment of how "
    "confident you are this plan is correct and complete — reserve high "
    "confidence for genuinely low-risk, well-scoped task breakdowns."
)
QA_PROMPT = (
    "You are a clean-context QA validator. You receive ONLY: the task's "
    "frozen ValidationContract, test output, and the materialized diff. "
    "You never see, and must never request, the implementer's summary "
    "or reasoning. Judge whether the diff satisfies each contract "
    "assertion — not whether tests merely pass. List concrete issues "
    "per unmet assertion."
)
MERGE_VERDICT_PROMPT = (
    "You are an ADVISORY release reviewer, consulted only after the "
    "deterministic quality gate has already passed. Given the QA report, "
    "reviewer summary and diff stats, give a confidence-scored opinion on "
    "whether the merge should proceed. You cannot block a merge on your "
    "own and you cannot approve one the deterministic gate failed; you "
    "only advise. Be conservative and list concrete concerns."
)
DEVOPS_PROMPT = (
    "You are a DevOps engineer. Given the architecture and repo state, "
    "produce the pipeline/infra tasks needed to ship this feature: "
    "CI updates, migrations, feature flags, deploy and rollback steps."
)

clarify_agent = Agent(
    MODEL,
    name="clarify_agent",
    output_type=ClarifiedRequirements,
    model_settings=MODEL_SETTINGS,
    system_prompt=CLARIFY_PROMPT,
)

architect_agent = Agent(
    MODEL,
    name="architect_agent",
    output_type=ArchitectureSpec,
    model_settings=MODEL_SETTINGS,
    system_prompt=ARCHITECT_PROMPT,
)

planner_agent = Agent(
    MODEL,
    name="planner_agent",
    output_type=ImplementationPlan,
    model_settings=MODEL_SETTINGS,
    system_prompt=PLAN_PROMPT,
)

qa_analyst_agent = Agent(
    MODEL,
    name="qa_analyst_agent",
    output_type=QAReport,
    model_settings=MODEL_SETTINGS,
    system_prompt=QA_PROMPT,
)

merge_verdict_agent = Agent(
    MODEL,
    name="merge_verdict_agent",
    output_type=MergeVerdict,
    model_settings=MODEL_SETTINGS,
    system_prompt=MERGE_VERDICT_PROMPT,
)

devops_agent = Agent(
    MODEL,
    name="devops_agent",
    output_type=ImplementationPlan,  # devops tasks reuse the task shape
    model_settings=MODEL_SETTINGS,
    system_prompt=DEVOPS_PROMPT,
)

PROMPT_SHAS: dict[str, str] = {
    "clarify": hashlib.sha256(CLARIFY_PROMPT.encode()).hexdigest(),
    "architect": hashlib.sha256(ARCHITECT_PROMPT.encode()).hexdigest(),
    "plan": hashlib.sha256(PLAN_PROMPT.encode()).hexdigest(),
    "devops": hashlib.sha256(DEVOPS_PROMPT.encode()).hexdigest(),
}

# Temporal-wrapped versions used inside workflows.
t_clarify = TemporalAgent(clarify_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_architect = TemporalAgent(architect_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_planner = TemporalAgent(planner_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_qa = TemporalAgent(qa_analyst_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_merge_verdict = TemporalAgent(merge_verdict_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_devops = TemporalAgent(devops_agent, activity_config=AGENT_ACTIVITY_CONFIG)

ALL_TEMPORAL_AGENTS = [t_clarify, t_architect, t_planner, t_qa,
                       t_merge_verdict, t_devops]
