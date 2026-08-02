# Real Hindsight Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fabricated `HindsightMemory` client with one written against Hindsight's actual REST API, verified by a contract test that validates every request against the container's own OpenAPI schema and by an opt-in live test that proves recall filters bite and the watermark cuts.

**Architecture:** `hindsight_client.py` is rewritten against paths pinned from the running container's `/openapi.json` (vendored to `tests/fixtures/`). The `Memory` protocol, `RecallSnapshot`, `RetainItem` and every `_recall`/`_retain` call site in `feature.py` are untouched — all change is behind the seam. Because Hindsight has no point-in-time read, the NFR-6 watermark becomes an ISO-8601 timestamp enforced client-side as a `mentioned_at` cutoff, with retain sending an explicit worker-clock timestamp so both sides of that comparison share a clock.

**Tech Stack:** Python 3.11, httpx (already a dependency), pydantic v2, temporalio, `jsonschema` (new **dev** dependency, contract test only).

**Spec:** `docs/superpowers/specs/2026-08-02-hindsight-real-integration-design.md`

## Global Constraints

- **No URL path is written as a literal in `src/` until Task 1 pins it from the container's schema.** All paths live in `src/sdlc/memory/hindsight_api.py` as named constants. This is the single most important constraint in this plan — the bug being fixed is a client written against a guessed API.
- The `Memory` protocol (`src/sdlc/memory/protocol.py`) does not change. `RecallSnapshot`, `RetainItem`, `MemoryKind` in `models.py` do not change.
- `src/sdlc/workflows/feature.py` and `src/sdlc/workflows/reflect.py` are **not edited by any task in this plan**.
- **The API key and tenant are read from the environment inside `_backend()` and never become activity-input or `MemoryConfig` fields.** `RecallInput`/`RetainInput`/`WatermarkInput`/`ReflectInput` are serialized into Temporal workflow history; a key placed on them is a key written to disk in plaintext.
- Memory must never block or fail a run: `recall_snapshot` degrades to an empty `RecallSnapshot(degraded=True)` on any backend error; `retain` propagates so Temporal retries.
- Env var naming follows the existing `SDLC_*` convention (`SDLC_MEMORY_BACKEND`, `SDLC_WORKTREES_ROOT`).
- New Python files: one short module docstring, inline comments only where a non-obvious invariant needs explaining. Match `activities.py` / `harness/adapters.py` style.
- Run tests with `python -m pytest`. Default `addopts` is `-q -m 'not slow and not temporal'`; the live test adds a `live` marker that is already registered in `pyproject.toml`.

---

### Task 1: Pin the API surface from the container's OpenAPI schema

Nothing else in this plan can be written honestly until this task runs. It resolves three contradictions in Hindsight's published docs (retain at `/memories/retain` vs `/memories`; recall at `/recall` vs `/memories/recall`; which parameter bounds recall's result count) and one unknown (whether bank ids tolerate `:`).

**Files:**
- Create: `tests/fixtures/hindsight-openapi.json`
- Create: `src/sdlc/memory/hindsight_api.py`
- Test: `tests/test_hindsight_api_constants.py`

**Interfaces:**
- Produces: `src/sdlc/memory/hindsight_api.py` exporting `BANK_PATH`, `RETAIN_PATH`, `RECALL_PATH`, `CONSOLIDATE_PATH`, `OPERATION_PATH` (all `str` templates containing `{tenant}` and, except `OPERATION_PATH`, `{bank}`), plus `RECALL_LIMIT_FIELD: str` naming the request field that bounds recall's result count, and `SCHEMA_PATH: Path` pointing at the vendored fixture.

- [ ] **Step 1: Start the container and confirm it answers**

```bash
docker compose up -d hindsight
# Poll until the API is up; the image boots an embedded Postgres and is slow first time.
python - <<'PY'
import time, urllib.request, urllib.error
for attempt in range(120):
    try:
        with urllib.request.urlopen("http://localhost:8888/openapi.json", timeout=5) as r:
            print("up after", attempt, "tries; status", r.status)
            break
    except Exception as exc:
        time.sleep(5)
else:
    raise SystemExit("hindsight never became reachable on :8888")
PY
```

Expected: `up after N tries; status 200`. If it never comes up, check `docker compose logs hindsight` — the most likely cause is a missing or rejected `HINDSIGHT_API_LLM_API_KEY` in `.env`.

- [ ] **Step 2: Vendor the schema**

```bash
python - <<'PY'
import json, urllib.request, pathlib
with urllib.request.urlopen("http://localhost:8888/openapi.json", timeout=30) as r:
    doc = json.load(r)
out = pathlib.Path("tests/fixtures/hindsight-openapi.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
print("openapi version:", doc.get("openapi"))
print("paths:", len(doc["paths"]))
PY
```

- [ ] **Step 3: Read the real paths out of the schema**

```bash
python - <<'PY'
import json, pathlib
doc = json.loads(pathlib.Path("tests/fixtures/hindsight-openapi.json").read_text(encoding="utf-8"))
for path in sorted(doc["paths"]):
    methods = sorted(m.upper() for m in doc["paths"][path] if m in
                     ("get", "put", "post", "patch", "delete"))
    if any(k in path for k in ("bank", "operation", "memor", "consolidat", "reflect")):
        print(f"{','.join(methods):20s} {path}")
PY
```

Read the output and identify the five operations this plan needs: create-or-update bank, retain memories, recall, trigger consolidation, and get operation status. Note the exact templates verbatim — including whether the tenant segment is `{tenant}`, `{tenant_id}` or literal `default`.

- [ ] **Step 4: Find the field that bounds recall's result count**

```bash
python - <<'PY'
import json, pathlib
doc = json.loads(pathlib.Path("tests/fixtures/hindsight-openapi.json").read_text(encoding="utf-8"))

def deref(node):
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"].lstrip("#/").split("/")
        node = doc
        for part in ref:
            node = node[part]
    return node

for path, ops in doc["paths"].items():
    if "recall" not in path:
        continue
    body = ops.get("post", {}).get("requestBody")
    if not body:
        continue
    schema = deref(deref(body)["content"]["application/json"]["schema"])
    print(path)
    for name, prop in sorted(schema.get("properties", {}).items()):
        print(f"   {name}: {json.dumps(deref(prop))[:160]}")
PY
```

Expected: exactly one of `limit`, `max_tokens` or `budget` bounds the number of results. Pick the one that bounds *count* if present (`limit`); otherwise use `max_tokens`. Record the choice — Task 7 uses it.

- [ ] **Step 5: Check whether bank ids tolerate a colon**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X PUT \
  "http://localhost:8888/v1/default/banks/project:probe" \
  -H "Content-Type: application/json" -d '{}'
curl -s -o /dev/null -w "%{http_code}\n" -X PUT \
  "http://localhost:8888/v1/default/banks/project-probe" \
  -H "Content-Type: application/json" -d '{}'
```

Adjust the URL prefix if Step 3 showed a different template. Expected: two 2xx codes, or a 4xx on the colon form. Either answer is fine — it decides whether `_bank_id()` in Task 5 is load-bearing or merely defensive. Record it.

- [ ] **Step 6: Write the constants module**

Fill each value from Steps 3–4. The strings below are placeholders showing the *shape*; **replace them with what the schema actually said** — do not commit these literals unverified.

```python
"""The pinned Hindsight API surface.

Every path here was read out of the container's own /openapi.json (vendored to
tests/fixtures/hindsight-openapi.json), not out of the published docs, which
contradict each other on two of them. tests/test_hindsight_api_constants.py
asserts each constant still exists in that schema, so a client cannot drift
back into calling an endpoint nobody serves."""
from __future__ import annotations

from pathlib import Path

SCHEMA_PATH = (Path(__file__).resolve().parents[3]
               / "tests" / "fixtures" / "hindsight-openapi.json")

