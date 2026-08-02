"""An httpx transport that validates requests against Hindsight's real
OpenAPI schema rather than against the caller's assumptions.

The client this replaces was tested with mocks whose handlers asserted
``request.url.path == <the path the client itself chose>``, so the suite could
only ever confirm the client agreed with itself. Here the schema is the
authority: an undefined path, an undefined method, a malformed request body,
or a canned response that does not match the documented response shape all
fail."""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from jsonschema import Draft202012Validator

from sdlc.memory.hindsight_api import SCHEMA_PATH


class ContractViolation(AssertionError):
    pass


_DOC: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _regex(template: str) -> re.Pattern:
    parts = re.split(r"(\{[^}]+\})", template)
    body = "".join(r"[^/]+" if p.startswith("{") else re.escape(p)
                   for p in parts)
    return re.compile("^" + body + "$")


def _match_path(path: str) -> str:
    """Resolve a concrete request path to its schema template. Literal
    segments win over placeholders so /memories/list is not swallowed by
    /memories/{id}."""
    candidates = [t for t in _DOC["paths"] if _regex(t).match(path)]
    if not candidates:
        raise ContractViolation(
            f"{path} is no path in the Hindsight OpenAPI schema")
    return min(candidates, key=lambda t: t.count("{"))


def _json_schema(node: Any) -> Any:
    """OpenAPI content -> the JSON Schema for application/json, or None."""
    if not node:
        return None
    return node.get("content", {}).get("application/json", {}).get("schema")


def _deref(node: Any, _seen: frozenset[str] = frozenset()) -> Any:
    """Resolve every local ``$ref`` against the full document so the
    validator sees a self-contained schema.

    Passing a fragment straight to ``Draft202012Validator(schema=fragment,
    registry=...)`` should work with :mod:`referencing`, but jsonschema's
    dynamic-scope handling shadows the registered root resource with the
    fragment itself, so ``$ref`` resolution lands inside the fragment (which
    has no ``components``) instead of the document. Pre-resolution sidesteps
    that entirely and is correct for OpenAPI's local-only refs."""
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if ref in _seen:
                return {}
            target: Any = _DOC
            for part in ref.lstrip("#/").split("/"):
                target = target[part]
            base = _deref(target, _seen | {ref})
            if len(node) == 1:
                return base
            merged = dict(base)
            merged.update({k: _deref(v, _seen | {ref})
                           for k, v in node.items() if k != "$ref"})
            return merged
        return {k: _deref(v, _seen) for k, v in node.items()}
    if isinstance(node, list):
        return [_deref(v, _seen) for v in node]
    return node


def _validate(schema: Any, instance: Any, label: str) -> None:
    if schema is None:
        return
    errors = sorted(Draft202012Validator(_deref(schema))
                    .iter_errors(instance), key=lambda e: e.path)
    if errors:
        first = errors[0]
        raise ContractViolation(
            f"{label} violates the Hindsight schema at "
            f"{'/'.join(str(p) for p in first.path) or '<root>'}: "
            f"{first.message}")


class ContractTransport(httpx.MockTransport):
    """``responses`` maps (METHOD, path_template) -> the JSON body to return.

    Keys use the templates from :mod:`sdlc.memory.hindsight_api` (e.g.
    ``("POST", RECALL_PATH)``), not concrete paths; the handler resolves the
    concrete request path to its template before lookup so a test does not
    have to repeat the tenant/bank substitution."""

    def __init__(self, responses: dict[tuple[str, str], Any]):
        self._responses = responses
        self.requests: list[httpx.Request] = []
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        template = _match_path(request.url.path)
        method = request.method.lower()
        operation = _DOC["paths"][template].get(method)
        if operation is None:
            raise ContractViolation(
                f"{request.method} is not served on {template}; "
                f"schema allows {sorted(_DOC['paths'][template])}")

        if request.content:
            try:
                body = json.loads(request.content)
            except json.JSONDecodeError as exc:
                raise ContractViolation(
                    f"request body to {template} is not JSON: {exc}") from exc
            _validate(_json_schema(operation.get("requestBody")), body,
                      f"request body to {request.method} {template}")

        # Response lookup: keys use hindsight_api's templates ({tenant}/{bank}),
        # but the schema serves literal `default`/{bank_id}, so equality on the
        # resolved schema template misses. Match the concrete path against the
        # response keys' templates structurally — the same regex _match_path
        # uses, applied to the response map instead of the schema's paths.
        matches = [(m, t) for (m, t) in self._responses
                   if m == request.method.upper()
                   and _regex(t).match(request.url.path)]
        if not matches:
            raise ContractViolation(
                f"test supplied no canned response for "
                f"{request.method} {request.url.path}; "
                f"available: {sorted(self._responses)}")
        _, resp_template = min(matches, key=lambda mt: mt[1].count("{"))
        payload = self._responses[(request.method.upper(), resp_template)]

        ok = (operation.get("responses", {}).get("200")
              or operation.get("responses", {}).get("201") or {})
        _validate(_json_schema(ok), payload,
                  f"canned response for {request.method} {template}")
        return httpx.Response(200, json=payload)
