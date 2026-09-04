# E-38 Capture-Always Harness Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every harness run emits a canonical, scrubbed, claim-checked `HarnessSession` transcript (full JSONL as an `ArtifactRef`, waste-aggregate `SessionDigest` inline on `HarnessRunResult`), with retro-time retention downgrade and a minimal env-gated Logfire slice.

**Architecture:** Adapters normalise their own stdout streams into a canonical schema (claude switches to `stream-json`); the `run_coding_task` activity runs capture → scrub (fail-closed) → digest → store via a new `ArtifactStore` seam (`file://` backend under the E-32 export root); the workflow collects refs and a retro-time activity deletes full transcripts for clean-green non-benchmark runs. Spec: `docs/superpowers/specs/2026-07-23-capture-always-harness-sessions-design.md`.

**Tech Stack:** Python 3.11+, Pydantic v2, Temporal Python SDK, pytest, logfire (optional dep).

## Global Constraints

- The full `HarnessSession` **never enters workflow state** — only `ArtifactRef` + `SessionDigest` do. Raw stdout travels on a pydantic `PrivateAttr` (excluded from serialization) and only within the activity.
- Scrub is **fail-closed w.r.t. storage**: any exception during normalise/scrub → nothing written to disk, `session_ref=None`, `session_digest=None` — but the coding task itself still succeeds.
- The raw (unscrubbed) stdout is never written to disk and never reaches Logfire. Logfire span attributes: counts, durations, sizes, ids only.
- Digest `decision_skeleton` cap: `SKELETON_MAX = 200` entries.
- Retention policy (OQ-B7, decided): delete full transcript iff `outcome.startswith("deployed")` ∧ no fix attempt > 1 ∧ `cfg.benchmark.case_id is None`. Digest is always kept. TTL stays out of scope.
- Benchmark-run detection: `cfg.benchmark.case_id is not None` (`models.py:397` — `case_id=None => not a benchmark run`). Do NOT add a new flag.
- New `CodingTaskInput` fields must have defaults (Temporal replay compatibility).
- Store root env var: `SDLC_ARTIFACT_ROOT`, falling back to `SDLC_EXPORT_ROOT`, then `./runs` (mirrors `observability/activities.py:25`).
- All tests run with `python -m pytest <file> -v` from repo root (Windows worker; paths via `pathlib`).

---

### Task 1: Session models + `digest_of`

**Files:**
- Modify: `src/sdlc/models.py` (after `ArtifactRef` ~line 58 and inside `HarnessRunResult` ~line 153)
- Create: `src/sdlc/harness/session.py`
- Test: `tests/test_session_models.py`

**Interfaces:**
- Produces: `models.SessionEvent`, `models.HarnessSession`, `models.SessionDigest`; `HarnessRunResult.session_ref: ArtifactRef | None`, `HarnessRunResult.session_digest: SessionDigest | None`, `HarnessRunResult._raw_stdout: str` (PrivateAttr); `harness.session.digest_of(session) -> SessionDigest`, `harness.session.scrub_session(session) -> HarnessSession`, `harness.session.session_to_jsonl(session) -> str`, `harness.session.SKELETON_MAX = 200`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session_models.py
"""E-38: canonical HarnessSession / SessionDigest models + pure helpers."""

import json

from sdlc.models import (
    ArtifactRef,
    HarnessKind,
    HarnessRunResult,
    HarnessSession,
    SessionDigest,
    SessionEvent,
)
from sdlc.harness.session import SKELETON_MAX, digest_of, scrub_session, session_to_jsonl


def _session(events):
    return HarnessSession(
        harness=HarnessKind.CLAUDE_CODE, session_id="s1", model="opus", events=events
    )


def test_run_result_gains_session_fields_defaulting_none():
    r = HarnessRunResult(harness=HarnessKind.CLAUDE_CODE, exit_code=0, summary="ok")
    assert r.session_ref is None
    assert r.session_digest is None


def test_raw_stdout_private_attr_never_serialized():
    r = HarnessRunResult(harness=HarnessKind.CLAUDE_CODE, exit_code=0, summary="ok")
    r._raw_stdout = "SECRET STREAM"
    assert "_raw_stdout" not in r.model_dump()
    assert "SECRET STREAM" not in r.model_dump_json()


def test_digest_counts_waste_aggregates():
    ev = [
        SessionEvent(kind="model_turn", text="thinking"),
        SessionEvent(kind="file_read", tool="Read", target="a.py"),
        SessionEvent(kind="file_read", tool="Read", target="a.py"),  # re-read
        SessionEvent(kind="file_write", tool="Write", target="b.py"),
        SessionEvent(kind="file_write", tool="Edit", target="b.py"),  # churn
        SessionEvent(kind="command", tool="Bash", target="pytest", exit_code=1),
        SessionEvent(kind="command", tool="Bash", target="pytest", exit_code=0),
        SessionEvent(kind="compaction"),
    ]
    d = digest_of(_session(ev))
    assert d.tool_calls == 6  # every tool-bearing event
    assert d.file_reads == 2
    assert d.file_rereads == 1  # a.py read twice -> 1 extra read
    assert d.files_written == 1  # distinct paths written
    assert d.rewrite_churn == 1  # b.py written twice
    assert d.failed_commands == 1
    assert d.model_turns == 1
    assert d.compacted is True
    assert d.decision_skeleton[0] == "Read a.py"
    assert len(d.decision_skeleton) == 6  # only tool-bearing events, in order


def test_digest_skeleton_capped():
    ev = [
        SessionEvent(kind="file_read", tool="Read", target=f"f{i}.py")
        for i in range(SKELETON_MAX + 50)
    ]
    d = digest_of(_session(ev))
    assert len(d.decision_skeleton) == SKELETON_MAX


def test_scrub_session_redacts_text_and_target():
    ev = [
        SessionEvent(
            kind="command",
            tool="Bash",
            target="export KEY=sk-abcdefghijklmnopqrstuv",
            text="password: hunter2hunter2",
        )
    ]
    s = scrub_session(_session(ev))
    assert "sk-abcdefghijklmnop" not in (s.events[0].target or "")
    assert "hunter2" not in (s.events[0].text or "")