BANK_PATH = "/v1/{tenant}/banks/{bank}"
RETAIN_PATH = "/v1/{tenant}/banks/{bank}/memories/retain"
RECALL_PATH = "/v1/{tenant}/banks/{bank}/memories/recall"
CONSOLIDATE_PATH = "/v1/{tenant}/banks/{bank}/consolidate"
OPERATION_PATH = "/v1/{tenant}/operations/{operation_id}"

# Step 4 of Task 1: the request field bounding recall's result count.
RECALL_LIMIT_FIELD = "limit"
```

- [ ] **Step 7: Write the test that keeps the constants honest**

```python
"""Asserts every pinned path exists in the vendored schema. This is what
stops the client drifting back to an invented API."""
from __future__ import annotations

import json
import re

import pytest

from sdlc.memory.hindsight_api import (
    BANK_PATH, CONSOLIDATE_PATH, OPERATION_PATH, RECALL_LIMIT_FIELD,
    RECALL_PATH, RETAIN_PATH, SCHEMA_PATH,
)


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _placeholder_agnostic(template: str) -> re.Pattern:
    """Our constants and the schema may name placeholders differently
    ({bank} vs {bank_id}); only the segment structure has to agree."""
    parts = re.split(r"(\{[^}]+\})", template)
    body = "".join(r"\{[^}]+\}" if p.startswith("{") else re.escape(p)
                   for p in parts)
    return re.compile("^" + body + "$")


def _find(schema, template):
    pattern = _placeholder_agnostic(template)
    return [p for p in schema["paths"] if pattern.match(p)]


@pytest.mark.parametrize("template,method", [
    (BANK_PATH, "put"),
    (RETAIN_PATH, "post"),
    (RECALL_PATH, "post"),
    (CONSOLIDATE_PATH, "post"),
    (OPERATION_PATH, "get"),
])
def test_pinned_path_exists_in_the_vendored_schema(schema, template, method):
    matches = _find(schema, template)
    assert matches, f"{template} is not a path in the vendored OpenAPI schema"
    assert any(method in schema["paths"][m] for m in matches), (
        f"{template} exists but serves no {method.upper()}")


def test_recall_limit_field_is_a_real_request_property(schema):
    matches = _find(schema, RECALL_PATH)
    body = schema["paths"][matches[0]]["post"]["requestBody"]
    ref = body["content"]["application/json"]["schema"].get("$ref", "")
    name = ref.rsplit("/", 1)[-1]
    props = schema["components"]["schemas"][name]["properties"]
    assert RECALL_LIMIT_FIELD in props, (
        f"{RECALL_LIMIT_FIELD} is not a recall request property; "
        f"available: {sorted(props)}")
```

- [ ] **Step 8: Run it**

Run: `python -m pytest tests/test_hindsight_api_constants.py -v`
Expected: 6 PASS. A failure here means Step 6 was filled in from memory instead of from the schema — go back and re-read the schema output.

- [ ] **Step 9: Commit**

```bash
git add tests/fixtures/hindsight-openapi.json src/sdlc/memory/hindsight_api.py tests/test_hindsight_api_constants.py
git commit -m "feat(memory): pin Hindsight's API surface from the container schema

The published docs contradict each other on retain's and recall's paths, so
both are read out of the running container's /openapi.json and vendored. Every
later path reference goes through these constants."
```

---

### Task 2: Contract-validating transport (the anti-fabrication harness)

Built before the client so every subsequent task's tests are contract-checked from the first line. It validates the *request* against the schema — catching invented paths and wrong body fields — and the test's own *canned response* against the schema, which is what catches the client parsing `items` when the API returns `results`.

**Files:**
- Modify: `pyproject.toml` (add `jsonschema>=4` to `dev` extra)
- Create: `tests/fakes/hindsight_contract.py`
- Test: `tests/test_hindsight_contract_harness.py`

**Interfaces:**
- Consumes: `SCHEMA_PATH` from Task 1.
- Produces: `ContractTransport(responses: dict[tuple[str, str], object])` — an `httpx.MockTransport` subclass; keys are `(METHOD, path_template)` using the templates from `hindsight_api`. Also `ContractViolation(AssertionError)`.

- [ ] **Step 1: Add the dev dependency**

In `pyproject.toml`, change the `dev` extra to:

```toml
dev = ["pytest>=8", "pytest-asyncio>=0.24", "pytest-cov>=5", "jsonschema>=4"]
```

Then: `uv pip install -e ".[dev]"` (or `python -m pip install -e ".[dev]"`).

- [ ] **Step 2: Write the failing test**

```python
"""The harness that replaces hand-asserted mock paths. If this test can be
made to pass by a client calling an endpoint nobody serves, the harness is
broken and so is every test built on it."""
from __future__ import annotations

import httpx
import pytest

from sdlc.memory.hindsight_api import BANK_PATH, RECALL_PATH
from tests.fakes.hindsight_contract import ContractTransport, ContractViolation


@pytest.mark.asyncio
async def test_a_path_absent_from_the_schema_is_rejected():
    transport = ContractTransport(responses={})
    client = httpx.AsyncClient(base_url="http://h.local", transport=transport)
    with pytest.raises(ContractViolation, match="no path in the Hindsight"):
        await client.post("/v1/default/banks/b/recall-memories",
                          json={"query": "q"})


@pytest.mark.asyncio
async def test_a_documented_path_is_accepted_and_returns_the_canned_body():
    transport = ContractTransport(responses={("POST", RECALL_PATH): {"results": []}})
    client = httpx.AsyncClient(base_url="http://h.local", transport=transport)
    resp = await client.post(
        RECALL_PATH.format(tenant="default", bank="b"), json={"query": "q"})
    assert resp.status_code == 200
    assert resp.json() == {"results": []}


@pytest.mark.asyncio
async def test_a_request_body_violating_the_schema_is_rejected():
    transport = ContractTransport(responses={("PUT", BANK_PATH): {}})
    client = httpx.AsyncClient(base_url="http://h.local", transport=transport)
    with pytest.raises(ContractViolation, match="request body"):
        # `items` is not a string-keyed object anywhere in the bank schema;
        # a list where an object is required must be caught.
        await client.put(BANK_PATH.format(tenant="default", bank="b"),
                         json=[1, 2, 3])
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python -m pytest tests/test_hindsight_contract_harness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.fakes.hindsight_contract'`.

- [ ] **Step 4: Implement the transport**

```python
"""An httpx transport that validates requests against Hindsight's real
OpenAPI schema rather than against the caller's assumptions.

The client this replaces was tested with mocks whose handlers asserted
`request.url.path == <the path the client itself chose>`, so the suite could
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
from referencing import Registry
from referencing.jsonschema import DRAFT202012

from sdlc.memory.hindsight_api import SCHEMA_PATH


class ContractViolation(AssertionError):
    pass


_DOC: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
_REGISTRY = Registry().with_resource("", DRAFT202012.create_resource(_DOC))


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


def _validate(schema: Any, instance: Any, label: str) -> None:
    if schema is None:
        return
    errors = sorted(Draft202012Validator(schema, registry=_REGISTRY)
                    .iter_errors(instance), key=lambda e: e.path)
    if errors:
        first = errors[0]
        raise ContractViolation(
            f"{label} violates the Hindsight schema at "
            f"{'/'.join(str(p) for p in first.path) or '<root>'}: "
            f"{first.message}")


class ContractTransport(httpx.MockTransport):
    """`responses` maps (METHOD, path_template) -> the JSON body to return."""

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

        key = (request.method.upper(), template)
        if key not in self._responses:
            raise ContractViolation(
                f"test supplied no canned response for {key}; "
                f"available: {sorted(self._responses)}")
        payload = self._responses[key]

        ok = (operation.get("responses", {}).get("200")
              or operation.get("responses", {}).get("201") or {})
        _validate(_json_schema(ok), payload,
                  f"canned response for {request.method} {template}")
        return httpx.Response(200, json=payload)
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_hindsight_contract_harness.py -v`
Expected: 3 PASS.

