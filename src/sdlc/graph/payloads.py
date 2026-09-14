"""The payload allowlist (E-72, spec §6.2).

Port payloads are model NAMES; this table maps each name to
"module.path:ClassName". Strings, not imports: resolving them here would pull
stage slices (and the benchmarks <-> stages cycle) into sdlc.graph's import
closure. check_node_types() resolves them lazily.

A port names the class its CONSUMER needs, living in a models module -- hence
ResearchBrief, not the ResearchOutcome subclass defined in research/step.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

PAYLOAD_TYPES: Mapping[str, str] = MappingProxyType(
    {
        "ArchitectureSpec": "sdlc.stages.architecture.models:ArchitectureSpec",
        "ClarifiedRequirements": "sdlc.stages.clarify.models:ClarifiedRequirements",
        "CodebaseMap": "sdlc.context.models:CodebaseMap",
        "GateDecision": "sdlc.core.models:GateDecision",
        "ImplementationPlan": "sdlc.stages.plan.models:ImplementationPlan",
        "ResearchBrief": "sdlc.stages.research.models:ResearchBrief",
    }
)
