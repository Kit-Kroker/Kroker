"""E-73 NFR-10 determinism (spec §8): hash-seed independence of the report
and of a router state sequence, and order independence of validate() under
permuted registry / roles insertion order and permuted port declarations."""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType

import sdlc.graph
from sdlc.graph.validate import validate
from tests.graph.fixtures.registries import GENERIC, edge, graph, node, roles

REPO = Path(sdlc.graph.__file__).parents[3]

# Validates a graph with many problems, then drives nested loops until at
# least two activations are live and two ids are retired, printing every JSON.
_SCRIPT = "\n".join(
    [
        "from sdlc.graph.router import Emitted, GraphRouter",
        "from sdlc.graph.validate import validate",
        "from tests.graph.fixtures.registries import GENERIC, edge, graph, node, roles",
        "from tests.graph.fixtures.routing import nested_loops_graph",
        "bad = graph([node('start', 'start'), node('x', 'nope'), node('merge', 'gate.art'),",
        "    node('b', 'builder', role={}), node('a', 'work'), node('c', 'sink')],",
        "    [edge('ghost.ok', 'x.in'), edge('a.out', 'c.art'), edge('c.done', 'a.trigger')])",
        "print(validate(bad, GENERIC, roles=roles()).model_dump_json())",
        "report = validate(nested_loops_graph(), GENERIC, roles=roles())",
        "router = GraphRouter(report.topology)",
        "step = router.start()",
        "script = [('start#1', 'ok'), ('a#1', 'out'), ('r#1', 'out'), ('gr#1', 'revise'),",
        "    ('ga#1', 'revise'), ('r#2', 'out'), ('a#2', 'out'), ('ga#2', 'reject')]",
        "for aid, port in script:",
        "    event = Emitted(activation_id=aid, port=port, payload_ref=aid)",
        "    step = router.advance(step.state, event)",
        "    print(step.model_dump_json())",
    ]
)


def _run_with_seed(seed: str) -> str:
    env = {
        **os.environ,
        "PYTHONHASHSEED": seed,
        "PYTHONPATH": os.pathsep.join(
            [str(REPO / "src"), str(REPO), os.environ.get("PYTHONPATH", "")]
        ),
    }
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        check=True,
        cwd=REPO,
    )
    return proc.stdout


def test_report_and_router_json_are_hash_seed_independent():
    outputs = [_run_with_seed(seed) for seed in ("0", "1", "4242")]
    assert outputs[0] == outputs[1] == outputs[2]
    lines = outputs[0].splitlines()
    report = json.loads(lines[0])
    assert "unknown_node_type" in {p["code"] for p in report["problems"]}
    # The script really exercises the set-backed fields (skeptic F8).
    states = [json.loads(line)["state"] for line in lines[1:]]
    assert max(len(s["live"]) for s in states) >= 2
    assert max(len(s["retired"]) for s in states) >= 2


def _bad_graph():
    return graph(
        [
            node("start", "start"),
            node("x", "nope"),
            node("merge", "gate.art"),
            node("b", "builder", role={}),
            node("a", "work"),
            node("c", "sink"),
            node("br", "brancher"),
            node("m", "sink"),
        ],
        [
            edge("ghost.ok", "x.in"),
            edge("a.out", "c.art"),
            edge("c.done", "a.trigger"),
            edge("start.ok", "br.trigger"),
            edge("br.left", "m.art"),
            edge("br.right", "m.art"),
        ],
    )


def test_report_is_independent_of_registry_and_roles_insertion_order():
    g = _bad_graph()
    baseline = validate(g, GENERIC, roles=roles())
    specs = list(GENERIC.values())
    role_items = list(roles().items())
    for k in range(6):
        shuffled_specs = specs[k:] + specs[:k]
        shuffled_roles = dict(role_items[k:] + role_items[:k])
        report = validate(
            g, MappingProxyType({s.type: s for s in shuffled_specs}), roles=shuffled_roles
        )
        assert report == baseline


def test_report_and_topology_are_independent_of_port_declaration_order():
    clean = graph(
        [node("start", "start"), node("br", "brancher"), node("m", "sink"), node("g", "gate.art")],
        [
            edge("start.ok", "br.trigger"),
            edge("br.left", "m.art"),
            edge("br.right", "g.artifact"),
        ],
    )
    for g in (clean, _bad_graph()):
        baseline = validate(g, GENERIC, roles=roles())
        for type_ in ("brancher", "gate.art"):
            spec = GENERIC[type_]
            for ports in itertools.permutations(spec.ports):
                permuted = MappingProxyType(
                    {**GENERIC, type_: spec.model_copy(update={"ports": ports})}
                )
                assert validate(g, permuted, roles=roles()) == baseline
                if baseline.topology is not None:
                    assert validate(g, permuted, roles=roles()).topology == baseline.topology