If `test_a_request_body_violating_the_schema_is_rejected` fails because the bank `PUT` accepts a free-form body, replace its assertion target with any endpoint in the vendored schema whose request body has a `required` property, and send `{}`. The point of the test is that body validation is wired up, not that one particular endpoint rejects lists.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/fakes/hindsight_contract.py tests/test_hindsight_contract_harness.py
git commit -m "test(memory): add a contract-validating httpx transport

Validates requests and canned responses against Hindsight's vendored OpenAPI
schema. The mocks it replaces asserted back whatever path the client chose,
which is why a client implementing an invented API stayed green."
```

---

### Task 3: Shared `recall_query_hash()`

`FakeMemory` hashes `bank|query|filters|cutoff`; the degraded path in `activities.py:49` omits the watermark entirely. Snapshots from the two are therefore not comparable, which matters because E-31/E-33 exist to measure a memory-on/memory-off delta.

**Files:**
- Create: `src/sdlc/memory/query_hash.py`
- Modify: `src/sdlc/memory/fake.py`, `src/sdlc/memory/activities.py`
- Test: `tests/test_recall_query_hash.py`

**Interfaces:**
- Produces: `recall_query_hash(bank: str, query: str, filters: dict[str, str], watermark: str | None) -> str`.

- [ ] **Step 1: Write the failing test**

```python
from sdlc.memory.query_hash import recall_query_hash


def test_hash_is_stable_across_filter_ordering():
    a = recall_query_hash("b", "q", {"stage": "clarify", "gate": "g"}, "5")
    b = recall_query_hash("b", "q", {"gate": "g", "stage": "clarify"}, "5")
    assert a == b


def test_watermark_changes_the_hash():
    assert (recall_query_hash("b", "q", {}, "5")
            != recall_query_hash("b", "q", {}, "6"))


def test_absent_watermark_is_distinct_from_a_literal_none_string():
    assert (recall_query_hash("b", "q", {}, None)
            != recall_query_hash("b", "q", {}, "none"))


def test_bank_and_query_are_separated_unambiguously():
    # "a|b" + "c" must not collide with "a" + "b|c".
    assert (recall_query_hash("a|b", "c", {}, None)
            != recall_query_hash("a", "b|c", {}, None))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_recall_query_hash.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.memory.query_hash'`.

- [ ] **Step 3: Implement**

```python
"""The one definition of a recall snapshot's identity.

FakeMemory, HindsightMemory and the degraded path in activities.py all use
this, so a snapshot taken against the fake and one taken against Hindsight
are comparable — which is what makes a memory-on/memory-off delta meaningful."""
from __future__ import annotations

import hashlib
import json


def recall_query_hash(bank: str, query: str, filters: dict[str, str],
                      watermark: str | None) -> str:
    # json.dumps rather than str(): it escapes separators, so a bank
    # containing the delimiter cannot forge another bank's hash.
    payload = json.dumps(
        [bank, query, sorted(filters.items()), watermark],
        separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_recall_query_hash.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Use it in `fake.py`**

In `src/sdlc/memory/fake.py`, add the import and replace the inline hash. Delete the now-unused `import hashlib`.

```python
from .query_hash import recall_query_hash
```

Replace lines 45–47 (the `query_hash = hashlib.sha256(...)` statement) with:

```python
        query_hash = recall_query_hash(bank, query, filters, str(cutoff))
```

- [ ] **Step 6: Use it in `activities.py`**

In `src/sdlc/memory/activities.py`, add `from .query_hash import recall_query_hash`, delete `import hashlib`, and replace the degraded-path hash (lines 49–51) with:

```python
        query_hash = recall_query_hash(inp.bank, inp.query, inp.filters,
                                       inp.watermark)
```

- [ ] **Step 7: Run the existing memory suite for regressions**

Run: `python -m pytest tests/test_memory_activities.py tests/test_recall_query_hash.py -v`
Expected: all PASS. No existing test asserts a literal hash value, so this is a pure refactor.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/memory/query_hash.py src/sdlc/memory/fake.py src/sdlc/memory/activities.py tests/test_recall_query_hash.py
git commit -m "refactor(memory): one definition of a recall snapshot's identity

The fake hashed bank|query|filters|cutoff; the degraded path dropped the
watermark, so snapshots from the two backends were not comparable."
```

---

### Task 4: Tenant and API key from the environment

**Files:**
- Modify: `src/sdlc/memory/activities.py:22-26`
- Test: `tests/test_memory_backend_selection.py`

**Interfaces:**
- Produces: `_backend(base_url: str, backend: str) -> Memory` — unchanged signature; reads `SDLC_MEMORY_TENANT` (default `"default"`) and `SDLC_MEMORY_API_KEY` (default `None`) from the environment.

> **Deviation from spec §3.6/§6, recorded deliberately.** The spec said `MemoryConfig.tenant`. Putting tenant on `MemoryConfig` means threading it through `RecallInput`/`RetainInput`/`WatermarkInput`/`ReflectInput`, `ScheduleAction`, `ReflectScheduleInput`, `feature.py` and `reflect.py` — and the plan's global constraint is that those two workflow files are not edited. Tenant is deployment configuration, exactly like the API key, so it is read from the environment in the same place. Net effect: fewer files touched, and `MemoryConfig` keeps its current shape.

- [ ] **Step 1: Write the failing test**

```python
"""The API key must never reach a `RecallInput`/`RetainInput`: those are
serialized into Temporal workflow history, which is durable storage."""
from __future__ import annotations

import dataclasses

import pytest

from sdlc.memory import activities
from sdlc.memory.activities import RecallInput, RetainInput, _backend
from sdlc.memory.fake import FakeMemory


def test_fake_backend_is_the_default():
    assert isinstance(_backend("http://x", "fake"), FakeMemory)


def test_hindsight_backend_reads_tenant_and_key_from_the_environment(monkeypatch):
    monkeypatch.setenv("SDLC_MEMORY_TENANT", "acme")
    monkeypatch.setenv("SDLC_MEMORY_API_KEY", "secret-token")
    mem = _backend("http://h.local", "hindsight")
    assert mem.tenant == "acme"
    assert mem.api_key == "secret-token"


def test_tenant_defaults_and_key_is_optional(monkeypatch):
    monkeypatch.delenv("SDLC_MEMORY_TENANT", raising=False)
    monkeypatch.delenv("SDLC_MEMORY_API_KEY", raising=False)
    mem = _backend("http://h.local", "hindsight")
    assert mem.tenant == "default"
    assert mem.api_key is None


@pytest.mark.parametrize("model", [RecallInput, RetainInput])
def test_activity_inputs_carry_no_credential_field(model):
    names = {f.name for f in dataclasses.fields(model)}
    assert not (names & {"api_key", "token", "authorization", "tenant"}), (
        f"{model.__name__} would write a credential into Temporal history")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_memory_backend_selection.py -v`
Expected: the two `hindsight` tests FAIL — `HindsightMemory.__init__` takes no `tenant`. The other two PASS.

- [ ] **Step 3: Implement `_backend`**

In `src/sdlc/memory/activities.py`, add `import os` and replace `_backend`:

```python
def _backend(base_url: str, backend: str) -> Memory:
    """Tenant and API key come from the environment, never from the activity
    input — RecallInput/RetainInput are serialized into Temporal history."""
    if backend == "hindsight":
        from .hindsight_client import HindsightMemory
        return HindsightMemory(
            base_url=base_url,
            tenant=os.environ.get("SDLC_MEMORY_TENANT", "default"),
            api_key=os.environ.get("SDLC_MEMORY_API_KEY") or None)
    return _fake_singleton
```

This does not pass until Task 5 gives `HindsightMemory` those parameters. Leave the two tests failing and proceed — Task 5 Step 5 is where they go green.

- [ ] **Step 4: Document the two new env vars**

Append to the Hindsight block in `.env.example`, after `SDLC_MEMORY_BASE_URL`:

```bash
# Tenant path segment; `default` for a single-tenant self-hosted container.
SDLC_MEMORY_TENANT=default
# Only needed if the Hindsight deployment enforces bearer auth. Read inside
# the activity and never placed on an activity input — those are serialized
# into Temporal workflow history.
# SDLC_MEMORY_API_KEY=
```

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/memory/activities.py tests/test_memory_backend_selection.py .env.example
git commit -m "feat(memory): read Hindsight tenant and API key from the environment

