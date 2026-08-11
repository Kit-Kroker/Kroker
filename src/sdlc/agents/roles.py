"""'Thinking' role agents — Pydantic AI, wrapped in TemporalAgent.

These agents never touch the repo. They read artifacts (via tools if
needed) and emit typed pipeline contracts. Model requests and tool calls
are automatically offloaded to Temporal activities by TemporalAgent.

IMPORTANT: agent names and toolset ids become Temporal activity names.
Set them explicitly and never rename after deploying to production.
"""
from __future__ import annotations

from pydantic_ai.durable_exec.temporal import TemporalAgent
from pydantic_ai.settings import ModelSettings
from datetime import timedelta
import hashlib
import os
from temporalio.workflow import ActivityConfig

AGENT_ACTIVITY_CONFIG = ActivityConfig(start_to_close_timeout=timedelta(minutes=10))

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

ALL_TEMPORAL_AGENTS = [t_clarify, t_architect, t_planner, t_qa,
                       t_reviewer, t_analyst, t_merge_verdict, t_devops]
if t_research is not None:
    ALL_TEMPORAL_AGENTS.append(t_research)
if t_deep_review is not None:
    ALL_TEMPORAL_AGENTS.append(t_deep_review)
if t_handoff is not None:
    ALL_TEMPORAL_AGENTS.append(t_handoff)
if t_adversary is not None:
    ALL_TEMPORAL_AGENTS.append(t_adversary)
