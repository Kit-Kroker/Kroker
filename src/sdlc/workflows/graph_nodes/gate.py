"""The generic gate handler (E-74 spec §6.1): _revisable_stage as topology.

In-loop rounds (revise available) read calibration only under the verbatim
predicate of role_host.py:245-249 and pass confidence; the final round
(revise unavailable) reads nothing, passes no confidence and no
auto_decision, and maps REVISE to reject (E-73 §6.5). Post-gate work runs
on approve/reject only; the board publish rides `finalize` so it lands
after the dispatcher's budget boundary (feature.py:588-591).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ...calibration.decision import auto_decision_for
    from ...core.models import GateConfig, GateOutcome, GatePolicy, PipelineConfig
    from ...graph.router import Activation
    from ...pending import GateContext
    from ...stages.architecture.step import finish as architecture_finish
    from ...stages.plan.step import finish as plan_finish
    from ..role_host import _spec_summary
    from .base import NodeContext, NodeResult


@dataclass(frozen=True)
class GateFinish:
    finish: Callable[..., Awaitable[None]]
    board_key: str
    sets_plan_version: bool


GATE_FINISH: Mapping[str, GateFinish] = MappingProxyType(
    {
        "gate.architecture": GateFinish(architecture_finish, "architecture", False),
        "gate.plan": GateFinish(plan_finish, "plan", True),
    }
)


async def gate_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    ref = act.inputs["artifact"]
    assert isinstance(ref, str)
    stored = nc.payload(ref)
    artifact: Any = stored.model
    author = stored.author_model or ""
    name = nc.node.id  # E-72 D7: gate identity is the node id
    confidence = getattr(artifact, "confidence", None)
    context = GateContext(spec_summary=_spec_summary(artifact))
    final = "revise" in act.unavailable_ports

    if not final:
        auto = None
        if confidence is not None and cfg.gates.get(name, GateConfig()).policy is GatePolicy.SOFT:
            calibration = await nc.host._calibration_verdict(cfg, name, author)
            auto = auto_decision_for(name, cfg, confidence, calibration)
        decision = await nc.ctx.gate(
            name,
            cfg.gate_settings(),
            auto_decision=auto,
            round=act.round,
            context=context,
            confidence=confidence,
            author_model=author,
        )
    else:
        decision = await nc.ctx.gate(
            name, cfg.gate_settings(), round=act.round, context=context, author_model=author
        )

    if decision.outcome is GateOutcome.REVISE and not final and nc.connected("revise"):
        return NodeResult(port="revise", payload=decision)

    approved = decision.outcome is GateOutcome.APPROVE
    port = "approve" if approved else "reject"
    fin = GATE_FINISH[nc.spec.type]
    producer_node = stored.producer.rpartition("#")[0]
    await fin.finish(
        nc.ctx, nc.carry(producer_node)["prep"], cfg=cfg, artifact=artifact, gate=decision
    )

    async def _publish() -> None:
        version = await nc.host._board_publish(
            cfg, fin.board_key, artifact.model_dump_json(), approved=decision.approved
        )
        if fin.sets_plan_version:
            nc.host._plan_version = version

    return NodeResult(
        port=port,
        payload=artifact if approved else None,
        author_model=author if approved else None,
        finalize=_publish,
    )