Activity inputs are serialized into Temporal history, so a credential placed
on one is a credential written to durable storage. Two tests fail until the
client grows the parameters."
```

---

### Task 5: Client core — bank ids, cached client, `ensure_bank`

**Files:**
- Rewrite: `src/sdlc/memory/hindsight_client.py`
- Test: `tests/test_hindsight_client_core.py`

**Interfaces:**
- Consumes: `BANK_PATH` (Task 1), `ContractTransport` (Task 2), `_backend` (Task 4).
- Produces: `HindsightMemory(base_url: str, tenant: str = "default", api_key: str | None = None, timeout_s: float = 30.0)` with public attributes `base_url`, `tenant`, `api_key`; `_bank_id(bank: str) -> str`; `async ensure_bank(bank: str) -> None`; and module-level `_clear_bank_cache()` / `_clear_client_cache()` for tests.

`_backend()` constructs a fresh `HindsightMemory` on **every** activity invocation. The client today builds an `httpx.AsyncClient` per instance and never closes it, so that is a socket leak under load — hence the module-level client cache below, not merely a tidier constructor.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import httpx
import pytest

from sdlc.memory import hindsight_client as hc
from sdlc.memory.hindsight_api import BANK_PATH
from sdlc.memory.hindsight_client import HindsightMemory, _bank_id
from tests.fakes.hindsight_contract import ContractTransport


@pytest.fixture(autouse=True)
def _clean():
    hc._clear_bank_cache()
    hc._clear_client_cache()
    yield
    hc._clear_bank_cache()
    hc._clear_client_cache()


def _client(transport) -> HindsightMemory:
    mem = HindsightMemory(base_url="http://h.local", tenant="default")
    mem._client = httpx.AsyncClient(base_url="http://h.local",
                                    transport=transport)
    return mem


def test_bank_ids_are_reduced_to_url_safe_segments():
    assert _bank_id("project:default") == "project-default"
    assert _bank_id("org") == "org"


def test_distinct_banks_stay_distinct_after_sanitising():
    assert _bank_id("project:a") != _bank_id("project:b")


@pytest.mark.asyncio
async def test_ensure_bank_puts_the_bank():
    transport = ContractTransport(responses={("PUT", BANK_PATH): {}})
    mem = _client(transport)
    await mem.ensure_bank("project:default")
    assert transport.requests[0].method == "PUT"
    assert transport.requests[0].url.path.endswith("/banks/project-default")


@pytest.mark.asyncio
async def test_ensure_bank_is_called_once_per_bank():
    transport = ContractTransport(responses={("PUT", BANK_PATH): {}})
    mem = _client(transport)
    await mem.ensure_bank("org")
    await mem.ensure_bank("org")
    assert len(transport.requests) == 1


def test_api_key_becomes_a_bearer_header():
    mem = HindsightMemory(base_url="http://h.local", api_key="tok")
    assert mem._client.headers["authorization"] == "Bearer tok"


def test_no_authorization_header_without_a_key():
    mem = HindsightMemory(base_url="http://h.local")
    assert "authorization" not in mem._client.headers


def test_instances_with_the_same_config_share_one_httpx_client():
    """_backend() builds a fresh HindsightMemory on every activity
    invocation; an AsyncClient per instance that is never closed is a socket
    leak under load."""
    a = HindsightMemory(base_url="http://h.local", tenant="default")
    b = HindsightMemory(base_url="http://h.local", tenant="default")
    assert a._client is b._client


def test_different_tenants_do_not_share_a_client():
    a = HindsightMemory(base_url="http://h.local", tenant="one")
    b = HindsightMemory(base_url="http://h.local", tenant="two")
    assert a._client is not b._client
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_hindsight_client_core.py -v`
Expected: FAIL — `ImportError: cannot import name '_bank_id'`.

- [ ] **Step 3: Rewrite the client's skeleton**

Replace the whole of `src/sdlc/memory/hindsight_client.py`. The `retain`/`recall`/`reflect` bodies land in Tasks 6–8; here they raise `NotImplementedError` so the module imports cleanly.

```python
"""Real Hindsight (vectorize-io) HTTP client — the integration seam noted in
ARCHITECTURE.md §6/§8.

Every path comes from hindsight_api, which is pinned against the container's
own OpenAPI schema. Callers only ever see the Memory protocol, so swapping
this module or base_url leaves workflow code untouched."""
from __future__ import annotations

import re

import httpx

from ..models import RecallSnapshot, RetainItem
from .hindsight_api import BANK_PATH
from .protocol import Memory

_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")

# Banks already ensured this process, keyed by (base_url, tenant, bank).
_ENSURED: set[tuple[str, str, str]] = set()

# _backend() builds a fresh HindsightMemory per activity invocation. One
# never-closed AsyncClient per instance leaks sockets, so connections are
# pooled per (base_url, tenant, api_key) instead.
_CLIENTS: dict[tuple[str, str, str | None], httpx.AsyncClient] = {}


def _clear_bank_cache() -> None:
    _ENSURED.clear()


def _clear_client_cache() -> None:
    _CLIENTS.clear()


def _client_for(base_url: str, tenant: str, api_key: str | None,
                timeout_s: float) -> httpx.AsyncClient:
    key = (base_url, tenant, api_key)
    client = _CLIENTS.get(key)
    if client is None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        client = httpx.AsyncClient(base_url=base_url, timeout=timeout_s,
                                   headers=headers)
        _CLIENTS[key] = client
    return client


def _bank_id(bank: str) -> str:
    """The factory's bank names ('project:default') contain characters a URL
    path segment should not carry. The mapping is one-way but injective for
    the names in use, since only ':' is ever replaced."""
    return _UNSAFE.sub("-", bank)


class HindsightMemory(Memory):
    def __init__(self, base_url: str, tenant: str = "default",
                 api_key: str | None = None, timeout_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.tenant = tenant
        self.api_key = api_key
        self._client = _client_for(self.base_url, tenant, api_key, timeout_s)

    def _path(self, template: str, bank: str, **extra: str) -> str:
        return template.format(tenant=self.tenant, bank=_bank_id(bank),
                               **extra)

    async def ensure_bank(self, bank: str) -> None:
        """Idempotent create-or-update. Without it the first recall against a
        fresh volume 404s."""
        key = (self.base_url, self.tenant, _bank_id(bank))
        if key in _ENSURED:
            return
        resp = await self._client.put(self._path(BANK_PATH, bank), json={})
        resp.raise_for_status()
        _ENSURED.add(key)

    async def current_watermark(self, bank: str) -> str:
        raise NotImplementedError

    async def retain(self, item: RetainItem) -> None:
        raise NotImplementedError

    async def recall(self, bank: str, query: str, filters: dict[str, str],
                     watermark: str | None) -> RecallSnapshot:
        raise NotImplementedError

    async def reflect(self, bank: str) -> None:
        raise NotImplementedError
```

- [ ] **Step 4: Run the core tests**

Run: `python -m pytest tests/test_hindsight_client_core.py -v`
Expected: 8 PASS.

If the bank `PUT` requires a non-empty body, Task 1 Step 5's probe will have shown a 4xx; send the minimal body the schema marks `required` instead of `{}`.

- [ ] **Step 5: Confirm Task 4's tests now pass**

Run: `python -m pytest tests/test_memory_backend_selection.py -v`
Expected: 5 PASS (they were failing at the end of Task 4).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/memory/hindsight_client.py tests/test_hindsight_client_core.py
git commit -m "feat(memory): Hindsight client core — bank ids, auth, ensure_bank

