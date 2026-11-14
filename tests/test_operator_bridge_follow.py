"""The follow section of the Rust<->Python verb bridge (spec 022 T034).

Contract: .specify/specs/022-mcp-channel-adapter/contracts/bridge-protocol.md

Split out of tests/test_operator_bridge.py along the follow process seam
when that file crossed the 1000-line ceiling: progress frames, cancel
mid-wait, and the consecutive-wait brake (FR-009/010, US4). The framing
helpers are this file's own copies — the sibling bridge test files are
deliberately self-contained (same pattern as test_operator_bridge_chaos).

The feeder wakes a waiting follow by pushing a changed snapshot into
every live subscription, so no case waits for real time except where a
real wait is the point (the clamp and cancel cases wait the 5 s floor).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from sdlc.pending import ClarifyPending
from tests.operator_fakes import RUN_A, build_fake_deps, fleet


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

    def frames(self) -> list[dict]:
        return [json.loads(line) for line in bytes(self.buf).splitlines() if line.strip()]


def _init(actor: str, request_id: str = "1") -> bytes:
    frame = {"op": "init", "id": request_id, "protocol": 1, "actor": actor}
    return (json.dumps(frame) + "\n").encode()


def _line(frame: dict) -> bytes:
    return (json.dumps(frame) + "\n").encode()


def _holder_factory(tmp_path, holder: dict):
    def factory(actor: str):
        tmp_path.mkdir(parents=True, exist_ok=True)
        holder["deps"] = build_fake_deps(tmp_path, actor)
        return holder["deps"]

    return factory


async def _serve_until_terminal(
    lines: list[bytes], factory, reply_ids: list[str], progress_interval_s: float = 0.01
) -> _FakeWriter:
    """Like the main file's _serve_until_all, but only op=result/error frames
    count as terminal.

    A progress frame carries the request id too, so a plain id check would
    stop on it; here stdin closes only after each request's final answer.
    """
    bridge = _bridge()
    reader = asyncio.StreamReader()
    for line in lines:
        reader.feed_data(line)
    writer = _FakeWriter()
    task = asyncio.ensure_future(
        bridge.serve(factory, reader, writer, progress_interval_s=progress_interval_s)
    )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 15
    while loop.time() < deadline:
        seen = {f.get("id") for f in writer.frames() if f.get("op") in ("result", "error")}
        if all(rid in seen for rid in reply_ids):
            break
        await asyncio.sleep(0.01)
    reader.feed_eof()
    await asyncio.wait_for(task, timeout=15)
    return writer


def _snapshot_with_new_pending():
    snap = fleet().model_copy(deep=True)
    for item in snap.inbox:
        if item.run_id == RUN_A:
            item.pending.append(
                ClarifyPending(key="Q9", question="which cache?", why_it_matters="pick")
            )
    return snap


async def _feed_changes(poller) -> None:
    changed = _snapshot_with_new_pending()
    while True:
        for q in list(poller.subscriptions):
            q.put_nowait(changed)
        await asyncio.sleep(0.001)


def _fed_factory(tmp_path, holder: dict):
    """Build deps as _holder_factory does, and start the feeder inside init so
    every follow in the session is woken by a changed snapshot."""

    base = _holder_factory(tmp_path, holder)

    def factory(actor: str):
        deps = base(actor)
        holder["feeder"] = asyncio.ensure_future(_feed_changes(deps.poller))
        return deps

    return factory


def _terminal(writer: _FakeWriter, rid: str) -> dict:
    found = [
        f for f in writer.frames() if f.get("id") == rid and f.get("op") in ("result", "error")
    ]
    assert len(found) == 1, f"expected one terminal frame for id {rid!r}, got {found}"
    return found[0]


@pytest.mark.asyncio
async def test_follow_progress_frames_precede_the_timed_out_terminal(tmp_path):
    holder: dict = {}
    # timeout_s=0 is below the floor: _clamp raises it to MIN_TIMEOUT_S (5 s),
    # so the terminal says "nothing changed in 5s".
    writer = await _serve_until_terminal(
        [
            _init("mcp:test"),
            _line(
                {
                    "op": "call",
                    "id": "2",
                    "tool": "follow",
                    "args": {"run_id": RUN_A, "timeout_s": 0},
                }
            ),
        ],
        _holder_factory(tmp_path, holder),
        reply_ids=["2"],
    )
    frames = writer.frames()
    progress = [f for f in frames if f.get("op") == "progress"]
    assert progress, "a 5 s wait must emit at least one progress frame"
    for f in progress:
        assert f["id"] == "2"
        assert isinstance(f["elapsed_s"], (int, float)) and f["elapsed_s"] >= 0
        assert isinstance(f["message"], str) and f["message"]

    last = frames[-1]
    assert last["op"] == "result" and last["id"] == "2", last
    assert last["ok"] is True, last
    assert last["value"]["timed_out"] is True
    assert "nothing changed in 5s" in last["value"]["detail"]

    first_progress = frames.index(progress[0])
    assert first_progress < len(frames) - 1, "progress must arrive before the terminal"


@pytest.mark.asyncio
async def test_follow_returns_early_when_a_new_pending_item_arrives(tmp_path):
    holder: dict = {}
    try:
        writer = await _serve_until_terminal(
            [
                _init("mcp:test"),
                _line({"op": "call", "id": "2", "tool": "follow", "args": {"run_id": RUN_A}}),
            ],
            _fed_factory(tmp_path, holder),
            reply_ids=["2"],
        )
    finally:
        holder["feeder"].cancel()

    terminal = _terminal(writer, "2")
    assert terminal["ok"] is True, terminal
    assert terminal["value"]["timed_out"] is False
    assert terminal["value"]["changed"] == ["feature-add-sso:pending"]
    assert "feature-add-sso is now waiting on:" in terminal["value"]["detail"]


@pytest.mark.asyncio
async def test_follow_cancel_mid_wait_answers_cancelled_and_releases_the_subscription(tmp_path):
    holder: dict = {}
    writer = await _serve_until_terminal(
        [
            _init("mcp:test"),
            _line(
                {
                    "op": "call",
                    "id": "2",
                    "tool": "follow",
                    "args": {"run_id": RUN_A, "timeout_s": 0},
                }
            ),
            _line({"op": "cancel", "id": "2"}),
        ],
        _holder_factory(tmp_path, holder),
        reply_ids=["2"],
    )
    terminal = _terminal(writer, "2")
    assert terminal["ok"] is False, terminal
    assert terminal["error"]["code"] == "cancelled", terminal
    assert not any(
        f.get("op") == "result" and f.get("id") == "2" and f.get("ok") is True
        for f in writer.frames()
    )
    assert holder["deps"].poller.subscriptions == set()
    assert holder["deps"].follow_calls == 1


@pytest.mark.asyncio
async def test_follow_eleventh_consecutive_wait_is_refused(tmp_path):
    holder: dict = {}
    lines = [_init("mcp:test")] + [
        _line({"op": "call", "id": str(n), "tool": "follow", "args": {}}) for n in range(2, 13)
    ]
    try:
        writer = await _serve_until_terminal(
            lines, _fed_factory(tmp_path, holder), reply_ids=[str(n) for n in range(2, 13)]
        )
    finally:
        holder["feeder"].cancel()

    for n in range(2, 12):
        assert _terminal(writer, str(n))["ok"] is True, n
    refused = _terminal(writer, "12")
    assert refused["ok"] is False, refused
    assert refused["error"]["code"] == "tool_error", refused
    assert refused["error"]["message"] == (
        "refusing a 11th consecutive wait; report to the operator before waiting again"
    )


@pytest.mark.asyncio
async def test_follow_streak_resets_on_list_runs(tmp_path):
    holder: dict = {}
    lines = [_init("mcp:test")]
    lines += [
        _line({"op": "call", "id": str(n), "tool": "follow", "args": {}}) for n in range(2, 12)
    ]
    lines += [_line({"op": "call", "id": "12", "tool": "list_runs", "args": {}})]
    lines += [_line({"op": "call", "id": "13", "tool": "follow", "args": {}})]
    try:
        writer = await _serve_until_terminal(
            lines, _fed_factory(tmp_path, holder), reply_ids=[str(n) for n in range(2, 14)]
        )
    finally:
        holder["feeder"].cancel()

    assert _terminal(writer, "12")["ok"] is True
    after_reset = _terminal(writer, "13")
    assert after_reset["ok"] is True, after_reset
    assert after_reset["value"]["changed"], after_reset
