"""E-76 D10: graph text rejects duplicate keys, anchors, aliases and merges."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sdlc.graph import GraphSchemaError, from_yaml, to_yaml

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


@pytest.mark.parametrize(
    "text",
    [
        "schema_version: 1\nnodes: []\nnodes: []\nedges: []\n",
        "schema_version: 1\nnodes:\n- id: a\n  type: intake\n  role:\n    model: x\n    model: y\n"
        "edges: []\n",
        "schema_version: 1\nnodes: []\nedges:\n- source: a\n  source: b\n  source_port: ok\n"
        "  target: c\n  target_port: trigger\n",
        "schema_version: 1\nnodes: []\nedges: [{source: a, source: b}]\n",
    ],
    ids=["top_level", "inside_role", "inside_edge_item", "flow_mapping"],
)
def test_duplicate_key_is_rejected_at_every_level(text):
    with pytest.raises(GraphSchemaError, match="duplicate key") as info:
        from_yaml(text)
    assert isinstance(info.value.__cause__, yaml.constructor.ConstructorError)


def test_alias_is_rejected_in_the_composer():
    text = "schema_version: 1\nnodes: &n []\nedges: *n\n"
    with pytest.raises(GraphSchemaError, match="anchors are not allowed") as info:
        from_yaml(text)
    assert isinstance(info.value.__cause__, yaml.composer.ComposerError)


def test_bare_alias_is_rejected_in_the_composer():
    # An alias with an unknown anchor still fails as an alias, not a lookup.
    with pytest.raises(GraphSchemaError, match="aliases are not allowed") as info:
        from_yaml("schema_version: 1\nnodes: *missing\nedges: []\n")
    assert isinstance(info.value.__cause__, yaml.composer.ComposerError)


def test_nested_alias_bomb_fails_fast():
    lines = ["a0: &a0 [x, x, x, x, x, x, x, x, x]"]
    lines += [f"a{i}: &a{i} [" + ", ".join([f"*a{i - 1}"] * 9) + "]" for i in range(1, 9)]
    with pytest.raises(GraphSchemaError, match="anchors are not allowed"):
        from_yaml("\n".join(lines) + "\n")


def test_merge_key_is_rejected():
    text = "schema_version: 1\nnodes: []\nedges:\n- <<: {source: a}\n  source_port: ok\n"
    with pytest.raises(GraphSchemaError, match="merge keys"):
        from_yaml(text)


def test_python_object_tag_is_still_rejected():
    with pytest.raises(GraphSchemaError) as info:
        from_yaml("!!python/object:os.system {}\n")
    assert isinstance(info.value.__cause__, yaml.YAMLError)


def test_yaml_error_mark_survives_on_the_cause():
    with pytest.raises(GraphSchemaError) as info:
        from_yaml("schema_version: 1\nnodes: []\nnodes: []\nedges: []\n")
    mark = info.value.__cause__.problem_mark
    assert (mark.line, mark.column) == (2, 0)


def test_the_fixture_still_round_trips():
    text = FIXTURE.read_text(encoding="utf-8")
    assert to_yaml(from_yaml(text)) == text


def test_the_strict_loader_leaves_safe_load_untouched():
    assert yaml.safe_load("a: 1\na: 2\n") == {"a": 2}