Paths come from the pinned constants; tests run through the contract
transport, so an invented endpoint cannot pass. retain/recall/reflect follow."
```

---

### Task 6: `retain` — async, tagged, idempotent

**Files:**
- Modify: `src/sdlc/memory/hindsight_client.py`
- Test: `tests/test_hindsight_retain.py`

**Interfaces:**
- Consumes: `RETAIN_PATH` (Task 1).
- Produces: module-level `TAG_PROMOTED_KEYS: tuple[str, ...] = ("stage", "gate")`, `_tags(item: RetainItem) -> list[str]`, `_document_id(item: RetainItem) -> str`, and a working `HindsightMemory.retain`. `current_watermark` is implemented here too — it is a pure clock read with no HTTP call, and Task 7's cutoff depends on it.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest

from sdlc.memory import hindsight_client as hc
from sdlc.memory.hindsight_api import BANK_PATH, RETAIN_PATH
from sdlc.memory.hindsight_client import HindsightMemory
from sdlc.models import MemoryKind, RetainItem
from tests.fakes.hindsight_contract import ContractTransport


@pytest.fixture(autouse=True)
def _clean():
    hc._clear_bank_cache()
    hc._clear_client_cache()
    yield
    hc._clear_bank_cache()
    hc._clear_client_cache()


def _transport():
    return ContractTransport(responses={
        ("PUT", BANK_PATH): {},
        ("POST", RETAIN_PATH): {"success": True, "bank_id": "b",
                                "items_count": 1},
    })


def _client(transport) -> HindsightMemory:
    mem = HindsightMemory(base_url="http://h.local")
    mem._client = httpx.AsyncClient(base_url="http://h.local",
                                    transport=transport)
    return mem


def _sent(transport) -> dict:
    post = [r for r in transport.requests if r.method == "POST"][0]
    return json.loads(post.content)


def _item(**over) -> RetainItem:
    base = dict(kind=MemoryKind.STAGE_SUMMARY, bank="project:default",
                text="the clarifier settled the scope",
                metadata={"stage": "clarify", "run_id": "run-1"})
    base.update(over)
    return RetainItem(**base)


@pytest.mark.asyncio
async def test_retain_sends_content_not_text():
    transport = _transport()
    await _client(transport).retain(_item())
    item = _sent(transport)["items"][0]
    assert item["content"] == "the clarifier settled the scope"
    assert "text" not in item


@pytest.mark.asyncio
async def test_promoted_metadata_becomes_tags_alongside_kind():
    transport = _transport()
    await _client(transport).retain(_item())
    tags = _sent(transport)["items"][0]["tags"]
    assert "kind:stage_summary" in tags
    assert "stage:clarify" in tags


@pytest.mark.asyncio
async def test_unbounded_metadata_keys_stay_out_of_tags():
    transport = _transport()
    await _client(transport).retain(_item())
    item = _sent(transport)["items"][0]
    assert not any(t.startswith("run_id:") for t in item["tags"])
    assert item["metadata"]["run_id"] == "run-1"


@pytest.mark.asyncio
async def test_retain_is_async_with_a_deterministic_operation_id():
    t1, t2 = _transport(), _transport()
    await _client(t1).retain(_item())
    await _client(t2).retain(_item())
    body1, body2 = _sent(t1), _sent(t2)
    assert body1["async"] is True
    assert body1["operation_id"] == body2["operation_id"]
    assert body1["items"][0]["document_id"] == body2["items"][0]["document_id"]


@pytest.mark.asyncio
async def test_different_text_gets_a_different_document_id():
    t1, t2 = _transport(), _transport()
    await _client(t1).retain(_item())
    await _client(t2).retain(_item(text="something else entirely"))
    assert (_sent(t1)["items"][0]["document_id"]
            != _sent(t2)["items"][0]["document_id"])


@pytest.mark.asyncio
async def test_retain_stamps_a_worker_clock_timestamp():
    transport = _transport()
    await _client(transport).retain(_item())
    stamp = _sent(transport)["items"][0]["timestamp"]
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


@pytest.mark.asyncio
async def test_retain_ensures_the_bank_first():
    transport = _transport()
    await _client(transport).retain(_item())
    assert transport.requests[0].method == "PUT"


@pytest.mark.asyncio
async def test_current_watermark_is_an_iso_timestamp_and_makes_no_request():
    transport = _transport()
    mem = _client(transport)
    wm = await mem.current_watermark("project:default")
    assert datetime.fromisoformat(wm.replace("Z", "+00:00")).tzinfo is not None
    assert transport.requests == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_hindsight_retain.py -v`
Expected: 8 FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement**

Add to the imports in `hindsight_client.py`:

```python
import hashlib
import uuid
from datetime import datetime, timezone

from .hindsight_api import BANK_PATH, RETAIN_PATH
```

Add after `_bank_id`:

```python
# Metadata keys promoted to tags so recall can filter on them. Hindsight
# cannot filter on metadata at query time, so anything absent here is
# unfilterable — see _filter_tags in recall. run_id/task_id/source_url stay
# out deliberately: unbounded cardinality, and URLs do not belong in a tag
# namespace.
TAG_PROMOTED_KEYS: tuple[str, ...] = ("stage", "gate")


def _tags(item: RetainItem) -> list[str]:
    tags = [f"kind:{item.kind.value}"]
    tags += [f"{k}:{item.metadata[k]}"
             for k in TAG_PROMOTED_KEYS if k in item.metadata]
    return tags


def _document_id(item: RetainItem) -> str:
    """Content-addressed, so Temporal's retries upsert rather than duplicate."""
    return hashlib.sha256(
        f"{item.bank}|{item.kind.value}|{item.text}".encode("utf-8")
    ).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
```

Replace the two stub methods:

```python
    async def current_watermark(self, bank: str) -> str:
        """Hindsight has no watermark, version or as-of endpoint, so the
        freeze point is a worker-clock timestamp and recall enforces it
        client-side. retain stamps the same clock, so the comparison in
        recall is like-for-like and server skew cannot leak a post-freeze
        memory into a pinned run."""
        return _now_iso()

    async def retain(self, item: RetainItem) -> None:
        await self.ensure_bank(item.bank)
        doc_id = _document_id(item)
        resp = await self._client.post(
            self._path(RETAIN_PATH, item.bank),
            json={
                "items": [{
                    "content": item.text,
                    "context": item.kind.value,
                    "tags": _tags(item),
                    "metadata": item.metadata,
                    "timestamp": _now_iso(),
                    "document_id": doc_id,
                }],
                # Retain runs LLM fact extraction; synchronously it would
                # exceed MEM_ACT's 30s ceiling. The operation_id is derived
                # from content so Temporal's five retries are idempotent.
                "async": True,
                "operation_id": str(uuid.UUID(hex=doc_id[:32])),
            })
        resp.raise_for_status()
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_hindsight_retain.py -v`
Expected: 8 PASS.

If the contract transport rejects `operation_id` or `document_id` as unknown properties, the vendored schema names them differently — read `components.schemas` for the retain request and use the real names. Do **not** delete the fields to make the test pass; their absence is what breaks retry idempotency.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/memory/hindsight_client.py tests/test_hindsight_retain.py
git commit -m "feat(memory): implement Hindsight retain

