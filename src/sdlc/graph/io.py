"""YAML storage shape for `graphs/<sha>.yaml` (E-72, spec §7.2).

Serialize/deserialize only -- writing, reading and lookup of the store are
E-75/E-77. `from_yaml` raises exactly one exception type, GraphSchemaError,
for every way text fails to become a graph: one catch contract for E-75/E-76.

Graph text is stricter than YAML (E-76 spec D10): anchors, aliases and `<<`
merge keys are rejected, and so is a duplicate key in any mapping --
`yaml.safe_load` would keep the last one silently.
"""

from __future__ import annotations

import yaml

from .model import PipelineGraph

_SCHEMA_VERSION = 1
_MERGE_TAG = "tag:yaml.org,2002:merge"


class GraphSchemaError(ValueError):
    """Graph text is not a well-shaped PipelineGraph (bad YAML, not a
    mapping, unsupported schema_version, or a model shape failure).
    Legality of a well-shaped graph is validate.py's (E-73), not this."""


class _StrictLoader(yaml.SafeLoader):
    """MUST stay a yaml.SafeLoader subclass: it inherits only the safe
    constructors, which is what makes yaml.load(..., Loader=_StrictLoader)
    safe. Never register these overrides on yaml.SafeLoader itself -- that
    would change every safe_load in the process."""

    def compose_node(self, parent, index):  # type: ignore[no-untyped-def]
        # Reject at COMPOSE time: by construct time an alias graph exists.
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise yaml.composer.ComposerError(
                None, None, "aliases are not allowed in graph text", event.start_mark
            )
        event = self.peek_event()
        if getattr(event, "anchor", None) is not None:
            raise yaml.composer.ComposerError(
                None, None, "anchors are not allowed in graph text", event.start_mark
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):  # type: ignore[no-untyped-def]
        seen: set[object] = set()
        for key_node, _ in node.value:
            if key_node.tag == _MERGE_TAG:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "merge keys (<<) are not allowed in graph text",
                    key_node.start_mark,
                )
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def to_yaml(graph: PipelineGraph) -> str:
    """Deterministic: model field order, normalized node/edge order,
    exclude_defaults. Cosmetics are INCLUDED -- the canvas needs them."""
    return yaml.safe_dump(
        graph.model_dump(mode="json", exclude_defaults=True),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def from_yaml(text: str) -> PipelineGraph:
    try:
        data = yaml.load(text, Loader=_StrictLoader)  # noqa: S506 -- a SafeLoader subclass
    except yaml.YAMLError as exc:
        raise GraphSchemaError(f"graph text is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise GraphSchemaError(f"graph document must be a mapping, got {type(data).__name__}")
    version = data.get("schema_version")
    # type() not isinstance(): bool is an int subclass, and `true` is not 1.
    if type(version) is not int or version != _SCHEMA_VERSION:
        raise GraphSchemaError(
            f"unsupported graph schema_version {version!r}; this worker reads {_SCHEMA_VERSION}"
        )
    try:
        return PipelineGraph.model_validate(data)
    except ValueError as exc:  # pydantic.ValidationError is a ValueError
        raise GraphSchemaError(f"graph does not match the schema: {exc}") from exc
