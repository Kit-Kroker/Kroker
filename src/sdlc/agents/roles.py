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
    "criteria into a ValidationContract: concrete, checkable assertions, "
    "test commands, and lint commands, written before any code exists — "
    "correctness will be judged against this contract, not the "
    "implementation. 'test_commands' and 'lint_commands' MUST be real, "
    "runnable shell commands for the stack chosen in the architecture "
    "(e.g. 'npm test', 'npm run lint' for TypeScript/Node — never assume "
    "a Python toolchain like pytest/ruff unless the stack actually is "
    "Python). These commands may run in a worktree that has never had "
    "dependencies installed (e.g. the integration branch, which "
    "accumulates merged code but is never `npm install`/`pip install`-ed "
    "on its own) — each command MUST be self-contained, installing its "
    "own dependencies first (e.g. 'npm install && npm test'), never "
    "assuming a prior install step already ran. Set "
    "'stack' on EVERY task's contract to the exact language/runtime/"
    "package manager decided in the architecture (e.g. 'TypeScript/"
    "Node.js, npm workspaces'), copied verbatim — this is a hard "
    "constraint the coding agent must not deviate from, not a soft "
    "acceptance criterion. "
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
    "per unmet assertion. Set 'stack_mismatch' to true ONLY when the diff "
    "uses a fundamentally different language/runtime/package manager than "
    "the contract's 'stack' field (e.g. Python instead of the required "
    "TypeScript) — never for a merely incomplete implementation within "
    "the correct stack."
)
REVIEWER_PROMPT = (
    "You are a clean-context code reviewer. You receive ONLY: the task's "
    "frozen ValidationContract assertions, the test output, and the "
    "materialized diff. You never see, and must never request, the "
    "implementer's summary, reasoning, or session. Judge whether the diff "
    "correctly and safely satisfies each contract assertion. Report concrete "
    "findings with a severity of 'critical', 'high', 'medium', or 'low' and a "
    "suggested fix. Set 'approve' to false if ANY finding is 'critical' or "
    "'high'. Set confidence to a calibrated 0.0-1.0 self-assessment."
)
ANALYST_PROMPT = (
    "You are a clean-context release analyst. You receive ONLY: the run's "
    "acceptance criteria (each tagged with its task id), the materialized "
    "integration diff, and the aggregate test output. You never see, and "
    "must never request, any implementer's summary, reasoning, or session. "
    "For EACH acceptance criterion, populate a CriterionTrace with the exact "
    "test name(s) in the diff/test output that verify it; leave 'tests' empty "
    "if nothing does — do NOT invent a test name. Copy each criterion's "
    "task_id and text verbatim so it matches the plan. Report any "
    "integration-level concerns as 'findings'. Set a calibrated 0.0-1.0 "
    "confidence. You do not decide pass/fail — you only propose the mapping."
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
    _model("clarify"),
    name="clarify_agent",
    output_type=ClarifiedRequirements,
    model_settings=MODEL_SETTINGS,
    system_prompt=CLARIFY_PROMPT,
)

architect_agent = Agent(
    _model("architect"),
    name="architect_agent",
    output_type=ArchitectureSpec,
    model_settings=MODEL_SETTINGS,
    system_prompt=ARCHITECT_PROMPT,
)

planner_agent = Agent(
    _model("planner"),
    name="planner_agent",
    output_type=ImplementationPlan,
    model_settings=MODEL_SETTINGS,
    system_prompt=PLAN_PROMPT,
)

qa_analyst_agent = Agent(
    _model("qa"),
    name="qa_analyst_agent",
    output_type=QAReport,
    model_settings=MODEL_SETTINGS,
    system_prompt=QA_PROMPT,
)

reviewer_agent = Agent(
    _model("reviewer"),
    name="reviewer_agent",
    output_type=ReviewReport,
    model_settings=MODEL_SETTINGS,
    system_prompt=REVIEWER_PROMPT,
)

analyst_agent = Agent(
    _model("analyst"),
    name="analyst_agent",
    output_type=AnalysisReport,
    model_settings=MODEL_SETTINGS,
    system_prompt=ANALYST_PROMPT,
)

merge_verdict_agent = Agent(
    _model("merge_verdict"),
    name="merge_verdict_agent",
    output_type=MergeVerdict,
    model_settings=MODEL_SETTINGS,
    system_prompt=MERGE_VERDICT_PROMPT,
)

devops_agent = Agent(
    _model("devops_planner"),
    name="devops_agent",
    output_type=ImplementationPlan,  # devops tasks reuse the task shape
    model_settings=MODEL_SETTINGS,
    system_prompt=DEVOPS_PROMPT,
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

_STAGE_PROMPTS: dict[str, str] = {
    "clarify": CLARIFY_PROMPT,
    "architect": ARCHITECT_PROMPT,
    "plan": PLAN_PROMPT,
    "devops": DEVOPS_PROMPT,
    "review": REVIEWER_PROMPT,
    "analyze": ANALYST_PROMPT,
    "qa": QA_PROMPT,
    "merge_verdict": MERGE_VERDICT_PROMPT,
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