Sends content/context/tags/timestamp per the pinned schema. Promotes stage and
gate metadata to tags so recall can actually filter on them — Hindsight cannot
filter on metadata at query time. Async with a content-derived operation_id:
LLM fact extraction would blow through MEM_ACT's 30s ceiling, and the id makes
Temporal's retries idempotent."
```

---

### Task 7: `recall` — tag filters, watermark cutoff, over-fetch

The task that fixes the silent-wrongness defect: today's filters go into metadata, which Hindsight cannot filter on, so clarify would recall architect's memories.

**Files:**
- Modify: `src/sdlc/memory/hindsight_client.py`
- Test: `tests/test_hindsight_recall.py`

**Interfaces:**
- Consumes: `RECALL_PATH`, `RECALL_LIMIT_FIELD` (Task 1), `recall_query_hash` (Task 3), `TAG_PROMOTED_KEYS` (Task 6).
- Produces: `_filter_tags(filters: dict[str, str]) -> list[str]` (raises `ValueError` on unfilterable keys), `RECALL_KEEP: int = 10`, `OVER_FETCH: int = 3`, and a working `HindsightMemory.recall`.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import json

import httpx
import pytest

from sdlc.memory import hindsight_client as hc
from sdlc.memory.hindsight_api import BANK_PATH, RECALL_LIMIT_FIELD, RECALL_PATH
from sdlc.memory.hindsight_client import RECALL_KEEP, HindsightMemory
from tests.fakes.hindsight_contract import ContractTransport


@pytest.fixture(autouse=True)
def _clean():
    hc._clear_bank_cache()
    hc._clear_client_cache()
    yield
    hc._clear_bank_cache()
    hc._clear_client_cache()


def _result(text: str, mentioned_at: str) -> dict:
    return {"id": f"m-{text[:6]}", "text": text, "type": "world",
            "mentioned_at": mentioned_at, "tags": [], "entities": [],
            "document_id": "d1", "chunk_id": "c1",
            "scores": {"final": 0.9}}


def _transport(results):
    return ContractTransport(responses={
        ("PUT", BANK_PATH): {},
        ("POST", RECALL_PATH): {"results": results},
    })


def _client(transport) -> HindsightMemory:
    mem = HindsightMemory(base_url="http://h.local")
    mem._client = httpx.AsyncClient(base_url="http://h.local",
                                    transport=transport)
    return mem


def _sent(transport) -> dict:
    post = [r for r in transport.requests if r.method == "POST"][0]
    return json.loads(post.content)


@pytest.mark.asyncio
async def test_recall_reads_results_not_items():
    transport = _transport([_result("a gotcha worth knowing",
                                    "2026-08-01T00:00:00+00:00")])
    snap = await _client(transport).recall("project:default", "q", {}, None)
    assert snap.items == ["a gotcha worth knowing"]


@pytest.mark.asyncio
async def test_filters_become_strict_tag_matches():
    transport = _transport([])
    await _client(transport).recall("project:default", "q",
                                    {"stage": "clarify"}, None)
    body = _sent(transport)
    assert body["tags"] == ["stage:clarify"]
    assert body["tags_match"] == "all_strict"


@pytest.mark.asyncio
async def test_empty_filters_send_no_tag_keys_at_all():
    transport = _transport([])
    await _client(transport).recall("project:default", "q", {}, None)
    body = _sent(transport)
    assert "tags" not in body
    assert "tags_match" not in body


@pytest.mark.asyncio
async def test_an_unfilterable_filter_key_raises_rather_than_returning_everything():
    transport = _transport([])
    with pytest.raises(ValueError, match="run_id"):
        await _client(transport).recall("project:default", "q",
                                        {"run_id": "run-1"}, None)


@pytest.mark.asyncio
async def test_results_after_the_watermark_are_dropped():
    transport = _transport([
        _result("before the freeze", "2026-08-01T00:00:00+00:00"),
        _result("after the freeze", "2026-08-03T00:00:00+00:00"),
    ])
    snap = await _client(transport).recall(
        "project:default", "q", {}, "2026-08-02T00:00:00+00:00")
    assert snap.items == ["before the freeze"]


@pytest.mark.asyncio
async def test_a_result_without_a_timestamp_is_dropped_when_pinned():
    bad = _result("undateable", "2026-08-01T00:00:00+00:00")
    del bad["mentioned_at"]
    transport = _transport([bad])
    snap = await _client(transport).recall(
        "project:default", "q", {}, "2026-08-02T00:00:00+00:00")
    assert snap.items == []


@pytest.mark.asyncio
async def test_a_result_without_a_timestamp_survives_when_unpinned():
    bad = _result("undateable", "2026-08-01T00:00:00+00:00")
    del bad["mentioned_at"]
    snap = await _client(_transport([bad])).recall(
        "project:default", "q", {}, None)
    assert snap.items == ["undateable"]


@pytest.mark.asyncio
async def test_recall_over_fetches_so_the_cutoff_does_not_starve_the_snapshot():
    transport = _transport([])
    await _client(transport).recall("project:default", "q", {}, None)
    assert _sent(transport)[RECALL_LIMIT_FIELD] > RECALL_KEEP


@pytest.mark.asyncio
async def test_snapshot_is_truncated_to_the_keep_size():
    results = [_result(f"memory {i}", "2026-08-01T00:00:00+00:00")
               for i in range(RECALL_KEEP + 5)]
    snap = await _client(_transport(results)).recall(
        "project:default", "q", {}, None)
    assert len(snap.items) == RECALL_KEEP


@pytest.mark.asyncio
async def test_snapshot_carries_the_pinned_watermark_and_a_query_hash():
    snap = await _client(_transport([])).recall(
        "project:default", "q", {}, "2026-08-02T00:00:00+00:00")
    assert snap.watermark == "2026-08-02T00:00:00+00:00"
    assert snap.bank == "project:default"
    assert len(snap.query_hash) == 64
    assert snap.degraded is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_hindsight_recall.py -v`
Expected: 10 FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement**

Extend the imports:

```python
from .hindsight_api import (
    BANK_PATH, RECALL_LIMIT_FIELD, RECALL_PATH, RETAIN_PATH,
)
from .query_hash import recall_query_hash
```

Add after `_tags`:

```python
# Filter keys recall can honour — the promoted tags plus the always-written
# kind tag.
_FILTERABLE = frozenset(TAG_PROMOTED_KEYS) | {"kind"}

RECALL_KEEP = 10          # matches FakeMemory's slice size
OVER_FETCH = 3            # the cutoff discards, so ask for more than we keep


def _filter_tags(filters: dict[str, str]) -> list[str]:
    """Raises rather than silently returning unfiltered results. Hindsight
    cannot filter on metadata at query time, so a key with no promoted tag
    would otherwise produce a filtered-looking call that matched everything."""
    unfilterable = sorted(set(filters) - _FILTERABLE)
    if unfilterable:
        raise ValueError(
            f"recall filter keys {unfilterable} are not promoted to Hindsight "
            f"tags, and Hindsight cannot filter on metadata; add them to "
            f"TAG_PROMOTED_KEYS (filterable today: {sorted(_FILTERABLE)})")
    return [f"{k}:{v}" for k, v in sorted(filters.items())]


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _within_watermark(result: dict, watermark: str | None) -> bool:
    if watermark is None:
        return True
    stamp = result.get("mentioned_at")
    if not stamp:
        # Cannot prove it predates the freeze, so it does not enter a pinned
        # run. Keeps the NFR-6 guarantee honest at the cost of a rare drop.
        return False
    try:
        return _parse_iso(stamp) <= _parse_iso(watermark)
    except ValueError:
        return False
```

Replace the `recall` stub:

```python
    async def recall(self, bank: str, query: str, filters: dict[str, str],
                     watermark: str | None) -> RecallSnapshot:
        await self.ensure_bank(bank)
        payload: dict[str, object] = {
            "query": query,
            RECALL_LIMIT_FIELD: RECALL_KEEP * OVER_FETCH,
        }
        tags = _filter_tags(filters)
        if tags:
            # all_strict: every tag must match AND untagged memories are
            # excluded. The permissive default would match everything, which
            # is the filter-shaped no-op this client exists to remove.
            payload["tags"] = tags
            payload["tags_match"] = "all_strict"

        resp = await self._client.post(self._path(RECALL_PATH, bank),
                                       json=payload)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        kept = [r["text"] for r in results
                if _within_watermark(r, watermark)][:RECALL_KEEP]
        return RecallSnapshot(
            query_hash=recall_query_hash(bank, query, filters, watermark),
            bank=bank, watermark=watermark or _now_iso(), items=kept)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_hindsight_recall.py -v`
Expected: 10 PASS.

If `test_recall_over_fetches...` fails because `RECALL_LIMIT_FIELD` is `max_tokens` rather than a count, change `RECALL_KEEP * OVER_FETCH` to a token budget (`4096`) and change that test to assert the field is present and positive. Record the change in the module docstring.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/memory/hindsight_client.py tests/test_hindsight_recall.py
git commit -m "feat(memory): implement Hindsight recall with tag filters and a watermark cutoff

