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
from temporalio.common import RetryPolicy
from temporalio.workflow import ActivityConfig

from ..clarify.models import ClarifyRoute, ProbeResult
from ..clarify.prompts import PROBE_SYSTEM, ROUTE_SCOPE

AGENT_ACTIVITY_CONFIG = ActivityConfig(start_to_close_timeout=timedelta(minutes=10))

# E-85: the clarify fan-out's own config. It exists ONLY because
# AGENT_ACTIVITY_CONFIG sets no retry_policy, which means Temporal's default
# applies: UNLIMITED attempts. Every other agent is a single serial call, so
# an unlimited retry there is a slow stage. For the fan-out it is a different
# failure entirely -- spec §8 and decision D10 say a dead probe degrades to
# "that dimension asked nothing" while its siblings still report, and
# _clarify_fanout implements that with asyncio.gather(return_exceptions=True).
# A retryable failure that never exhausts never raises, so gather never
# returns and the stage HANGS instead of degrading. A bounded
# maximum_attempts is what makes fail-open true rather than aspirational.
#
# Deliberately a separate ActivityConfig, not a mutation of the shared one:
# no other agent's retry behaviour changes.
CLARIFY_FANOUT_MAX_ATTEMPTS = 3
CLARIFY_FANOUT_ACTIVITY_CONFIG = ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=CLARIFY_FANOUT_MAX_ATTEMPTS),
)

from .loader import build_agents, load_registry

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

# Re-exported from agents/settings.py, which carries the rationale. It lives
# there so the eval path can import the settings without triggering this
# module's ~18s eager agent construction (E-82). This name stays importable
# from `sdlc.agents.roles` -- feature.py and worker.py rely on it.
from .settings import MODEL_SETTINGS  # noqa: E402

AGENTS = build_agents(REGISTRY, MODEL_SETTINGS)

# Module-level names are preserved verbatim: feature.py and worker.py import
# these and must not change. Note role name != agent name for two of them.
clarify_agent = AGENTS["clarify"]
architect_agent = AGENTS["architect"]
planner_agent = AGENTS["planner"]
qa_analyst_agent = AGENTS["qa"]                 # role 'qa'
reviewer_agent = AGENTS["reviewer"]
analyst_agent = AGENTS["analyst"]
merge_verdict_agent = AGENTS["merge_verdict"]
devops_agent = AGENTS["devops_planner"]         # role 'devops_planner'

# Optional research agent (2026-07-17). Present iff agents/research/ ships,
# which it does; the STAGE runs only under cfg.research_enabled (feature.py).
research_agent = AGENTS.get("research")

# Optional deep_review agent (E-39). Present iff agents/deep_review/ ships;
# the STAGE runs only under cfg.deep_review_enabled (feature.py).
deep_review_agent = AGENTS.get("deep_review")

# Optional handoff extractor (FR-805). Present iff agents/handoff/ ships.
handoff_agent = AGENTS.get("handoff")

# Optional adversarial reviewer (spec part 2). Present iff agents/adversary/
# ships; the LENS runs only under cfg.adversarial_review_enabled (feature.py).
adversary_agent = AGENTS.get("adversary")

# Optional discover proposer (E-48 DD7). Present iff agents/discover/ ships.
discover_agent = AGENTS.get("discover")

# Optional risk proposer (E-49 RD7). Present iff agents/risk/ ships.
risk_agent = AGENTS.get("risk")

# E-85: two extra agents for the clarify fan-out. NOT new registry roles --
# they reuse the clarify role's model, so agents/ stays at 15 roles and the
# loader is untouched.
#
# Only the ROUTE agent inherits agents/clarify/instructions.md. It IS the
# requirements analyst that file describes -- it authors the body and the
# out-of-scope list -- and ROUTE_SCOPE opens with "You are ALSO the ROUTER",
# composing with the preamble rather than replacing it.
#
# The PROBE agent does not, and must not: instructions.md tells its reader to
# extract requirements and define what is out of scope, while PROBE_SYSTEM
# says "You own exactly one dimension... Depth on your own dimension is the
# entire job" over an output_type (ProbeResult) with no field for either. Two
# role assignments in one system prompt is a coin flip, not a prompt.
#
# They exist as separate Agents rather than per-run output_type overrides
# because an Agent's output type is fixed at build time and t_clarify is
# pinned to ClarifiedRequirements. Keeping them as TemporalAgents means every
# call still goes through _run_role, so E-33's single model-egress accounting
# prices and attributes the spend -- research had to hand RoleUsage back from
# its activities precisely because fan-out moved its calls out of that reach.
_clarify_role = REGISTRY["clarify"]

clarify_route_agent = Agent(
    _clarify_role.model,
    name="clarify_route_agent",     # Temporal activity name -- NEVER rename
    output_type=ClarifyRoute,
    model_settings=MODEL_SETTINGS,
    system_prompt=_clarify_role.instructions + "\n\n" + ROUTE_SCOPE,
)