def test_session_to_jsonl_header_plus_one_line_per_event():
    ev = [
        SessionEvent(kind="model_turn", text="hi"),
        SessionEvent(kind="file_read", tool="Read", target="a.py"),
    ]
    lines = session_to_jsonl(_session(ev)).strip().splitlines()
    assert len(lines) == 3
    head = json.loads(lines[0])
    assert head["session_id"] == "s1" and "events" not in head
    assert json.loads(lines[1])["kind"] == "model_turn"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_session_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'HarnessSession'`

- [ ] **Step 3: Add models to `src/sdlc/models.py`**

Insert after `ArtifactRef` (keep comment style of the file):

```python
class SessionEvent(BaseModel):
    """One normalised harness-transcript event (ADR-16). Harness-agnostic;
    adapters map their native streams onto this schema."""

    kind: str  # model_turn | tool_call | tool_result | file_read
    # | file_write | command | compaction | result
    tool: str | None = None
    target: str | None = None  # file path or command line (scrubbed)
    exit_code: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    text: str | None = None  # payload (scrubbed)


class HarnessSession(BaseModel):
    """Canonical transcript of one harness run (ADR-16). NEVER enters
    workflow state — serialized to JSONL and claim-checked (E-38)."""

    harness: HarnessKind
    session_id: str | None = None
    model: str | None = None
    events: list[SessionEvent] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class SessionDigest(BaseModel):
    """BENCHMARK §4.3 waste aggregates + decision-skeleton. Small and
    bounded — travels inline on HarnessRunResult; always kept, even when
    the full transcript is downgraded at retro (OQ-B7)."""

    tool_calls: int = 0
    file_reads: int = 0
    file_rereads: int = 0  # same path read more than once
    files_written: int = 0  # distinct paths written
    rewrite_churn: int = 0  # paths written more than once
    failed_commands: int = 0  # command events with exit_code not in (0, None)
    model_turns: int = 0
    compacted: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    decision_skeleton: list[str] = Field(default_factory=list)
```

`HarnessKind` is defined above `HarnessRunResult`; if `SessionEvent`/`HarnessSession` land before it, place them *after* `HarnessKind`'s definition instead — they reference it.

In `HarnessRunResult`, add fields + private attr (import `PrivateAttr` from pydantic at top of file):

```python
compacted: bool = False  # harness signalled a mid-run compaction
# E-38 (ADR-16): full scrubbed transcript as a claim-checked ref; waste
# digest inline. The raw stdout rides a PrivateAttr so it can never
# serialize into workflow state.
session_ref: ArtifactRef | None = None
session_digest: SessionDigest | None = None
_raw_stdout: str = PrivateAttr(default="")
```

- [ ] **Step 4: Create `src/sdlc/harness/session.py`**

```python
"""Pure session helpers (E-38/ADR-16): waste digest, scrub, JSONL render.

No IO, no Temporal — activity code composes these; tests hit them directly.
"""

from __future__ import annotations

from collections import Counter

from ..memory.scrub import scrub
from ..models import HarnessSession, SessionDigest, SessionEvent

SKELETON_MAX = 200

_TOOL_KINDS = {"tool_call", "tool_result", "file_read", "file_write", "command"}


def digest_of(session: HarnessSession) -> SessionDigest:
    """BENCHMARK §4.3 aggregates, computed pre-truncation so they exist for
    every run — including clean-green runs whose full transcript is later
    downgraded (OQ-B7)."""
    reads: Counter[str] = Counter()
    writes: Counter[str] = Counter()
    d = SessionDigest(input_tokens=session.input_tokens, output_tokens=session.output_tokens)
    skeleton: list[str] = []
    for ev in session.events:
        if ev.kind in _TOOL_KINDS:
            d.tool_calls += 1
        if ev.kind == "file_read" and ev.target:
            d.file_reads += 1
            reads[ev.target] += 1
        elif ev.kind == "file_write" and ev.target:
            writes[ev.target] += 1
        elif ev.kind == "command" and ev.exit_code not in (0, None):
            d.failed_commands += 1
        elif ev.kind == "model_turn":
            d.model_turns += 1
        elif ev.kind == "compaction":
            d.compacted = True
        if ev.kind in _TOOL_KINDS and len(skeleton) < SKELETON_MAX:
            skeleton.append(f"{ev.tool or ev.kind} {ev.target or ''}".strip())
    d.file_rereads = sum(n - 1 for n in reads.values() if n > 1)
    d.files_written = len(writes)
    d.rewrite_churn = sum(1 for n in writes.values() if n > 1)
    d.decision_skeleton = skeleton
    return d


def scrub_session(session: HarnessSession) -> HarnessSession:
    """Apply the memory scrub to every payload-bearing field. Raises on
    internal failure — the caller (capture) is fail-closed and stores
    nothing in that case."""
    events = [
        ev.model_copy(
            update={
                "text": scrub(ev.text) if ev.text else ev.text,
                "target": scrub(ev.target) if ev.target else ev.target,
            }
        )
        for ev in session.events
    ]
    return session.model_copy(update={"events": events})


def session_to_jsonl(session: HarnessSession) -> str:
    """Header line (session metadata, no events) + one event per line —
    same idiom as events.jsonl (E-32)."""
    head = session.model_dump_json(exclude={"events"})
    lines = [head] + [ev.model_dump_json() for ev in session.events]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_session_models.py -v`
Expected: 6 PASS. Also run `python -m pytest tests/test_harness_result.py tests/test_module_imports.py -v` — must stay green.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py src/sdlc/harness/session.py tests/test_session_models.py
git commit -m "feat(session): canonical HarnessSession/SessionDigest + pure helpers (E-38)"
```

---

### Task 2: `ArtifactStore` seam with `LocalFileStore`

**Files:**
- Create: `src/sdlc/artifacts/__init__.py` (empty)
- Create: `src/sdlc/artifacts/store.py`
- Test: `tests/test_artifact_store.py`

**Interfaces:**
- Consumes: `models.ArtifactRef`
- Produces: `artifacts.store.ArtifactStore` (Protocol: `put(kind, run_id, name, data: bytes) -> ArtifactRef`, `delete(ref) -> None`), `artifacts.store.LocalFileStore(root=None)`, `artifacts.store.ref_to_path(ref) -> Path`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_artifact_store.py
"""E-38: first real claim-check store (file:// backend behind a seam)."""

import hashlib

from sdlc.artifacts.store import LocalFileStore, ref_to_path