Filters map to strict tag matches instead of metadata, which Hindsight cannot
filter on — the previous shape would have had clarify recalling architect's
memories with no error anywhere. The NFR-6 freeze is enforced client-side as a
mentioned_at cutoff because Hindsight has no point-in-time read; recall
over-fetches so the cutoff does not starve the snapshot."
```

---

### Task 8: `reflect` → consolidate, and wait for it

**Files:**
- Modify: `src/sdlc/memory/hindsight_client.py`
- Test: `tests/test_hindsight_reflect.py`

**Interfaces:**
- Consumes: `CONSOLIDATE_PATH`, `OPERATION_PATH` (Task 1).
- Produces: `POLL_INTERVAL_S: float = 5.0`, `POLL_DEADLINE_S: float = 540.0`, a working `HindsightMemory.reflect`, and `ConsolidationFailed(RuntimeError)`.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import httpx
import pytest

from sdlc.memory import hindsight_client as hc
from sdlc.memory.hindsight_api import (
    BANK_PATH, CONSOLIDATE_PATH, OPERATION_PATH,
)
from sdlc.memory.hindsight_client import ConsolidationFailed, HindsightMemory
from tests.fakes.hindsight_contract import ContractTransport


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    hc._clear_bank_cache()
    hc._clear_client_cache()
    # Never actually sleep in unit tests.
    monkeypatch.setattr(hc, "POLL_INTERVAL_S", 0.0)
    yield
    hc._clear_bank_cache()
    hc._clear_client_cache()


def _transport(op_status: str):
    return ContractTransport(responses={
        ("PUT", BANK_PATH): {},
        ("POST", CONSOLIDATE_PATH): {"operation_id": "op-1"},
        ("GET", OPERATION_PATH): {"id": "op-1", "type": "consolidate",
                                  "status": op_status},
    })


def _client(transport) -> HindsightMemory:
    mem = HindsightMemory(base_url="http://h.local")
    mem._client = httpx.AsyncClient(base_url="http://h.local",
                                    transport=transport)
    return mem


@pytest.mark.asyncio
async def test_reflect_triggers_consolidation_not_the_qa_endpoint():
    transport = _transport("completed")
    await _client(transport).reflect("project:default")
    posted = [r for r in transport.requests if r.method == "POST"][0]
    assert "consolidate" in posted.url.path
    assert not posted.url.path.endswith("/reflect")


@pytest.mark.asyncio
async def test_reflect_polls_the_operation_to_completion():
    transport = _transport("completed")
    await _client(transport).reflect("project:default")
    assert any(r.method == "GET" and "op-1" in r.url.path
               for r in transport.requests)


@pytest.mark.asyncio
async def test_a_failed_consolidation_raises():
    with pytest.raises(ConsolidationFailed, match="failed"):
        await _client(_transport("failed")).reflect("project:default")


@pytest.mark.asyncio
async def test_a_cancelled_consolidation_raises():
    with pytest.raises(ConsolidationFailed):
        await _client(_transport("cancelled")).reflect("project:default")


@pytest.mark.asyncio
async def test_polling_gives_up_rather_than_hanging_past_the_activity_budget(
        monkeypatch):
    monkeypatch.setattr(hc, "POLL_DEADLINE_S", 0.0)
    with pytest.raises(ConsolidationFailed, match="did not finish"):
        await _client(_transport("processing")).reflect("project:default")


@pytest.mark.asyncio
async def test_a_synchronous_consolidation_needs_no_polling():
    transport = ContractTransport(responses={
        ("PUT", BANK_PATH): {},
        ("POST", CONSOLIDATE_PATH): {},
    })
    await _client(transport).reflect("project:default")
    assert not any(r.method == "GET" for r in transport.requests)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_hindsight_reflect.py -v`
Expected: 6 FAIL — `ImportError: cannot import name 'ConsolidationFailed'`.

- [ ] **Step 3: Implement**

Extend imports with `import asyncio`, `import time`, and add `CONSOLIDATE_PATH, OPERATION_PATH` to the `hindsight_api` import.

Add near the other module constants:

```python
# ReflectWorkflow's REFLECT_ACT allows 10 minutes; give up just inside it so
# the client raises something diagnosable instead of Temporal killing the
# activity on a timeout that says nothing about consolidation. Both values are
# unmeasured — tune against a real bank.
POLL_INTERVAL_S = 5.0
POLL_DEADLINE_S = 540.0

_TERMINAL_OK = {"completed", "complete", "succeeded", "success"}
_TERMINAL_BAD = {"failed", "cancelled", "canceled", "error"}


class ConsolidationFailed(RuntimeError):
    pass
```

Replace the `reflect` stub:

```python
    async def reflect(self, bank: str) -> None:
        """Consolidation, not the /reflect question-answering endpoint —
        that runs an agent loop and returns prose the nightly job discards.
        Polls to a terminal state: without it ReflectWorkflow reports success
        for a consolidation that failed, the silent no-op its own docstring
        names as the failure mode it exists to prevent."""
        await self.ensure_bank(bank)
        resp = await self._client.post(self._path(CONSOLIDATE_PATH, bank))
        resp.raise_for_status()
        operation_id = (resp.json() or {}).get("operation_id")
        if not operation_id:
            return  # consolidation ran synchronously
        await self._await_operation(bank, operation_id)

    async def _await_operation(self, bank: str, operation_id: str) -> None:
        deadline = time.monotonic() + POLL_DEADLINE_S
        status = "unknown"
        while True:
            resp = await self._client.get(
                self._path(OPERATION_PATH, bank, operation_id=operation_id))
            resp.raise_for_status()
            body = resp.json() or {}
            status = str(body.get("status", "unknown")).lower()
            if status in _TERMINAL_OK:
                return
            if status in _TERMINAL_BAD:
                raise ConsolidationFailed(
                    f"consolidation of {bank} ended {status}: "
                    f"{body.get('error_message') or 'no detail'}")
            if time.monotonic() >= deadline:
                raise ConsolidationFailed(
                    f"consolidation of {bank} did not finish within "
                    f"{POLL_DEADLINE_S:.0f}s (last status {status})")
            await asyncio.sleep(POLL_INTERVAL_S)
```

`_path` already accepts `**extra`, so `operation_id` substitutes even though `OPERATION_PATH` carries no `{bank}`. If Task 1 found the operations endpoint is bank-scoped, the same call works unchanged.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_hindsight_reflect.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Run the whole memory suite**

Run: `python -m pytest tests/ -k "memory or hindsight or recall_query" -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/memory/hindsight_client.py tests/test_hindsight_reflect.py
git commit -m "feat(memory): point reflect at consolidation and wait for it

/reflect is agentic Q&A returning prose the nightly job discards; bank
consolidation is /consolidate. Polls the operation to a terminal state so
ReflectWorkflow cannot report success for a consolidation that failed."
```

---

### Task 9: Retire the fabricated tests; add the live test

**Files:**
- Delete: `tests/test_hindsight_client.py`
- Create: `tests/test_hindsight_live.py`

**Interfaces:**
- Consumes: the complete `HindsightMemory` from Tasks 5–8.

- [ ] **Step 1: Delete the fabricated tests**

```bash
git rm tests/test_hindsight_client.py
```

All four assert the invented API (`/v1/banks/{bank}/recall` and friends). Repairing them would rebuild the same trap: a mock that asserts back whatever the client chose. Their coverage is replaced by Tasks 5–8, which run through the contract transport.

- [ ] **Step 2: Write the live test**

