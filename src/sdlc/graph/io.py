"""YAML storage shape for `graphs/<sha>.yaml` (E-72, spec §7.2).

Serialize/deserialize only -- writing, reading and lookup of the store are
E-75/E-77. `from_yaml` raises exactly one exception type, GraphSchemaError,
for every way text fails to become a graph: one catch contract for E-75/E-76.
"""

from __future__ import annotations

import yaml

from .model import PipelineGraph

_SCHEMA_VERSION = 1


class GraphSchemaError(ValueError):
    """Graph text is not a well-shaped PipelineGraph (bad YAML, not a
    mapping, unsupported schema_version, or a model shape failure).
    Legality of a well-shaped graph is validate.py's (E-73), not this."""


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
        data = yaml.safe_load(text)
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
