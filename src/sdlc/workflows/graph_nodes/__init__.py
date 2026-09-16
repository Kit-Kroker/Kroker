"""Graph node handlers (E-74 spec §6). HANDLERS binds node types to handlers;
worker boot asserts set(NODE_TYPES) == set(HANDLERS) | set(NOT_EXECUTABLE)."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from .base import Handler
from .gate import gate_node
from .postplan import (
    analyze_node,
    code_node,
    deploy_node,
    merge_node,
    plan_check_node,
    seed_plan_node,
    seed_spec_node,
)
from .precode import (
    architect_node,
    clarify_node,
    context_node,
    intake_node,
    plan_node,
    research_node,
)

HANDLERS: Mapping[str, Handler] = MappingProxyType(
    {
        "analyze": analyze_node,
        "architect": architect_node,
        "clarify": clarify_node,
        "code": code_node,
        "context": context_node,
        "deploy": deploy_node,
        "gate.architecture": gate_node,
        "gate.plan": gate_node,
        "intake": intake_node,
        "merge": merge_node,
        "plan": plan_node,
        "plan_check": plan_check_node,
        "research": research_node,
        "seed.plan": seed_plan_node,
        "seed.spec": seed_spec_node,
    }
)

__all__ = ["HANDLERS"]