```python
"""The test that proves the integration is real.

Skipped by default: it needs a running Hindsight container and spends LLM
tokens through HINDSIGHT_API_LLM_API_KEY on every retain (fact extraction).

Run with:
  docker compose up -d hindsight
  SDLC_LIVE_TESTS=1 python -m pytest tests/test_hindsight_live.py -v -m live
"""
from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest

from sdlc.memory.hindsight_client import HindsightMemory
from sdlc.models import MemoryKind, RetainItem

BASE_URL = os.environ.get("SDLC_MEMORY_BASE_URL_LIVE", "http://localhost:8888")


def _reachable() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/openapi.json", timeout=3).status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("SDLC_LIVE_TESTS") != "1",
                       reason="set SDLC_LIVE_TESTS=1 to spend tokens"),
    pytest.mark.skipif(not _reachable(),
                       reason=f"no Hindsight answering on {BASE_URL}"),
]


@pytest.fixture
def memory() -> HindsightMemory:
    return HindsightMemory(
        base_url=BASE_URL,
        tenant=os.environ.get("SDLC_MEMORY_TENANT", "default"),
        api_key=os.environ.get("SDLC_MEMORY_API_KEY") or None,
        timeout_s=120.0)


@pytest.fixture
def bank() -> str:
    return f"livetest-{uuid.uuid4().hex[:8]}"


async def _settle(memory: HindsightMemory, bank: str) -> None:
    """Retain is async on Hindsight's side; consolidation makes what was
    retained recallable. reflect() blocks until the operation is terminal."""
    await memory.reflect(bank)
    await asyncio.sleep(2)


@pytest.mark.asyncio
async def test_a_retained_memory_comes_back_from_recall(memory, bank):
    await memory.retain(RetainItem(
        kind=MemoryKind.GOTCHA, bank=bank,
        text="The staging deploy fails when PGBOUNCER_MAX_CLIENT_CONN is unset.",
        metadata={"stage": "qa"}))
    await _settle(memory, bank)

    snap = await memory.recall(bank, "why does the staging deploy fail?", {},
                               None)
    assert snap.items, "nothing recalled — retain or consolidation did not land"
    assert any("PGBOUNCER" in item.upper() for item in snap.items)
    assert snap.degraded is False


@pytest.mark.asyncio
async def test_stage_filters_actually_exclude_other_stages(memory, bank):
    await memory.retain(RetainItem(
        kind=MemoryKind.STAGE_SUMMARY, bank=bank,
        text="Clarify settled that the export format is CSV, not XLSX.",
        metadata={"stage": "clarify"}))
    await memory.retain(RetainItem(
        kind=MemoryKind.STAGE_SUMMARY, bank=bank,
        text="Architecture chose a read-through Redis cache for the catalogue.",
        metadata={"stage": "architect"}))
    await _settle(memory, bank)

    snap = await memory.recall(bank, "what was decided?",
                               {"stage": "clarify"}, None)
    joined = " ".join(snap.items).upper()
    assert "CSV" in joined or "XLSX" in joined, (
        "the clarify memory did not come back; filter may be over-strict")
    assert "REDIS" not in joined, (
        "the architect memory leaked through a stage:clarify filter — "
        "this is the defect the tag mapping exists to fix")


@pytest.mark.asyncio
async def test_the_watermark_excludes_memories_retained_after_it(memory, bank):
    await memory.retain(RetainItem(
        kind=MemoryKind.GOTCHA, bank=bank,
        text="Postgres 14 rejects the CONCURRENTLY index build in a txn.",
        metadata={"stage": "qa"}))
    await _settle(memory, bank)

    watermark = await memory.current_watermark(bank)
    await asyncio.sleep(2)

    await memory.retain(RetainItem(
        kind=MemoryKind.GOTCHA, bank=bank,
        text="Redis 7 changed the default eviction policy to noeviction.",
        metadata={"stage": "qa"}))
    await _settle(memory, bank)

    pinned = await memory.recall(bank, "what should I watch out for?", {},
                                 watermark)
    joined = " ".join(pinned.items).upper()
    assert "REDIS" not in joined, (
        "a memory retained after the freeze point entered a pinned recall")

    unpinned = await memory.recall(bank, "what should I watch out for?", {},
                                   None)
    assert "REDIS" in " ".join(unpinned.items).upper(), (
        "the second memory never landed at all — the pinned assertion above "
        "would then be vacuous")
```

- [ ] **Step 3: Run it against the live container**

```bash
docker compose up -d hindsight
SDLC_LIVE_TESTS=1 python -m pytest tests/test_hindsight_live.py -v -m live
```

Expected: 3 PASS. Save the output — Task 10 records it.

Failures are informative, not just red:
- **Nothing recalled at all** → `_settle`'s wait is too short, or retain's `async: true` never completed. Check `docker compose logs hindsight` for extraction errors, and raise the sleep.
- **Test 2's Redis assertion fails** → `all_strict` is not excluding untagged/other-tagged memories. Re-read the vendored schema's `tags_match` enum; the value may be named differently.
- **Test 3's Redis assertion fails** → `mentioned_at` does not echo the `timestamp` we send (spec §8's open question). Log a recalled result's `mentioned_at` next to the watermark and compare; if Hindsight stamps its own receipt time the cutoff still works, but record the finding in the spec.

- [ ] **Step 4: Run the full default suite for regressions**

Run: `python -m pytest`
Expected: all PASS. The live test is excluded by its skipif; the contract tests run.

- [ ] **Step 5: Commit**

```bash
git add tests/test_hindsight_live.py
git commit -m "test(memory): prove the Hindsight integration against a live container

Asserts the three things mocks structurally cannot: a retained memory comes
back, a stage filter excludes other stages, and the watermark excludes what
was retained after it. Deletes the four tests that asserted the invented API."
```

---

### Task 10: Record what is now true in the ROADMAP

**Files:**
- Modify: `ROADMAP.md:222` (NFR-7), `ROADMAP.md:221` (NFR-6)
- Modify: `docs/superpowers/specs/2026-08-02-hindsight-real-integration-design.md` (§8 resolutions)

- [ ] **Step 1: Resolve the spec's known unknowns**

In §8 of the spec, replace each bullet with what Tasks 1 and 9 actually found: the real retain/recall paths, the result-count field, whether bank ids tolerate `:`, observed consolidation latency, and whether `mentioned_at` echoed the sent `timestamp`. Delete bullets that are no longer unknown.

- [ ] **Step 2: Correct the NFR lines**

Replace `ROADMAP.md:221`:

```markdown
- [x] **NFR-6** Reproducibility vs memoization — watermark-pinned recall + content-addressed cache. *Pinning is exact on `fake` (entry-count cutoff) and a `mentioned_at` cutoff on `hindsight`, which has no point-in-time read: memories retained after the freeze cannot enter a stage input, but ranking is still contaminated by them and post-freeze consolidation can mint observations carrying pre-freeze timestamps. `2026-08-02-hindsight-real-integration-design` §2.1.*
```

Replace `ROADMAP.md:222`:

```markdown
- [x] **NFR-7** Portability — `MemoryConfig.backend` defaults to `fake`; real Hindsight client for self-hosting, verified against a live container by `tests/test_hindsight_live.py` (the client shipped before 2026-08-02 implemented an invented API and could not have worked).
```

- [ ] **Step 3: Verify the line numbers still match**

Run: `python -m pytest` and `git diff ROADMAP.md`
Expected: exactly the two NFR lines changed. If earlier edits shifted line numbers, find the lines by their `**NFR-6**` / `**NFR-7**` text.

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md docs/superpowers/specs/2026-08-02-hindsight-real-integration-design.md
git commit -m "docs(memory): record the real state of the Hindsight integration

NFR-7 claimed a working client for a client whose every endpoint would 404.
NFR-6 now states what watermark pinning does and does not guarantee on a
backend with no point-in-time read. Live-test evidence, not a green CI run."
```

---

## Definition of done

- `python -m pytest` green.
- `SDLC_LIVE_TESTS=1 python -m pytest tests/test_hindsight_live.py -m live` green against a running container, **run at least once and its output recorded in Task 10's commit**. A green default suite is not evidence for NFR-7 — that is exactly the mistake this work is correcting.
- No path literal to Hindsight anywhere in `src/` outside `hindsight_api.py`.
- `git grep -n "api_key" src/sdlc/models.py` returns nothing.
- `src/sdlc/workflows/feature.py` and `src/sdlc/workflows/reflect.py` unchanged: `git diff --stat main -- src/sdlc/workflows/` is empty.
