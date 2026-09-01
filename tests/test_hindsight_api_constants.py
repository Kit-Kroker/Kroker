"""Asserts every pinned path exists in the vendored schema. This is what
stops the client drifting back to an invented API."""

from __future__ import annotations

import json
import re

import pytest

from sdlc.memory.hindsight_api import (
    BANK_PATH,
    CONSOLIDATE_PATH,
    OPERATION_PATH,
    RECALL_LIMIT_FIELD,
    RECALL_PATH,
    RETAIN_PATH,
    SCHEMA_PATH,
)


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _placeholder_agnostic(template: str) -> re.Pattern:
    """Our constants and the schema may name placeholders differently
    (``{bank}`` vs ``{bank_id}``), and the schema pins the tenant segment to
    the literal ``default`` where our constant carries ``{tenant}``. A
    placeholder in our template therefore matches any non-slash segment in the
    schema; literal segments still have to agree."""
    parts = re.split(r"(\{[^}]+\})", template)
    body = "".join(r"[^/]+" if p.startswith("{") else re.escape(p) for p in parts)
    return re.compile("^" + body + "$")


def _find(schema, template):
    pattern = _placeholder_agnostic(template)
    return [p for p in schema["paths"] if pattern.match(p)]


@pytest.mark.parametrize(
    "template,method",
    [
        (BANK_PATH, "put"),
        (RETAIN_PATH, "post"),
        (RECALL_PATH, "post"),
        (CONSOLIDATE_PATH, "post"),
        (OPERATION_PATH, "get"),
    ],
)
def test_pinned_path_exists_in_the_vendored_schema(schema, template, method):
    matches = _find(schema, template)
    assert matches, f"{template} is not a path in the vendored OpenAPI schema"
    assert any(method in schema["paths"][m] for m in matches), (
        f"{template} exists but serves no {method.upper()}"
    )


def test_recall_limit_field_is_a_real_request_property(schema):
    matches = _find(schema, RECALL_PATH)
    body = schema["paths"][matches[0]]["post"]["requestBody"]
    ref = body["content"]["application/json"]["schema"].get("$ref", "")
    name = ref.rsplit("/", 1)[-1]
    props = schema["components"]["schemas"][name]["properties"]
    assert RECALL_LIMIT_FIELD in props, (
        f"{RECALL_LIMIT_FIELD} is not a recall request property; available: {sorted(props)}"
    )