def test_put_writes_under_run_sessions_dir(tmp_path):
    store = LocalFileStore(root=tmp_path)
    ref = store.put("harness_session", "run-1", "t1-a1.jsonl", b"hello\n")
    assert ref.kind == "harness_session"
    assert ref.uri.startswith("file://")
    p = tmp_path / "run-1" / "sessions" / "t1-a1.jsonl"
    assert p.read_bytes() == b"hello\n"
    assert ref.sha256 == hashlib.sha256(b"hello\n").hexdigest()


def test_digest_kind_lands_beside_full(tmp_path):
    store = LocalFileStore(root=tmp_path)
    store.put("harness_session_digest", "run-1", "t1-a1.digest.json", b"{}")
    assert (tmp_path / "run-1" / "sessions" / "t1-a1.digest.json").exists()


def test_ref_round_trips_to_path_and_delete(tmp_path):
    store = LocalFileStore(root=tmp_path)
    ref = store.put("harness_session", "run-1", "t1-a1.jsonl", b"x")
    assert ref_to_path(ref).read_bytes() == b"x"
    store.delete(ref)
    assert not ref_to_path(ref).exists()
    store.delete(ref)  # idempotent — second delete is a no-op


def test_env_root_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path / "art"))
    store = LocalFileStore()
    ref = store.put("harness_session", "r", "n.jsonl", b"y")
    assert (tmp_path / "art" / "r" / "sessions" / "n.jsonl").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_artifact_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.artifacts'`

- [ ] **Step 3: Implement `src/sdlc/artifacts/store.py`** (and an empty `__init__.py`)

```python
"""Claim-check artifact store (E-38, first FR-702 consumer).

One seam, one backend: LocalFileStore writes beside the E-32 export root.
S3 becomes a second backend behind the same Protocol when it earns its
keep. Layout: <root>/<run_id>/<subdir>/<name>; sessions and their digests
share a subdir so a human can `ls` one run's transcripts.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import url2pathname

from ..models import ArtifactRef

_SUBDIRS = {
    "harness_session": "sessions",
    "harness_session_digest": "sessions",
}


def ref_to_path(ref: ArtifactRef) -> Path:
    """file:// URI -> local Path (Windows-safe: file:///D:/x -> D:\\x)."""
    return Path(url2pathname(urlparse(ref.uri).path))


class ArtifactStore(Protocol):
    def put(self, kind: str, run_id: str, name: str, data: bytes) -> ArtifactRef: ...
    def delete(self, ref: ArtifactRef) -> None: ...


class LocalFileStore:
    def __init__(self, root: str | os.PathLike | None = None):
        self.root = Path(
            root
            or os.environ.get("SDLC_ARTIFACT_ROOT")
            or os.environ.get("SDLC_EXPORT_ROOT", "./runs")
        )

    def put(self, kind: str, run_id: str, name: str, data: bytes) -> ArtifactRef:
        path = self.root / run_id / _SUBDIRS.get(kind, kind) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return ArtifactRef(
            kind=kind, uri=path.resolve().as_uri(), sha256=hashlib.sha256(data).hexdigest()
        )

    def delete(self, ref: ArtifactRef) -> None:
        ref_to_path(ref).unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_artifact_store.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/artifacts/ tests/test_artifact_store.py
git commit -m "feat(artifacts): ArtifactStore seam + LocalFileStore file:// backend (E-38)"
```

---

### Task 3: claude adapter — `stream-json` + normaliser

**Files:**
- Modify: `src/sdlc/harness/adapters.py` (`ClaudeCodeHarness.build_cmd` ~line 227, `.parse` ~line 240; base `CodingHarness` gains `normalise_session` default + `run()` sets `_raw_stdout` ~line 203)
- Test: `tests/test_claude_stream_normalise.py`
- Modify: `tests/test_harness_parse.py` (existing claude parse fixtures move to stream-json shape)

**Interfaces:**
- Consumes: `models.HarnessSession`, `models.SessionEvent`
- Produces: `CodingHarness.normalise_session(stdout: str) -> HarnessSession` (base default: empty-events session); claude `build_cmd` emits `--output-format stream-json --verbose`; claude `parse()` reads the `result` event from the stream; `run()` sets `result._raw_stdout`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_claude_stream_normalise.py
"""E-38: claude stream-json -> canonical HarnessSession."""

import json

from sdlc.harness.adapters import ClaudeCodeHarness, HarnessRequest

STREAM = "\n".join(
    [
        json.dumps(
            {"type": "system", "subtype": "init", "session_id": "abc", "model": "claude-opus-4-8"}
        ),
        json.dumps(
            {
                "type": "assistant",
                "session_id": "abc",
                "message": {"content": [{"type": "text", "text": "I'll read the file."}]},
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "session_id": "abc",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "src/app.py"}}
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "user",
                "session_id": "abc",
                "message": {"content": [{"type": "tool_result", "content": "def app(): ..."}]},
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "session_id": "abc",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Write", "input": {"file_path": "src/out.py"}}
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "session_id": "abc",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}}
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "user",
                "session_id": "abc",
                "message": {
                    "content": [{"type": "tool_result", "content": "1 failed", "is_error": True}]
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "session_id": "abc",
                "total_cost_usd": 0.12,
                "result": "done",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
        ),
    ]
)


def test_build_cmd_uses_stream_json_with_verbose():
    cmd = ClaudeCodeHarness().build_cmd(HarnessRequest(prompt="p", cwd="."))
    assert "stream-json" in cmd
    assert "--verbose" in cmd
    assert "json" not in [a for a in cmd if a == "json"]  # plain json gone


def test_parse_reads_result_event_from_stream():
    r = ClaudeCodeHarness().parse(STREAM, 0)
    assert r.session_id == "abc"
    assert r.cost_usd == 0.12
    assert r.input_tokens == 100 and r.output_tokens == 50
    assert r.summary == "done"


def test_normalise_maps_tools_onto_canonical_kinds():
    s = ClaudeCodeHarness().normalise_session(STREAM)
    kinds = [e.kind for e in s.events]
    assert s.session_id == "abc" and s.model == "claude-opus-4-8"
    assert kinds == [
        "model_turn",
        "file_read",
        "tool_result",
        "file_write",
        "command",
        "tool_result",
        "result",
    ]
    read = s.events[1]
    assert read.tool == "Read" and read.target == "src/app.py"
    bash = s.events[4]
    assert bash.tool == "Bash" and bash.target == "pytest -q"
    err = s.events[5]
    assert err.exit_code == 1  # is_error -> exit_code 1
    assert s.cost_usd == 0.12


