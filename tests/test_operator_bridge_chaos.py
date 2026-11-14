"""Chaos / edge-case tests for the Rust<->Python verb bridge (spec 022).

Contract: .specify/specs/022-mcp-channel-adapter/contracts/bridge-protocol.md

RED until src/sdlc/operator/bridge.py exists. The bridge is imported inside
helpers, so every test fails on its own for the missing feature. Only the
behaviour the contract pins down is asserted; where the contract is silent,
the test asserts "does not crash / does not hang / does not leak".
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

SECRET = "SECRET-PATH-D:\\own\\Kroker\\hunter2"
TIMEOUT = 10


def _bridge():
    from sdlc.operator import bridge

    return bridge


class _FakeWriter:
    def __init__(self) -> None:
        self.buf = bytearray()

    def write(self, data: bytes) -> None:
        self.buf.extend(data)

    async def drain(self) -> None:
        return None

    def lines(self) -> list[bytes]:
        return [ln for ln in bytes(self.buf).splitlines() if ln.strip()]

    def frames(self) -> list[dict]:
        out = []
        for ln in self.lines():
            out.append(json.loads(ln))
        return out


async def _noop() -> None:
    return None


def _factory(calls: list[str], aclose=_noop, raises: Exception | None = None):
    def factory(actor: str):
        calls.append(actor)
        if raises is not None:
            raise raises
        return SimpleNamespace(poller=SimpleNamespace(aclose=aclose), actor=actor)

    return factory


def _init(actor: str = "mcp:test", request_id: str = "1", protocol: int = 1) -> bytes:
    frame = {"op": "init", "id": request_id, "protocol": protocol, "actor": actor}
    return (json.dumps(frame) + "\n").encode()


def _call(request_id: str, tool: str, args: dict | None = None, **extra) -> bytes:
    frame = {"op": "call", "id": request_id, "tool": tool, "args": args or {}, **extra}
    return (json.dumps(frame) + "\n").encode()


async def _serve(lines: list[bytes], factory, *, eof: bool = True) -> _FakeWriter:
    bridge = _bridge()
    reader = asyncio.StreamReader()
    for line in lines:
        reader.feed_data(line)
    if eof:
        reader.feed_eof()
    writer = _FakeWriter()
    await asyncio.wait_for(bridge.serve(factory, reader, writer), timeout=TIMEOUT)
    return writer


def _terminal(writer: _FakeWriter, request_id: str) -> list[dict]:
    return [f for f in writer.frames() if f.get("id") == request_id and f.get("op") == "result"]


# --- malformed input never kills the loop ----------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "garbage",
    [
        b"{not json\n",
        b"[]\n",
        b"null\n",
        b"42\n",
        b'"just a string"\n',
        b"\xff\xfe\xfa not utf-8\n",
        b"\n\n   \n",
    ],
    ids=["truncated-json", "array", "null", "number", "string", "invalid-utf8", "blank-lines"],
)
async def test_malformed_line_does_not_stop_the_loop(garbage):
    calls: list[str] = []
    writer = await _serve([garbage, _init("mcp:test")], _factory(calls))

    assert calls == ["mcp:test"], "a later valid init must still be served"
    assert any(f.get("op") == "describe" for f in writer.frames())


@pytest.mark.asyncio
async def test_request_without_id_does_not_stop_the_loop():
    calls: list[str] = []
    no_id = (json.dumps({"op": "call", "tool": "inbox", "args": {}}) + "\n").encode()
    writer = await _serve([no_id, _init("mcp:test")], _factory(calls))

    assert calls == ["mcp:test"]
    assert any(f.get("op") == "describe" for f in writer.frames())


# --- handshake edge cases ---------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", [0, 2, "1", None])
async def test_protocol_mismatch_refuses_handshake(protocol):
    calls: list[str] = []
    frame = {"op": "init", "id": "1", "protocol": protocol, "actor": "mcp:test"}
    writer = await _serve([(json.dumps(frame) + "\n").encode()], _factory(calls))

    assert not any(f.get("op") == "describe" for f in writer.frames())
    assert calls == [], "no OperatorDeps may be built on a protocol mismatch"


@pytest.mark.asyncio
async def test_init_missing_actor_is_refused_without_building_deps():
    calls: list[str] = []
    frame = {"op": "init", "id": "1", "protocol": 1}
    writer = await _serve([(json.dumps(frame) + "\n").encode()], _factory(calls))

    assert calls == []
    assert not any(f.get("op") == "describe" for f in writer.frames())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actor",
    ["mcp:a" + "b" * 39, "mcp:x\n", "mcp:a b", "mcp:a/../b", "mcp:\u0661", "MCP:x", " mcp:x"],
    ids=[
        "40-chars-ok",
        "trailing-newline",
        "space",
        "path-traversal",
        "arabic-digit",
        "upper-prefix",
        "leading-space",
    ],
)
async def test_actor_boundary_cases(actor):
    calls: list[str] = []
    writer = await _serve([_init(actor)], _factory(calls))

    if actor == "mcp:a" + "b" * 39:
        # 40 chars after the prefix is the maximum and must be accepted.
        assert calls == [actor]
    else:
        assert calls == [], f"actor {actor!r} must not build deps"
        results = _terminal(writer, "1")
        assert results and results[0]["error"]["code"] == "bad_request"


@pytest.mark.asyncio
async def test_request_before_init_is_refused():
    calls: list[str] = []
    writer = await _serve([_call("1", "inbox")], _factory(calls))

    assert calls == []
    results = _terminal(writer, "1")
    assert results and results[0]["ok"] is False


# --- argument validation: None / empty / wrong type --------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args",
    [{"run_id": None}, {"run_id": ""}, {"run_id": 12345}, {}],
    ids=["null", "empty-string", "wrong-type", "missing"],
)
async def test_bad_arguments_are_bad_request_not_internal(args):
    calls: list[str] = []
    writer = await _serve([_init(), _call("2", "get_run", args)], _factory(calls))

    results = _terminal(writer, "2")
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert results[0]["error"]["code"] in {"bad_request", "tool_error"}


@pytest.mark.asyncio
async def test_bad_argument_message_does_not_echo_values():
    calls: list[str] = []
    writer = await _serve([_init(), _call("2", "get_run", {"run_id": SECRET})], _factory(calls))

    results = _terminal(writer, "2")
    assert results and results[0]["ok"] is False
    assert SECRET not in json.dumps(results[0]), "validation errors must not echo values"


@pytest.mark.asyncio
async def test_unknown_tool_is_bad_request_with_fixed_prefix():
    calls: list[str] = []
    writer = await _serve([_init(), _call("2", "no_such_verb")], _factory(calls))

    results = _terminal(writer, "2")
    assert results[0]["error"]["code"] == "bad_request"
    assert results[0]["error"]["message"].startswith("unknown tool or bad arguments:")


@pytest.mark.asyncio
async def test_empty_tool_name_is_bad_request():
    calls: list[str] = []
    writer = await _serve([_init(), _call("2", "")], _factory(calls))

    results = _terminal(writer, "2")
    assert results and results[0]["error"]["code"] == "bad_request"


# --- confirm-gated writes fail closed ---------------------------------------


@pytest.mark.asyncio
async def test_write_tool_without_expect_digest_is_refused():
    calls: list[str] = []
    writer = await _serve(
        [
            _init(),
            _call("2", "answer_question", {"run_id": "r1", "key": "Q1", "text": "yes"}),
        ],
        _factory(calls),
    )

    results = _terminal(writer, "2")
    assert len(results) == 1
    assert results[0]["ok"] is False, "confirm=pending call without expect_digest must not run"


# --- exception handling does not leak detail --------------------------------


@pytest.mark.asyncio
async def test_factory_exception_is_internal_and_leaks_no_detail():
    calls: list[str] = []
    writer = await _serve([_init()], _factory(calls, raises=RuntimeError(SECRET)))

    assert SECRET not in json.dumps(writer.frames())
    results = _terminal(writer, "1")
    assert results and results[0]["error"]["code"] == "internal"
    assert "RuntimeError" in results[0]["error"]["message"]


@pytest.mark.asyncio
async def test_verb_exception_is_contained_and_leaks_no_detail(monkeypatch):
    from sdlc.operator import tools

    async def boom(deps, **kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(tools, "inbox", boom)
    calls: list[str] = []
    writer = await _serve([_init(), _call("2", "inbox")], _factory(calls))

    assert SECRET not in json.dumps(writer.frames())
    results = _terminal(writer, "2")
    assert len(results) == 1 and results[0]["ok"] is False


# --- cancel / timeout / hang ------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_of_hung_verb_yields_cancelled_frame(monkeypatch):
    from sdlc.operator import tools

    async def hang(deps, **kwargs):
        await asyncio.Event().wait()  # never completes

    monkeypatch.setattr(tools, "inbox", hang)
    calls: list[str] = []
    cancel = (json.dumps({"op": "cancel", "id": "2"}) + "\n").encode()
    writer = await _serve([_init(), _call("2", "inbox"), cancel], _factory(calls))

    results = _terminal(writer, "2")
    assert len(results) == 1
    assert results[0]["error"]["code"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_for_unknown_id_is_harmless():
    calls: list[str] = []
    cancel = (json.dumps({"op": "cancel", "id": "ghost"}) + "\n").encode()
    writer = await _serve([_init(), cancel], _factory(calls))

    assert calls == ["mcp:test"]
    assert any(f.get("op") == "describe" for f in writer.frames())


@pytest.mark.asyncio
async def test_eof_cancels_hung_tasks_and_returns(monkeypatch):
    from sdlc.operator import tools

    async def hang(deps, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(tools, "inbox", hang)
    closed: list[bool] = []

    async def aclose() -> None:
        closed.append(True)

    calls: list[str] = []
    await _serve([_init(), _call("2", "inbox")], _factory(calls, aclose=aclose))

    assert closed == [True], "EOF must await poller.aclose() exactly once"


@pytest.mark.asyncio
async def test_eof_with_no_init_returns_without_building_deps():
    calls: list[str] = []
    await _serve([], _factory(calls))

    assert calls == []


@pytest.mark.asyncio
async def test_poller_aclose_failure_at_eof_does_not_raise():
    async def aclose() -> None:
        raise OSError("socket already closed")

    calls: list[str] = []
    # serve() must swallow or log a close failure; it must not propagate it.
    await _serve([_init()], _factory(calls, aclose=aclose))


# --- concurrency: one terminal frame per id, no torn lines ------------------


@pytest.mark.asyncio
async def test_concurrent_calls_each_get_one_terminal_frame_and_no_torn_lines(monkeypatch):
    from sdlc.operator import tools

    async def jittery(deps, **kwargs):
        await asyncio.sleep(0)
        return "ok"

    monkeypatch.setattr(tools, "inbox", jittery)
    ids = [str(i) for i in range(2, 42)]
    lines = [_init()] + [_call(i, "inbox") for i in ids]
    writer = await _serve(lines, _factory([]))

    for raw in writer.lines():
        json.loads(raw)  # any interleaved write would fail to parse here
    for rid in ids:
        assert len(_terminal(writer, rid)) == 1, f"id {rid} must get exactly one terminal frame"


# --- size boundary ----------------------------------------------------------


@pytest.mark.asyncio
async def test_frame_one_byte_over_limit_is_rejected_without_crashing():
    limit = 4 * 1024 * 1024
    prefix = b'{"op":"call","id":"9","tool":"inbox","args":{"x":"'
    oversized = prefix + b"a" * (limit + 1) + b'"}}\n'
    calls: list[str] = []
    writer = await _serve([_init(), oversized, _init("mcp:test", "3")], _factory(calls))

    assert any(f.get("id") == "9" and f.get("ok") is False for f in writer.frames())
    assert any(f.get("op") == "describe" for f in writer.frames()), "loop must survive"