clarify_probe_agent = Agent(
    _clarify_role.model,
    name="clarify_probe_agent",     # Temporal activity name -- NEVER rename
    output_type=ProbeResult,
    model_settings=MODEL_SETTINGS,
    system_prompt=PROBE_SYSTEM,     # standalone -- see the note above
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
    "research": "research",             # optional; present iff the folder ships
    "deep_review": "deep_review",       # optional; present iff the folder ships
    "handoff": "handoff",               # optional; present iff the folder ships
    "adversary": "adversary",           # optional; present iff the folder ships
    "discover": "discover",             # optional; present iff the folder ships
    "risk": "risk",                     # optional; present iff the folder ships
}

# Both maps are keyed by stage and looked up together in _cached_stage. Keep
# their keyspaces identical (tests/test_stage_models.py asserts it). The
# tolerant `if role in REGISTRY` covers optional roles whose folder is absent
# (research today, possibly others later) — without it, _model(role) would
# KeyError at import on a tree that ships an OPTIONAL_ROLES slot but no folder.
STAGE_MODELS: dict[str, str] = {
    stage: _model(role) for stage, role in STAGE_ROLES.items()
    if role in REGISTRY
}

# Prompt text now lives in agents/<role>/instructions.md (E-2). The hash is
# over the same bytes it was over when the text was a Python constant --
# tests/test_prompt_migration.py pins every value.
_STAGE_PROMPTS: dict[str, str] = {
    stage: REGISTRY[role].instructions for stage, role in STAGE_ROLES.items()
    if role in REGISTRY and REGISTRY[role].instructions is not None
}

PROMPT_SHAS: dict[str, str] = {
    stage: hashlib.sha256(prompt.encode()).hexdigest()
    for stage, prompt in _STAGE_PROMPTS.items()
}

# Temporal-wrapped versions used inside workflows.
t_clarify = TemporalAgent(clarify_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_clarify_route = TemporalAgent(clarify_route_agent,
                                activity_config=CLARIFY_FANOUT_ACTIVITY_CONFIG)
t_clarify_probe = TemporalAgent(clarify_probe_agent,
                                activity_config=CLARIFY_FANOUT_ACTIVITY_CONFIG)
t_architect = TemporalAgent(architect_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_planner = TemporalAgent(planner_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_qa = TemporalAgent(qa_analyst_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_reviewer = TemporalAgent(reviewer_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_analyst = TemporalAgent(analyst_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_merge_verdict = TemporalAgent(merge_verdict_agent, activity_config=AGENT_ACTIVITY_CONFIG)
t_devops = TemporalAgent(devops_agent, activity_config=AGENT_ACTIVITY_CONFIG)

# Optional: the research TemporalAgent exists iff agents/research/ shipped
# and built cleanly. feature.py guards the stage with `t_research is not None`
# AND cfg.research_enabled before invoking it.
t_research = (TemporalAgent(research_agent, activity_config=AGENT_ACTIVITY_CONFIG)
              if research_agent is not None else None)

t_deep_review = (
    TemporalAgent(deep_review_agent, activity_config=AGENT_ACTIVITY_CONFIG)
    if deep_review_agent is not None else None)

t_handoff = (
    TemporalAgent(handoff_agent, activity_config=AGENT_ACTIVITY_CONFIG)
    if handoff_agent is not None else None)

t_adversary = (
    TemporalAgent(adversary_agent, activity_config=AGENT_ACTIVITY_CONFIG)
    if adversary_agent is not None else None)

# Optional: the discover TemporalAgent exists iff agents/discover/ shipped and
# built cleanly. workflows/assessment.py guards the phase with
# `t_discover is not None`, feature.py's t_research pattern (DD7).
t_discover = (
    TemporalAgent(discover_agent, activity_config=AGENT_ACTIVITY_CONFIG)
    if discover_agent is not None else None)

# Optional: the risk TemporalAgent exists iff agents/risk/ shipped and built
# cleanly. workflows/assessment.py guards the phase with
# `t_risk is not None`, t_discover's pattern (RD7).
t_risk = (
    TemporalAgent(risk_agent, activity_config=AGENT_ACTIVITY_CONFIG)
    if risk_agent is not None else None)

ALL_TEMPORAL_AGENTS = [t_clarify, t_clarify_route, t_clarify_probe,
                       t_architect, t_planner, t_qa,
                       t_reviewer, t_analyst, t_merge_verdict, t_devops]
if t_research is not None:
    ALL_TEMPORAL_AGENTS.append(t_research)
if t_deep_review is not None:
    ALL_TEMPORAL_AGENTS.append(t_deep_review)
if t_handoff is not None:
    ALL_TEMPORAL_AGENTS.append(t_handoff)
if t_adversary is not None:
    ALL_TEMPORAL_AGENTS.append(t_adversary)
if t_discover is not None:
    ALL_TEMPORAL_AGENTS.append(t_discover)
if t_risk is not None:
    ALL_TEMPORAL_AGENTS.append(t_risk)