def test_normalise_tolerates_garbage_lines():
    s = ClaudeCodeHarness().normalise_session("not json\n" + STREAM)
    assert len(s.events) == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_claude_stream_normalise.py -v`
Expected: FAIL — no `--verbose`/`stream-json` in cmd; `normalise_session` missing; `parse` reads last line only (last line IS the result event here, so `test_parse_reads_result_event_from_stream` may already pass — that's fine).

- [ ] **Step 3: Implement in `adapters.py`**

Base class — add default normaliser and keep raw stdout (in `run()`, right after `result = self.parse(...)`):

```python
    def normalise_session(self, stdout: str) -> HarnessSession:
        """Canonical transcript from this harness's stdout stream (ADR-16:
        normalisation is the adapter's job). Base default: metadata-only
        session with no events — a harness without a normaliser degrades
        to digest-of-nothing rather than failing capture."""
        return HarnessSession(harness=self.kind)
```

```python
result = self.parse(stdout_b.decode(errors="replace"), proc.returncode or 0)
# E-38: keep the raw stream for activity-side capture. PrivateAttr —
# never serialized, never enters workflow state.
result._raw_stdout = stdout_b.decode(errors="replace")
```

(Import `HarnessSession`, `SessionEvent` from `..models` at top.)

`ClaudeCodeHarness.build_cmd` — replace the output-format pair:

```python
cmd = [
    "claude",
    "-p",
    req.prompt,
    # E-38: stream-json emits the full event stream (transcript
    # source) AND a final `result` event with the same fields the
    # old plain-json payload carried. --verbose is required by the
    # CLI for stream-json in print mode.
    "--output-format",
    "stream-json",
    "--verbose",
    "--allowedTools",
    self.allowed_tools,
    "--permission-mode",
    self.permission_mode,
]
```

`ClaudeCodeHarness.parse` — walk lines, find the `result` event (fall back to raw stdout as summary exactly as today):

```python
def parse(self, stdout: str, exit_code: int) -> HarnessRunResult:
    session_id = cost = summary = None
    input_tokens = output_tokens = None
    payload = None
    for ln in stdout.strip().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict) and ev.get("type") == "result":
            payload = ev
    if payload is not None:
        session_id = payload.get("session_id")
        cost = payload.get("total_cost_usd")
        summary = payload.get("result") or payload.get("content")
        usage = payload.get("usage") or {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
    else:
        _log.warning(
            "claude parse: no result event in stream, falling back to raw stdout as summary"
        )
        summary = stdout
    return HarnessRunResult(
        harness=self.kind,
        session_id=session_id,
        exit_code=exit_code,
        summary=(summary or "")[:SUMMARY_MAX],
        cost_usd=cost,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
```

`ClaudeCodeHarness.normalise_session`:

```python
# tool name -> canonical event kind + which input field is the target
_TOOL_MAP = {
    "Read": ("file_read", "file_path"),
    "Write": ("file_write", "file_path"),
    "Edit": ("file_write", "file_path"),
    "Bash": ("command", "command"),
}


def normalise_session(self, stdout: str) -> HarnessSession:
    events: list[SessionEvent] = []
    session_id = model = None
    cost = in_tok = out_tok = None
    for ln in stdout.strip().splitlines():
        try:
            ev = json.loads(ln.strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        session_id = session_id or ev.get("session_id")
        etype = ev.get("type")
        if etype == "system":
            model = model or ev.get("model")
        elif etype in ("assistant", "user"):
            msg = ev.get("message") or {}
            for block in msg.get("content") or []:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text" and block.get("text"):
                    events.append(SessionEvent(kind="model_turn", text=block["text"]))
                elif btype == "tool_use":
                    name = block.get("name") or "tool"
                    kind, field = self._TOOL_MAP.get(name, ("tool_call", ""))
                    inp = block.get("input") or {}
                    target = inp.get(field) if field else json.dumps(inp)[:500]
                    events.append(SessionEvent(kind=kind, tool=name, target=target))
                elif btype == "tool_result":
                    content = block.get("content")
                    if isinstance(content, list):
                        content = " ".join(
                            c.get("text", "") for c in content if isinstance(c, dict)
                        )
                    events.append(
                        SessionEvent(
                            kind="tool_result",
                            exit_code=1 if block.get("is_error") else None,
                            text=(content or "")[:2000] or None,
                        )
                    )
        elif etype == "result":
            usage = ev.get("usage") or {}
            cost = ev.get("total_cost_usd")
            in_tok = usage.get("input_tokens")
            out_tok = usage.get("output_tokens")
            events.append(SessionEvent(kind="result", text=(ev.get("result") or "")[:2000]))
    return HarnessSession(
        harness=self.kind,
        session_id=session_id,
        model=model,
        events=events,
        cost_usd=cost,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )
```

- [ ] **Step 4: Update `tests/test_harness_parse.py` claude fixtures**

Read the file; any claude fixture that is a single plain-JSON payload still parses (a bare `{"type": ...}`-less dict has no `result` event → falls back to raw-stdout summary). Update those fixtures to a one-line stream: wrap the old payload as `{"type": "result", **old_payload}` so assertions on `session_id`/`cost` keep their meaning. Assert `build_cmd` expectations there too if the file checks the old `--output-format json`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_claude_stream_normalise.py tests/test_harness_parse.py tests/test_harness_observability.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/harness/adapters.py tests/test_claude_stream_normalise.py tests/test_harness_parse.py
git commit -m "feat(harness): claude stream-json capture + canonical normaliser (E-38)"
```

---

### Task 4: opencode normaliser

**Files:**
- Modify: `src/sdlc/harness/adapters.py` (`OpenCodeHarness`)
- Test: `tests/test_opencode_normalise.py`

**Interfaces:**
- Consumes: base `normalise_session` contract from Task 3
- Produces: `OpenCodeHarness.normalise_session(stdout) -> HarnessSession`

**Spec verification item:** if `opencode` is on PATH, run `opencode run --format json "read README.md and summarize"` in a scratch dir once and inspect which tool-level event types the stream carries (look for `type: "tool"` / `part.tool`); extend `_normalise_tool_event` accordingly and paste the real line shapes into the test fixture. If unavailable, ship the mapping below (step_start/step_finish/text are confirmed by the existing `parse()`); the normaliser is best-effort per harness — the canonical schema is the contract.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_opencode_normalise.py
"""E-38: opencode --format json event stream -> canonical HarnessSession."""

import json

from sdlc.harness.adapters import OpenCodeHarness

STREAM = "\n".join(
    [
        json.dumps({"type": "step_start", "sessionID": "oc1"}),
        json.dumps({"type": "text", "sessionID": "oc1", "part": {"text": "Working on it."}}),
        json.dumps(
            {
                "type": "tool",
                "sessionID": "oc1",
                "part": {
                    "tool": "read",
                    "state": {"input": {"filePath": "src/app.py"}, "status": "completed"},
                },
            }
        ),
        json.dumps(
            {
                "type": "tool",
                "sessionID": "oc1",
                "part": {
                    "tool": "bash",
                    "state": {"input": {"command": "pytest -q"}, "status": "error"},
                },
            }
        ),
        json.dumps(
            {
                "type": "step_finish",
                "sessionID": "oc1",
                "part": {"tokens": {"input": 10, "output": 5}, "cost": 0.01},
            }
        ),
    ]
)


def test_normalise_maps_stream_onto_canonical_kinds():
    s = OpenCodeHarness().normalise_session(STREAM)
    assert s.session_id == "oc1"
    kinds = [e.kind for e in s.events]
    assert kinds == ["model_turn", "file_read", "command"]
    assert s.events[1].target == "src/app.py"
    assert s.events[2].target == "pytest -q"
    assert s.events[2].exit_code == 1  # status: error -> failed command
    assert s.input_tokens == 10 and s.output_tokens == 5
    assert s.cost_usd == 0.01


def test_normalise_empty_stream_yields_empty_session():
    s = OpenCodeHarness().normalise_session("")
    assert s.events == [] and s.session_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_opencode_normalise.py -v`
Expected: FAIL — base default returns empty events for the populated stream

- [ ] **Step 3: Implement `OpenCodeHarness.normalise_session`**

```python
# opencode tool name -> canonical kind + target field in state.input
_TOOL_MAP = {
    "read": ("file_read", "filePath"),
    "write": ("file_write", "filePath"),
    "edit": ("file_write", "filePath"),
    "bash": ("command", "command"),
}


def normalise_session(self, stdout: str) -> HarnessSession:
    events: list[SessionEvent] = []
    session_id = None
    in_tok = out_tok = 0
    cost = 0.0
    saw_tokens = saw_cost = False
    for ln in stdout.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        session_id = session_id or ev.get("sessionID") or ev.get("session_id")
        part = ev.get("part") or {}
        etype = ev.get("type")
        if etype == "text" and part.get("text"):
            events.append(SessionEvent(kind="model_turn", text=part["text"][:2000]))
        elif etype == "tool":
            name = (part.get("tool") or "tool").lower()
            kind, field = self._TOOL_MAP.get(name, ("tool_call", ""))
            state = part.get("state") or {}
            inp = state.get("input") or {}
            target = inp.get(field) if field else json.dumps(inp)[:500]
            events.append(
                SessionEvent(
                    kind=kind,
                    tool=name,
                    target=target,
                    exit_code=1 if state.get("status") == "error" else None,
                )
            )
        elif etype == "step_finish":
            tokens = part.get("tokens") or {}
            if isinstance(tokens.get("input"), (int, float)):
                in_tok += tokens["input"]
                saw_tokens = True
            if isinstance(tokens.get("output"), (int, float)):
                out_tok += tokens["output"]
                saw_tokens = True
            if isinstance(part.get("cost"), (int, float)):
                cost += part["cost"]
                saw_cost = True
    return HarnessSession(
        harness=self.kind,
        session_id=session_id,
        events=events,
        input_tokens=in_tok if saw_tokens else None,
        output_tokens=out_tok if saw_tokens else None,
        cost_usd=cost if saw_cost else None,
    )
```

Note the digest counts a `command` event with `exit_code=1` as failed — the opencode `status: "error"` maps onto the same signal claude's `is_error` does.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_opencode_normalise.py tests/test_harness_parse.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/harness/adapters.py tests/test_opencode_normalise.py
git commit -m "feat(harness): opencode normaliser onto canonical session schema (E-38)"
```

---

### Task 5: capture pipeline in `run_coding_task`

**Files:**
- Create: `src/sdlc/artifacts/capture.py`
- Modify: `src/sdlc/activities.py` (`CodingTaskInput` ~line 371, `run_coding_task` ~line 382)
- Modify: `src/sdlc/workflows/feature.py:570` (pass `task_id`/`attempt`)
- Test: `tests/test_session_capture.py`

**Interfaces:**
- Consumes: Task 1 helpers (`scrub_session`, `digest_of`, `session_to_jsonl`), Task 2 store, Task 3/4 `normalise_session`
- Produces: `artifacts.capture.capture_session(harness, raw_stdout, run_id, task_id, attempt) -> tuple[ArtifactRef | None, SessionDigest | None]`; `CodingTaskInput.task_id: str = "task"`, `CodingTaskInput.attempt: int = 1`; `run_coding_task` returns results with `session_ref`/`session_digest` set.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session_capture.py
"""E-38: capture -> scrub (fail-closed) -> digest -> store."""

import json

import pytest

from sdlc.artifacts.capture import capture_session
from sdlc.artifacts.store import ref_to_path
from sdlc.harness.adapters import ClaudeCodeHarness

STREAM = "\n".join(
    [
        json.dumps(
            {
                "type": "assistant",
                "session_id": "abc",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "export K=sk-abcdefghijklmnopqrstuv"},
                        }
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "session_id": "abc",
                "result": "done",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        ),
    ]
)


def test_capture_stores_scrubbed_jsonl_and_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    ref, dig = capture_session(ClaudeCodeHarness(), STREAM, run_id="r1", task_id="t1", attempt=1)
    assert ref is not None and ref.kind == "harness_session"
    stored = ref_to_path(ref).read_text(encoding="utf-8")
    assert "sk-abcdefghijklmnop" not in stored  # scrub effectiveness
    assert "[REDACTED_API_KEY]" in stored
    assert dig.tool_calls == 1
    assert (tmp_path / "r1" / "sessions" / "t1-a1.digest.json").exists()


def test_capture_fail_closed_stores_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "sdlc.artifacts.capture.scrub_session",
        lambda s: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    ref, dig = capture_session(ClaudeCodeHarness(), STREAM, run_id="r1", task_id="t1", attempt=1)
    assert ref is None and dig is None
    assert not (tmp_path / "r1").exists()  # nothing on disk


def test_capture_sanitizes_task_id(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    ref, _ = capture_session(
        ClaudeCodeHarness(), STREAM, run_id="r1", task_id="T/1: setup", attempt=2
    )
    assert ref_to_path(ref).name == "T_1__setup-a2.jsonl"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_session_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: sdlc.artifacts.capture`

- [ ] **Step 3: Implement `src/sdlc/artifacts/capture.py`**

```python
"""Session capture pipeline (E-38): normalise -> scrub (fail-closed) ->
digest (pre-truncation) -> store full JSONL + digest JSON.

Fail-closed w.r.t. STORAGE: any failure here stores nothing and returns
(None, None) — the coding task itself must still succeed (an observability
bug must not block delivery; SC-5-style strictness applies to what gets
stored). Ordering is strict: scrub runs before any byte touches disk.
"""

from __future__ import annotations

import logging
import re

from ..harness.adapters import CodingHarness
from ..harness.session import digest_of, scrub_session, session_to_jsonl
from ..models import ArtifactRef, SessionDigest
from .store import LocalFileStore

_log = logging.getLogger(__name__)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def capture_session(
    harness: CodingHarness,
    raw_stdout: str,
    run_id: str,
    task_id: str,
    attempt: int,
) -> tuple[ArtifactRef | None, SessionDigest | None]:
    try:
        session = harness.normalise_session(raw_stdout)
        session = scrub_session(session)  # fail-closed: before any put
        digest = digest_of(session)  # pre-truncation (OQ-B7)
        store = LocalFileStore()
        name = f"{_safe(task_id)}-a{attempt}"
        ref = store.put(
            "harness_session", run_id, f"{name}.jsonl", session_to_jsonl(session).encode("utf-8")
        )
        store.put(
            "harness_session_digest",
            run_id,
            f"{name}.digest.json",
            digest.model_dump_json(indent=2).encode("utf-8"),
        )
        return ref, digest
    except Exception:
        _log.warning("session capture failed — nothing stored (fail-closed)", exc_info=True)
        return None, None
```

- [ ] **Step 4: Wire into `run_coding_task`**

In `activities.py`, extend the input (defaults keep old histories replayable):

```python
@dataclass
class CodingTaskInput:
    harness: HarnessKind
    prompt: str
    worktree: str
    model: str | None = None
    session_id: str | None = None
    timeout_s: int = 3600
    task_id: str = "task"  # E-38: session artifact naming
    attempt: int = 1
```

After `result = await harness.run(...)` (before the checkpoint-commit block), add:

```python
# E-38: capture the transcript. Raw stdout rides a PrivateAttr — it
# exists only inside this activity and is never written unscrubbed.
ref, digest = capture_session(
    harness,
    result._raw_stdout,
    run_id=activity.info().workflow_run_id,
    task_id=inp.task_id,
    attempt=inp.attempt,
)
result.session_ref = ref
result.session_digest = digest
```

Import `capture_session` from `.artifacts.capture` at the top of `activities.py`.

In `feature.py:570`, pass the new fields:

```python
(
    CodingTaskInput(
        harness=role_cfg.harness,
        prompt=prompt,
        worktree=worktree,
        model=role_cfg.model,
        session_id=session_id,
        task_id=task.id,
        attempt=attempt,
    ),
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_session_capture.py tests/test_coding_task_checkpoint.py tests/test_env_allowlist.py -v`
Expected: all PASS (checkpoint/allowlist tests exercise `run_coding_task` with fakes; capture's fail-closed catch absorbs fakes that lack `_raw_stdout` content)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/artifacts/capture.py src/sdlc/activities.py src/sdlc/workflows/feature.py tests/test_session_capture.py
git commit -m "feat(activities): capture-always session pipeline in run_coding_task (E-38)"
```

---

### Task 6: retention activity + retro wiring + worker registration

**Files:**
- Create: `src/sdlc/artifacts/retention.py`
- Modify: `src/sdlc/workflows/feature.py` (state init near the trace comment ~line 234; ref collection in `_dev_task` after the `run_coding_task` call ~line 574; retro terminal block after `export_run_artifacts` ~line 766; imports in the passed-through block ~line 50)
- Modify: `src/sdlc/worker.py` (imports ~line 45, activities list ~line 81)
- Test: `tests/test_session_retention.py`

**Interfaces:**
- Consumes: Task 2 store (`LocalFileStore.delete`), `models.ArtifactRef`
- Produces: `artifacts.retention.keep_full_transcripts(outcome: str, had_fix_attempts: bool, is_benchmark: bool) -> bool` (pure — callable from workflow code); `artifacts.retention.RetentionInput(refs: list[ArtifactRef], keep_full: bool)`; activity `artifacts.retention.apply_session_retention(inp) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session_retention.py
"""E-38/OQ-B7: full transcript deleted only on clean-green non-benchmark."""

import pytest

from sdlc.artifacts.retention import RetentionInput, apply_session_retention, keep_full_transcripts
from sdlc.artifacts.store import LocalFileStore, ref_to_path


@pytest.mark.parametrize(
    "outcome,had_fix,is_bench,expected",
    [
        ("deployed:staging", False, False, False),  # clean-green -> downgrade
        ("deployed:staging", True, False, True),  # green after retry -> keep
        ("deployed:staging", False, True, True),  # benchmark -> keep
        ("rejected:merge", False, False, True),  # failed -> keep
        ("rejected:merge", True, True, True),
    ],
)
def test_keep_full_transcripts_matrix(outcome, had_fix, is_bench, expected):
    assert keep_full_transcripts(outcome, had_fix, is_bench) is expected


@pytest.mark.asyncio
async def test_retention_deletes_full_keeps_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    store = LocalFileStore()
    ref = store.put("harness_session", "r1", "t1-a1.jsonl", b"full")
    store.put("harness_session_digest", "r1", "t1-a1.digest.json", b"{}")
    out = await apply_session_retention(RetentionInput(refs=[ref], keep_full=False))
    assert not ref_to_path(ref).exists()
    assert (tmp_path / "r1" / "sessions" / "t1-a1.digest.json").exists()
    assert out == "downgraded:1"


@pytest.mark.asyncio
async def test_retention_keep_full_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_ARTIFACT_ROOT", str(tmp_path))
    store = LocalFileStore()
    ref = store.put("harness_session", "r1", "t1-a1.jsonl", b"full")
    out = await apply_session_retention(RetentionInput(refs=[ref], keep_full=True))
    assert ref_to_path(ref).exists()
    assert out == "kept:1"
```

(Check `pyproject.toml`/`conftest.py` for the async test plugin already used by activity tests — `test_export_activity.py` is the model; mirror its idiom if it differs from `pytest.mark.asyncio`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_session_retention.py -v`
Expected: FAIL — `ModuleNotFoundError: sdlc.artifacts.retention`

- [ ] **Step 3: Implement `src/sdlc/artifacts/retention.py`**

```python
"""Retro-time session retention (E-38, OQ-B7 decided half).

Full transcript is kept on fail / benchmark / any fix-loop retry — "green
after a retry" keeps full, because HOW the agent recovered is the point.
Only clean-green non-benchmark runs are downgraded to digest-only. The
digest file is never deleted. TTL on kept transcripts stays open (OQ-B7).
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from temporalio import activity

from ..models import ArtifactRef

_log = logging.getLogger(__name__)


def keep_full_transcripts(outcome: str, had_fix_attempts: bool, is_benchmark: bool) -> bool:
    """Pure policy — called from workflow code, so: no IO, no env."""
    clean_green = outcome.startswith("deployed") and not had_fix_attempts
    return is_benchmark or not clean_green


class RetentionInput(BaseModel):
    refs: list[ArtifactRef] = Field(default_factory=list)
    keep_full: bool


@activity.defn
async def apply_session_retention(inp: RetentionInput) -> str:
    if inp.keep_full:
        return f"kept:{len(inp.refs)}"
    from .store import LocalFileStore

    store = LocalFileStore()
    for ref in inp.refs:
        store.delete(ref)  # digests are not in refs — never deleted
    return f"downgraded:{len(inp.refs)}"
```

- [ ] **Step 4: Wire into `feature.py`**

Imports (inside the existing `workflow.unsafe.imports_passed_through()` block near line 50):

```python
from ..artifacts.retention import RetentionInput, apply_session_retention, keep_full_transcripts
```

State init — beside the E-32 trace comment (~line 234):

```python
        # E-38: session refs collected per coding attempt; retro applies
        # the OQ-B7 retention policy over them.
        self._session_refs: list[ArtifactRef] = []
```

(`ArtifactRef` is already importable from `..models` there; add it to that import if missing.)

In `_dev_task`, right after the `run_coding_task` activity call returns `run` (~line 574):

```python
            if run.session_ref is not None:
                self._session_refs.append(run.session_ref)
```

Retro terminal block — after the `export_run_artifacts` try/except (~line 766), still inside the outer retro `try`:

```python
# E-38: OQ-B7 retention — downgrade clean-green non-benchmark
# runs to digest-only. Best-effort like the export above.
try:
    had_fix = any(
        ev.kind == RunEventKind.FIX_ATTEMPT and ev.data.get("attempt") not in (None, "1")
        for ev in self._trace
    )
    await workflow.execute_activity(
        apply_session_retention,
        RetentionInput(
            refs=self._session_refs,
            keep_full=keep_full_transcripts(
                outcome=result,
                had_fix_attempts=had_fix,
                is_benchmark=cfg.benchmark.case_id is not None,
            ),
        ),
        **EXPORT_ACT,
    )
except Exception:
    pass
```

(`RunEventKind` is already imported for `_emit`; `result` is the terminal outcome string in that scope — verify both names against the surrounding code before editing.)

Worker registration (`worker.py`): add to imports

```python
from .artifacts.retention import apply_session_retention
```

and add `apply_session_retention,` to the `activities=[...]` list beside `export_run_artifacts`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_session_retention.py tests/test_worker_registration.py tests/test_retro_stage.py tests/test_e2e_greenfield.py -v`
Expected: all PASS. If `test_worker_registration.py` asserts an exact activity list, add `apply_session_retention` there.

Then extend `tests/test_retro_stage.py`: it already asserts the terminal path invokes `export_run_artifacts` — mirror that exact fixture pattern (same fake-activity registration idiom the file uses) to assert `apply_session_retention` is also invoked on a terminal path, with `keep_full=True` for a non-deployed outcome. Register a fake `apply_session_retention` the same way the file fakes `export_run_artifacts`, record its input, and assert on `RetentionInput.keep_full`.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/artifacts/retention.py src/sdlc/workflows/feature.py src/sdlc/worker.py tests/test_session_retention.py
git commit -m "feat(retro): OQ-B7 session retention — downgrade clean-green to digest (E-38)"
```

---

### Task 7: Logfire slice (env-gated, metadata-only)

**Files:**
- Create: `src/sdlc/observability/logfire_setup.py`
- Modify: `src/sdlc/worker.py` (call in `main()` after `validate_registry`)
- Modify: `src/sdlc/activities.py` (spans in `run_coding_task`)
- Modify: `pyproject.toml` (optional dependency)
- Test: `tests/test_logfire_setup.py`

**Interfaces:**
- Produces: `observability.logfire_setup.configure() -> bool` (True iff configured), `observability.logfire_setup.span(name, **attrs)` (context manager; `nullcontext` when disabled).

**Note:** load the `logfire:logfire-instrumentation` skill before this task for current API details; the code below follows the documented `send_to_logfire="if-token-present"` pattern from https://pydantic.dev/docs/logfire/get-started/.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_logfire_setup.py
"""E-38: Logfire slice is env-gated and a strict no-op without a token."""

import importlib

import sdlc.observability.logfire_setup as lf


def _reload(monkeypatch, token):
    if token is None:
        monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("LOGFIRE_TOKEN", token)
    return importlib.reload(lf)


def test_disabled_without_token(monkeypatch):
    mod = _reload(monkeypatch, None)
    assert mod.configure() is False
    with mod.span("x", n=1):  # nullcontext — must not raise, no import
        pass


def test_span_attrs_are_metadata_only_by_convention(monkeypatch):
    # The guard is conventional (spec: counts/durations/ids only); this
    # test pins the API shape so misuse is at least grep-able.
    mod = _reload(monkeypatch, None)
    ctx = mod.span("capture", events=12, bytes=3400, session_id="abc")
    with ctx:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_logfire_setup.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement `src/sdlc/observability/logfire_setup.py`**

```python
"""Minimal env-gated Logfire slice (E-38 spec §6).

Gate: LOGFIRE_TOKEN present -> configure + instrument; absent -> every call
is a no-op (nullcontext), and logfire is never imported. Span attributes
must be metadata only — counts, durations, sizes, ids. NEVER transcript
payloads: the scrub-before-store invariant applies to telemetry too.
"""

from __future__ import annotations

import os
from contextlib import nullcontext

_ENABLED = bool(os.environ.get("LOGFIRE_TOKEN"))


def configure() -> bool:
    """Called once at worker boot. Returns True iff Logfire is live."""
    if not _ENABLED:
        return False
    import logfire  # lazy: optional dependency, only needed when gated on

    logfire.configure(send_to_logfire="if-token-present", console=False)
    logfire.instrument_pydantic_ai()
    return True


def span(name: str, **attrs):
    """Context manager: logfire.span when enabled, else nullcontext."""
    if not _ENABLED:
        return nullcontext()
    import logfire

    return logfire.span(name, **attrs)
```

- [ ] **Step 4: Wire worker boot + activity spans**

`worker.py`, in `main()` after `validate_registry(...)`:

```python
from .observability.logfire_setup import configure as configure_logfire

if configure_logfire():
    logging.getLogger(__name__).info("logfire instrumentation enabled")
```

`activities.py`, in `run_coding_task` — wrap the harness run and capture (import `span` from `.observability.logfire_setup`):

```python
harness = HARNESSES[inp.harness]
with span("harness.run", harness=inp.harness.value, task_id=inp.task_id, attempt=inp.attempt):
    result = await harness.run(
        HarnessRequest(
            prompt=inp.prompt,
            cwd=inp.worktree,
            model=inp.model,
            session_id=inp.session_id,
            timeout_s=inp.timeout_s,
        ),
        heartbeat=activity.heartbeat,
    )
with span("session.capture", task_id=inp.task_id, stdout_bytes=len(result._raw_stdout)):
    ref, digest = capture_session(
        harness,
        result._raw_stdout,
        run_id=activity.info().workflow_run_id,
        task_id=inp.task_id,
        attempt=inp.attempt,
    )
    result.session_ref = ref
    result.session_digest = digest
```

(These are the exact calls Task 5 wrote — only the `with` wrappers are new.)

`pyproject.toml` — add to `[project.optional-dependencies]` (create the table if absent, merge if present):

```toml
[project.optional-dependencies]
logfire = ["logfire[pydantic-ai]>=3"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_logfire_setup.py tests/test_coding_task_checkpoint.py tests/test_worker_registration.py -v`
Expected: all PASS (no `LOGFIRE_TOKEN` in CI → everything no-ops)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/observability/logfire_setup.py src/sdlc/worker.py src/sdlc/activities.py pyproject.toml tests/test_logfire_setup.py
git commit -m "feat(observability): env-gated Logfire slice, metadata-only spans (E-38)"
```

---

### Task 8: Docs — PRD FR-109, ROADMAP, BENCHMARK, ADR-16 check

**Files:**
- Modify: `PRD.md` (FR list, after FR-108)
- Modify: `ROADMAP.md` (E-38 entry §9.8; §9.8 ordering note; FR-702 note)
- Modify: `BENCHMARK.md` (OQ-B7)
- Verify: `ARCHITECTURE.md` ADR-16 (~line 485) matches what landed

**Interfaces:** none — documentation only.

- [ ] **Step 1: PRD — add FR-109 after FR-108** (match the file's FR phrasing style):

```markdown
- **FR-109 (new scope; ADR-16)** Capture-always harness sessions: every
  harness run emits a canonical, scrubbed `HarnessSession` transcript as a
  claim-checked `ArtifactRef{kind: harness_session}` plus an inline
  `SessionDigest` (waste aggregates + decision-skeleton, always kept).
  Scrub is fail-closed before storage; retention downgrades clean-green
  non-benchmark runs to digest-only (full-transcript TTL remains open,
  OQ-B7).
```

- [ ] **Step 2: ROADMAP — mark E-38 landed.** Change `- [ ] **E-38 (new scope; ADR-16)**` to `- [x]`, and append a `*Landed:*` note in the established style:

```markdown
  *Landed:* `HarnessSession`/`SessionDigest` + per-adapter normalisers
  (claude via `--output-format stream-json --verbose`; opencode from its
  event stream), `ArtifactStore` seam with `file://` backend
  (`src/sdlc/artifacts/`), fail-closed capture in `run_coding_task`,
  retro-time OQ-B7 retention, env-gated Logfire slice. PRD line: FR-109.
  Diff claim-check (FR-702 proper) and report rendering deliberately not
  here; TTL still open. Spec
  `docs/superpowers/specs/2026-07-23-capture-always-harness-sessions-design.md`,
  plan `docs/superpowers/plans/2026-07-23-capture-always-harness-sessions.md`.
```

Also update §9.8's ordering line marking E-38 ✓, and FR-702's §2 note ("`ArtifactRef` model exists but diffs travel inline") to record that sessions are now a real claim-check consumer while diffs remain inline.

- [ ] **Step 3: BENCHMARK.md — OQ-B7**: mark the decided half implemented (capture → fail-closed scrub → full+digest, retro downgrade), TTL still the one open sub-point.

- [ ] **Step 4: ARCHITECTURE.md ADR-16 check**: read ~lines 485-511; confirm the landed shape matches (it should — no `session_digest` field is mentioned there, so add the inline-digest clause to the `HarnessRunResult` field list at §4/~line 182 if absent).

- [ ] **Step 5: Full test suite, then commit**

Run: `python -m pytest tests/ -q`
Expected: all PASS

```bash
git add PRD.md ROADMAP.md BENCHMARK.md ARCHITECTURE.md
git commit -m "docs: FR-109 + mark E-38 capture-always sessions landed (E-38)"
```
