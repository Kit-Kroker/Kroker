"""E-72 graph identity: content_sha() over the canonical form (spec §7.1)."""

from __future__ import annotations

import copy
import itertools
from pathlib import Path

import pytest

from sdlc.graph import PipelineGraph, canonical_json, from_yaml

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"

# Pinned on purpose: ANY change to the canonical form (field set, exclusion
# rules, sort order, JSON separators) re-shas every stored graph. If this
# fails, that is a schema decision (spec §7.3), not a test to update blindly.
GOLDEN_SHA = "9bc61539a897be2744030e2d1147ce5083dcb776b7d6f97fe273281527009fa1"

SMALL = {
    "schema_version": 1,
    "nodes": [
        {"id": "architect", "type": "architect", "role": {"kind": "proposer", "model": "m1"}},
        {"id": "architecture", "type": "gate.architecture", "gate": {"policy": "hard"}},
        {"id": "planner", "type": "plan", "position": {"x": 3, "y": 4}},
        {"id": "plan", "type": "gate.plan", "label": "Plan gate"},
    ],
    "edges": [
        {
            "source": "architect",
            "source_port": "spec",
            "target": "architecture",
            "target_port": "artifact",
        },
        {
            "source": "architecture",
            "source_port": "approve",
            "target": "planner",
            "target_port": "spec",
        },
        {
            "source": "architecture",
            "source_port": "revise",
            "target": "architect",
            "target_port": "guidance",
            "max_traversals": 2,
        },
        {
            "source": "planner",
            "source_port": "plan",
            "target": "plan",
            "target_port": "artifact",
            "label": "x",
        },
    ],
}


def _small(mutate=None) -> PipelineGraph:
    data = copy.deepcopy(SMALL)
    if mutate is not None:
        mutate(data)
    return PipelineGraph.model_validate(data)


def test_golden_sha_for_fixture():
    assert from_yaml(FIXTURE.read_text(encoding="utf-8")).content_sha() == GOLDEN_SHA


def test_sha_is_sha256_hex_of_canonical_json():
    import hashlib

    graph = _small()
    assert graph.content_sha() == hashlib.sha256(canonical_json(graph).encode()).hexdigest()


def test_canonical_json_is_compact_sorted_and_cosmetic_free():
    text = canonical_json(_small())
    assert " " not in text.replace("Plan gate", "")
    assert '"position"' not in text and '"label"' not in text
    assert text.index('"edges"') < text.index('"nodes"') < text.index('"schema_version"')


def test_sha_is_order_independent():
    """NFR-10, per-module pattern: byte-identical across input order."""
    expected_json = canonical_json(_small())
    expected_sha = _small().content_sha()
    for ns in itertools.permutations(SMALL["nodes"]):
        for es in itertools.permutations(SMALL["edges"]):
            graph = PipelineGraph.model_validate(
                {"schema_version": 1, "nodes": list(ns), "edges": list(es)}
            )
            assert canonical_json(graph) == expected_json
            assert graph.content_sha() == expected_sha


def _set_position(d):
    d["nodes"][0]["position"] = {"x": 999, "y": -1}


def _move_position(d):
    d["nodes"][2]["position"] = {"x": 0, "y": 0}


def _drop_position(d):
    del d["nodes"][2]["position"]


def _relabel_node(d):
    d["nodes"][3]["label"] = "Renamed"


def _label_edge(d):
    d["edges"][0]["label"] = "tidy"


@pytest.mark.parametrize(
    "cosmetic", [_set_position, _move_position, _drop_position, _relabel_node, _label_edge]
)
def test_cosmetics_never_change_sha(cosmetic):
    assert _small(cosmetic).content_sha() == _small().content_sha()


def _role_model(d):
    d["nodes"][0]["role"]["model"] = "m2"


def _gate_policy(d):
    d["nodes"][1]["gate"]["policy"] = "soft"


def _max_traversals(d):
    d["edges"][2]["max_traversals"] = 3


def _node_type(d):
    d["nodes"][2]["type"] = "architect"


def _edge_target(d):
    d["edges"][1]["target_port"] = "requirements"


def _drop_role(d):
    del d["nodes"][0]["role"]


def _empty_role(d):
    d["nodes"][2]["role"] = {}


@pytest.mark.parametrize(
    "edit",
    [_role_model, _gate_policy, _max_traversals, _node_type, _edge_target, _drop_role, _empty_role],
)
def test_semantic_edits_change_sha(edit):
    assert _small(edit).content_sha() != _small().content_sha()


def test_explicit_default_hashes_like_omitted():
    """`gate: {policy: hard}` and `gate: {}` mean the same -> one sha."""

    def omit_policy(d):
        d["nodes"][1]["gate"] = {}

    def explicit_threshold(d):
        d["nodes"][1]["gate"]["threshold"] = 0.8

    assert _small(omit_policy).content_sha() == _small().content_sha()
    assert _small(explicit_threshold).content_sha() == _small().content_sha()


def test_extra_args_order_is_meaningful():
    def args(order):
        def mutate(d):
            d["nodes"][0]["role"]["extra_args"] = order

        return mutate

    assert _small(args(["-a", "-b"])).content_sha() != _small(args(["-b", "-a"])).content_sha()


# --- E-77 T008 (RED): PipelineGraph.document_sha (FR-019 layout identity) ---
# document_sha() hashes the canonical JSON WITH cosmetics (data-model.md);
# content_sha() keeps hashing the cosmetic-free form. Reuses the mutators
# above on purpose: one fixture, two identities over it.


def test_document_sha_is_order_independent():
    """Layout identity inherits NFR-10: same graph, reordered lists, one sha."""
    expected = _small().document_sha()
    shuffles = [
        (list(reversed(SMALL["nodes"])), list(reversed(SMALL["edges"]))),
        (SMALL["nodes"][2:] + SMALL["nodes"][:2], SMALL["edges"][1:] + SMALL["edges"][:1]),
    ]
    for nodes, edges in shuffles:
        g = PipelineGraph.model_validate({"schema_version": 1, "nodes": nodes, "edges": edges})
        assert g.content_sha() == _small().content_sha()  # the shuffle changed nothing semantic
        assert g.document_sha() == expected


@pytest.mark.parametrize(
    "cosmetic", [_set_position, _move_position, _drop_position, _relabel_node, _label_edge]
)
def test_cosmetics_change_document_sha_but_not_content_sha(cosmetic):
    """FR-019 vs FR-1201: positions/labels are layout identity, not content."""
    base = _small()
    edited = _small(cosmetic)
    assert edited.content_sha() == base.content_sha()
    assert edited.document_sha() != base.document_sha()


def test_document_sha_is_deterministic_64_lowercase_hex():
    """Same shape contract as content_sha: 64 lowercase hex, stable across
    repeated calls and independent builds of the same graph."""
    import re

    g = _small()
    assert re.fullmatch(r"[0-9a-f]{64}", g.document_sha())
    assert g.document_sha() == g.document_sha()
    assert _small().document_sha() == g.document_sha()
