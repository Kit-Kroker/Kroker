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

from .models import (
    ArchitectureSpec,
    ClarifiedRequirements,
    GateDecision,
    IdeaBrief,
    ImplementationPlan,
    QAReport,
)

MODEL = "anthropic:claude-sonnet-4-6"

clarify_agent = Agent(
    MODEL,
    name="clarify_agent",
    output_type=ClarifiedRequirements,
    system_prompt=(
        "You are a requirements analyst. Given a feature idea, extract "
        "functional and non-functional requirements, define what is out of "
        "scope, and list ONLY the open questions whose answers materially "
        "change the design (Definition-of-Ready style). For each question "
        "include a suggested answer so the human can approve or override."
    ),
)

architect_agent = Agent(
    MODEL,
    name="architect_agent",
    output_type=ArchitectureSpec,
    system_prompt=(
        "You are a software architect. Produce an architecture spec with "
        "explicit, numbered decisions and rationale. In BROWNFIELD mode, "
        "ground every decision in the provided codebase map and list the "
        "affected modules as a delta (added / modified / removed). In "
        "GREENFIELD mode, decide stack, project structure and key ADRs. "
        "Prefer boring technology; flag risks explicitly."
    ),
)

planner_agent = Agent(
    MODEL,
    name="planner_agent",
    output_type=ImplementationPlan,
    system_prompt=(
        "You are a tech lead. Decompose the approved architecture into "
        "small, independently mergeable dev tasks with acceptance criteria "
        "and dependency edges. For EVERY task, compile its acceptance "
        "criteria into a ValidationContract: concrete, checkable assertions "
        "and test commands, written before any code exists — correctness "
        "will be judged against this contract, not the implementation. "
        "Declare 'overlaps': modules any two tasks both touch (overlapping "
        "tasks will be serialized). Each task must be completable by a "
        "coding agent in one focused session. Include dedicated 'test' "
        "tasks and 'devops' tasks (CI, infra, deploy config) where needed."
    ),
)

qa_analyst_agent = Agent(
    MODEL,
    name="qa_analyst_agent",
    output_type=QAReport,
    system_prompt=(
        "You are a clean-context QA validator. You receive ONLY: the task's "
        "frozen ValidationContract, test output, and the materialized diff. "
        "You never see, and must never request, the implementer's summary "
        "or reasoning. Judge whether the diff satisfies each contract "
        "assertion — not whether tests merely pass. List concrete issues "
        "per unmet assertion."
    ),
)

quality_gate_agent = Agent(
    MODEL,
    name="quality_gate_agent",
    output_type=GateDecision,
    system_prompt=(
        "You are a release gate. Given the QA report, reviewer summary and "
        "diff stats, decide approve/reject for the SOFT gate policy. Be "
        "conservative: reject on failing tests, security smells, missing "
        "acceptance criteria, or reviewer objections. Explain briefly."
    ),
)

devops_agent = Agent(
    MODEL,
    name="devops_agent",
    output_type=ImplementationPlan,  # devops tasks reuse the task shape
    system_prompt=(
        "You are a DevOps engineer. Given the architecture and repo state, "
        "produce the pipeline/infra tasks needed to ship this feature: "
        "CI updates, migrations, feature flags, deploy and rollback steps."
    ),
)

# Temporal-wrapped versions used inside workflows.
t_clarify = TemporalAgent(clarify_agent)
t_architect = TemporalAgent(architect_agent)
t_planner = TemporalAgent(planner_agent)
t_qa = TemporalAgent(qa_analyst_agent)
t_gate = TemporalAgent(quality_gate_agent)
t_devops = TemporalAgent(devops_agent)

ALL_TEMPORAL_AGENTS = [t_clarify, t_architect, t_planner, t_qa, t_gate, t_devops]
