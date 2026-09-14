"""E-73 topology algorithms (spec §4-§5): pure, registry-free, sorted."""

from __future__ import annotations

import itertools

from sdlc.graph.model import GraphEdge
from sdlc.graph.topology import (
    edge_id,
    edge_key,
    forward_adjacency,
    forward_cycles,
    forward_reach,
    is_back_edge,
)


def _e(source: str, target: str, bound: int | None = None, sp: str = "out", tp: str = "in"):
    return GraphEdge(
        source=source, source_port=sp, target=target, target_port=tp, max_traversals=bound
    )


def test_edge_id_and_key():
    e = _e("plan", "planner", 2, sp="revise", tp="guidance")
    assert edge_id(e) == "plan.revise->planner.guidance"
    assert edge_key(e) == ("plan", "revise", "planner", "guidance")
    assert is_back_edge(e)
    assert not is_back_edge(_e("a", "b"))


def test_edge_id_string_order_equals_endpoint_tuple_order():
    names = ["a", "a1", "a_b", "ab", "b", "z9"]
    edges = [
        _e(s, t, sp=sp, tp=tp)
        for s, sp, t, tp in itertools.product(names, ["x", "x_y", "xy"], names[:3], ["p", "p_q"])
    ]
    assert sorted(edges, key=edge_id) == sorted(edges, key=edge_key)


def test_forward_adjacency_ignores_bounded_and_dangling_edges():
    edges = [_e("a", "b"), _e("a", "b", sp="other"), _e("b", "a", 2), _e("a", "ghost")]
    assert forward_adjacency(["b", "a"], edges) == {"a": ("b",), "b": ()}


def test_forward_reach_includes_start_and_is_sorted():
    adj = {"e": ("c", "a"), "a": ("d",), "c": (), "d": (), "x": ("e",)}
    assert forward_reach(adj, "e") == ("a", "c", "d", "e")
    assert forward_reach(adj, "d") == ("d",)


def test_forward_cycles_on_a_dag_is_empty():
    assert forward_cycles({"a": ("b", "c"), "b": ("c",), "c": ()}) == ()


def test_forward_cycles_reports_each_scc_once_sorted():
    adj = {
        "a": ("b",),
        "b": ("c",),
        "c": ("a", "d"),  # {a, b, c}
        "d": ("e",),
        "e": ("d",),  # {d, e}
        "f": ("f",),  # self edge
        "g": (),
    }
    assert forward_cycles(adj) == (("a", "b", "c"), ("d", "e"), ("f",))


def test_forward_cycles_is_independent_of_mapping_order():
    adj = {"a": ("b",), "b": ("a", "c"), "c": ("d",), "d": ("c",)}
    expected = forward_cycles(adj)
    for order in itertools.permutations(adj):
        assert forward_cycles({k: adj[k] for k in order}) == expected


def test_bounded_loop_is_not_a_forward_cycle():
    edges = [_e("a", "b"), _e("b", "a", 2)]
    assert forward_cycles(forward_adjacency(["a", "b"], edges)) == ()
