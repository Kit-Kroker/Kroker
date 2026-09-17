"""Record the graph wire fixtures the dashboard mock replays (E-76 spec §6.3).

    python scripts/dump_graph_fixtures.py

The mock is a recording, not a simulator (spec D4): every catalog, parse and
serialize answer it gives was produced here by the real sdlc.graph code, and
tests/test_graph_fixtures_fresh.py fails when the committed JSON no longer
equals what build() produces. The two *.provisional.json files beside them
are hand-written until E-73/E-74 exist and are not touched by this script.

`run_state/*.recorded.json` (E-75) are exports of the FINAL run-graph/
run-state/validate projections, recorded from router steps over the shipped
default graph. No frontend code reads them yet; the canvas follow-up swaps
them in with the TS mirror.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datetime import UTC, datetime  # noqa: E402

from sdlc.core.models import PipelineConfig  # noqa: E402
from sdlc.dashboard import graph_wire  # noqa: E402
from sdlc.graph import (  # noqa: E402
    NODE_TYPES,
    ActivationFacts,
    Emitted,
    GraphRouter,
    GraphRunView,
    PendingFact,
    UnroutedFailure,
    from_yaml,
    validate,
)
from sdlc.workflows.graph_catalog import SHIPPED, executable, resolved_roles  # noqa: E402

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)

OUT = ROOT / "interfaces/dashboard/frontend/src/api/__fixtures__/graph"
PRE_CODE = ROOT / "tests/graph/fixtures/pre_code.graph.yaml"

_POS = "  position:\n    x: {x}\n    y: 0.0\n"

SCENARIOS: dict[str, str] = {
    "pre_code": PRE_CODE.read_text(encoding="utf-8"),
    "dangling_edge": (
        "schema_version: 1\nnodes:\n- id: intake\n  type: intake\n"
        + _POS.format(x="0.0")
        + "edges:\n- source: intake\n  source_port: ok\n  target: ghost\n  target_port: trigger\n"
    ),
    "duplicate_node_id": (
        "schema_version: 1\nnodes:\n"
        "- id: intake\n  type: intake\n" + _POS.format(x="0.0") + "- id: intake\n  type: intake\n"
        "  position:\n    x: 200.0\n    y: 0.0\n"
        "edges: []\n"
    ),
    "incompatible_ports": (
        "schema_version: 1\nnodes:\n"
        "- id: architect\n  type: architect\n" + _POS.format(x="200.0") + "- id: intake\n"
        "  type: intake\n" + _POS.format(x="0.0") + "edges:\n- source: intake\n  source_port: ok\n"
        "  target: architect\n  target_port: requirements\n"
    ),
    "bad_yaml": "schema_version: 1\nnodes: [\n",
    "bad_schema_version": "schema_version: 2\nnodes: []\nedges: []\n",
    "role_typo": (
        "schema_version: 1\nnodes:\n- id: architect\n  type: architect\n  role:\n    modle: x\n"
        "edges: []\n"
    ),
    "duplicate_top_level_key": "schema_version: 1\nnodes: []\nnodes: []\nedges: []\n",
}


def _node(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(n for n in graph["nodes"] if n["id"] == node_id)


def _set_gate_policy(graph: dict[str, Any], node_id: str, policy: str) -> dict[str, Any]:
    """What schema_form emits for one touched field (SCHEMA_FORM-4)."""
    out = copy.deepcopy(graph)
    node = _node(out, node_id)
    node["gate"] = {**node.get("gate", {}), "policy": policy}
    return out


def _rename(graph: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    """The inspector's id-rename cascade (spec §8.3): the node and every
    incident edge endpoint, in place, no reordering."""
    out = copy.deepcopy(graph)
    _node(out, old)["id"] = new
    for edge in out["edges"]:
        if edge["source"] == old:
            edge["source"] = new
        if edge["target"] == old:
            edge["target"] = new
    return out


def _objects(pre_code: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "pre_code_architecture_soft": _set_gate_policy(pre_code, "architecture", "soft"),
        "pre_code_intake_renamed_invalid": _rename(pre_code, "intake", "Intake"),
    }


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json")


def _run_state() -> dict[str, Any]:
    g = SHIPPED["default"]
    roles = resolved_roles(PipelineConfig())
    topology = validate(g, NODE_TYPES, roles=roles).topology
    assert topology is not None
    router = GraphRouter(topology)

    def emit(state, aid, port):
        return router.advance(
            state, Emitted(activation_id=aid, port=port, payload_ref=f"{aid}.{port}")
        ).state

    s = router.start().state
    s = emit(s, "intake#1", "ok")
    s = emit(s, "clarify#1", "requirements")
    at_gate = emit(s, "architect#1", "spec")
    assert at_gate.nodes["architecture"].status == "running"
    facts = {
        "intake#1": ActivationFacts(started_at=AT, ended_at=AT),
        "clarify#1": ActivationFacts(started_at=AT, ended_at=AT, cost_usd=0.31),
        "architect#1": ActivationFacts(started_at=AT, ended_at=AT, cost_usd=1.87),
        "architecture#1": ActivationFacts(started_at=AT),
    }
    blocked = GraphRunView(
        graph_sha=g.content_sha(),
        state=at_gate,
        activations=facts,
        pending=(PendingFact(key="architecture#1", activation_id="architecture#1", kind="gate"),),
    )
    rejected = GraphRunView(
        graph_sha=g.content_sha(),
        state=emit(at_gate, "architecture#1", "reject"),
        activations={**facts, "architecture#1": ActivationFacts(started_at=AT, ended_at=AT)},
        result="rejected:architecture",
    )
    done = at_gate
    for aid, port in (
        ("architecture#1", "approve"),
        ("planner#1", "plan"),
        ("plan#1", "approve"),
        ("plan_check#1", "ok"),
        ("code#1", "results"),
        ("analyze#1", "analysis"),
        ("merge#1", "pr"),
        ("deploy#1", "done"),
    ):
        done = emit(done, aid, port)
    assert done.outcome == "completed"
    completed = GraphRunView(
        graph_sha=g.content_sha(),
        state=done,
        activations={
            aid: ActivationFacts(started_at=AT, ended_at=AT)
            for aid in sorted({e.activation_id for e in done.emissions})
        },
        result="deployed:https://example.invalid/pr/1",
    )
    looping = at_gate
    for aid, port in (
        ("architecture#1", "revise"),
        ("architect#2", "spec"),
        ("architecture#2", "revise"),
        ("architect#3", "spec"),
    ):
        looping = emit(looping, aid, port)
    exhausted = emit(looping, "architecture#3", "revise")
    assert exhausted.outcome == "escalated"
    escalated = GraphRunView(
        graph_sha=g.content_sha(), state=exhausted, escalated_by="architecture#3"
    )
    failed = GraphRunView(
        graph_sha=g.content_sha(),
        state=emit(router.start().state, "intake#1", "fail"),
        activations={"intake#1": ActivationFacts(started_at=AT, ended_at=AT)},
        unrouted_failure=UnroutedFailure(activation_id="intake#1", error_type="ApplicationError"),
    )
    cases = {
        "not_started": (None, False, None),
        "blocked_at_architecture": (blocked, False, None),
        "rejected_at_architecture": (rejected, True, "completed"),
        "completed": (completed, True, "completed"),
        "escalated_revise_exhausted": (escalated, True, "completed"),
        "unrouted_fail": (failed, True, "failed"),
        "interrupted": (blocked, True, "terminated"),
    }
    states = {
        name: _dump(
            graph_wire.project_graph_state(
                view, g, topology, execution_closed=closed, close_status=status
            )
        )
        for name, (view, closed, status) in sorted(cases.items())
    }
    pre_code = from_yaml(PRE_CODE.read_text(encoding="utf-8"))
    validation = graph_wire.with_executable(
        graph_wire.validation(pre_code, roles=roles), executable(pre_code)
    )
    return {
        "run_state/graph_response.recorded.json": _dump(graph_wire.graph_response(g)),
        "run_state/graph_state.recorded.json": states,
        "run_state/validation.recorded.json": _dump(validation),
    }


def build() -> dict[str, Any]:
    """Relative path under OUT -> JSON-ready object."""
    files: dict[str, Any] = {"catalog.json": _dump(graph_wire.catalog())}
    pre_code_graph: dict[str, Any] | None = None
    for name in sorted(SCENARIOS):
        text = SCENARIOS[name]
        parsed = graph_wire.parse_text(text)
        serialized = (
            _dump(graph_wire.serialize(parsed.graph))
            if isinstance(parsed, graph_wire.ParseOk)
            else None
        )
        if name == "pre_code":
            assert isinstance(parsed, graph_wire.ParseOk)
            pre_code_graph = parsed.graph
        files[f"scenarios/{name}.json"] = {
            "name": name,
            "yaml": text,
            "parse": _dump(parsed),
            "serialize": serialized,
        }
    assert pre_code_graph is not None
    for name, graph in sorted(_objects(pre_code_graph).items()):
        files[f"objects/{name}.json"] = {
            "name": name,
            "base": "pre_code",  # the scenario whose canned validation applies
            "graph": graph,
            "parse": _dump(graph_wire.parse_object(graph)),
        }
    files.update(_run_state())
    return files


def main() -> None:
    for rel, obj in build().items():
        path = OUT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
