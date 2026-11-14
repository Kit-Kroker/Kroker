"""The Rust<->Python verb bridge (022, contracts/bridge-protocol.md).

Owns the JSON-lines frame protocol spoken on the child's stdin/stdout:
the MCP server (interfaces/mcp) is a Rust process that spawns
``python -m sdlc.operator.bridge`` per session and forwards tool calls
here, so verb logic stays single-sourced in tools.py (seam (b), FR-001).

Protocol hygiene is the load-bearing part: fd 1 IS the protocol channel,
so main() duplicates it and redirects Python-level stdout to stderr
BEFORE importing anything from sdlc that might print. stdout is
protocol-only; every log line goes to stderr.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from collections.abc import Callable
from typing import Any, BinaryIO

BRIDGE_PROTOCOL = 1
MAX_FRAME_BYTES = 4 * 1024 * 1024

ACTOR_RE = re.compile(r"^mcp:[a-z0-9-]{1,40}$")

# progress cadence while a progress tool runs (T035); serve() accepts an
# override so tests can shrink it.
PROGRESS_INTERVAL_S = 15.0

_log = logging.getLogger(__name__)

SENTENCE_CHANGED = "the pending item changed while you were confirming; re-read the inbox and retry"
SENTENCE_BAD_ACTOR = "actor must match ^mcp:[a-z0-9-]{1,40}$"
SENTENCE_OVERSIZE = f"frame exceeds {MAX_FRAME_BYTES} bytes"
SENTENCE_UNPARSABLE = "frame is not a JSON object"
SENTENCE_INIT_FIRST = "init must precede every other op"
SENTENCE_UNKNOWN_OP = "op must be one of init, preview, call, cancel"

DepsFactory = Callable[[str], Any]


def sentence_internal(exc: BaseException) -> str:
    return f"the factory raised {type(exc).__name__}; the operator should check the server log"


def sentence_bad_request(detail: str) -> str:
    return f"unknown tool or bad arguments: {detail}"


def isolate_stdout() -> BinaryIO:
    """Duplicate fd 1 for protocol frames, then send stdout to stderr.

    Must run before any sdlc import that could print: a stray write to the
    real stdout would corrupt the frame stream the Rust parent is parsing.
    """
    proto = os.fdopen(os.dup(1), "wb", buffering=0)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return proto


def _error_frame(rid: Any, code: str, message: str) -> dict[str, Any]:
    return {"id": rid, "ok": False, "error": {"code": code, "message": message}}


def _result_frame(rid: Any, value: Any) -> dict[str, Any]:
    return {"id": rid, "ok": True, "value": value}


def _tool_descriptors() -> list[dict[str, Any]]:
    """One ToolDescriptor per member of READ_TOOLS + WRITE_TOOLS (T013)."""
    return []


class _FrameTooLarge(Exception):
    """A request line exceeded MAX_FRAME_BYTES."""


async def _read_line(reader: asyncio.StreamReader) -> bytes | None:
    """One raw line, or None at EOF. Raises _FrameTooLarge past the cap.

    The cap rides the StreamReader limit, which main() sets at the 4 MiB
    protocol ceiling; readline()'s ValueError there consumes the runaway
    line and keeps the stream positioned at the next one.
    """
    try:
        line = await reader.readline()
    except ValueError as e:
        raise _FrameTooLarge from e
    return line or None


async def _handle_request(
    op: str, rid: Any, req: dict[str, Any], deps: Any, send: Callable[[dict[str, Any]], Any]
) -> None:
    """One preview/call request -> exactly one terminal frame (T022/T027)."""
    tool = req.get("tool")
    if deps is None:
        await send(_error_frame(rid, "bad_request", sentence_bad_request(SENTENCE_INIT_FIRST)))
        return
    descriptor = next((d for d in _tool_descriptors() if d["name"] == tool), None)
    if descriptor is None:
        await send(_error_frame(rid, "bad_request", sentence_bad_request(f"unknown tool {tool!r}")))
        return
    await send(_error_frame(rid, "bad_request", sentence_bad_request("call is not wired yet")))


async def serve(
    deps_factory: DepsFactory,
    reader: asyncio.StreamReader,
    writer: Any,
    *,
    progress_interval_s: float | None = None,
) -> None:
    """Serve newline-delimited JSON requests until stdin EOF.

    One task per request id (the contract allows concurrency); writes are
    serialised behind a lock. On EOF every task is cancelled and the
    deps' poller (when present) is closed before returning.
    """
    del progress_interval_s  # used from T035
    lock = asyncio.Lock()
    deps: Any = None
    tasks: dict[Any, asyncio.Task] = {}

    async def send(frame: dict[str, Any]) -> None:
        data = (json.dumps(frame, separators=(",", ":")) + "\n").encode("utf-8")
        async with lock:
            writer.write(data)
            await writer.drain()

    while True:
        try:
            line = await _read_line(reader)
        except _FrameTooLarge:
            await send(_error_frame(None, "bad_request", sentence_bad_request(SENTENCE_OVERSIZE)))
            continue
        if line is None:
            break  # EOF
        text = line.strip()
        if not text:
            continue
        try:
            req = json.loads(text)
            if not isinstance(req, dict):
                raise TypeError("frame is not an object")
        except (ValueError, TypeError):
            await send(_error_frame(None, "bad_request", sentence_bad_request(SENTENCE_UNPARSABLE)))
            continue
        op = req.get("op")
        rid = req.get("id")
        if op == "init":
            if deps is not None:
                await send(
                    _error_frame(rid, "bad_request", sentence_bad_request("init already received"))
                )
                continue
            actor = req.get("actor")
            protocol = req.get("protocol")
            if not isinstance(actor, str) or not ACTOR_RE.fullmatch(actor):
                await send(
                    _error_frame(rid, "bad_request", sentence_bad_request(SENTENCE_BAD_ACTOR))
                )
                continue
            if protocol != BRIDGE_PROTOCOL:
                await send(
                    _error_frame(
                        rid,
                        "bad_request",
                        sentence_bad_request(f"protocol must be {BRIDGE_PROTOCOL}"),
                    )
                )
                continue
            deps = deps_factory(actor)
            await send(
                {"op": "describe", "protocol": BRIDGE_PROTOCOL, "tools": _tool_descriptors()}
            )
        elif op == "cancel":
            task = tasks.pop(rid, None)
            if task is not None:
                task.cancel()  # the task emits its own terminal frame
        elif op in ("preview", "call"):
            if rid in tasks:
                await send(
                    _error_frame(rid, "bad_request", sentence_bad_request("duplicate request id"))
                )
                continue
            tasks[rid] = asyncio.create_task(_handle_request(op, rid, req, deps, send))
        else:
            await send(_error_frame(rid, "bad_request", sentence_bad_request(SENTENCE_UNKNOWN_OP)))

    for task in tasks.values():
        task.cancel()
    await asyncio.gather(*tasks.values(), return_exceptions=True)
    poller = getattr(deps, "poller", None) if deps is not None else None
    aclose = getattr(poller, "aclose", None)
    if aclose is not None:
        await aclose()


async def _serve_pipes(deps_factory: DepsFactory, proto: BinaryIO) -> None:
    """Wire real stdin + the isolated protocol fd into serve()."""
    loop: Any = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=MAX_FRAME_BYTES + 65536)
    read_proto = asyncio.StreamReaderProtocol(reader, loop=loop)
    await loop.connect_read_pipe(lambda: read_proto, sys.stdin)
    transport, write_proto = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, proto)
    writer = asyncio.StreamWriter(transport, write_proto, None, loop)
    await serve(deps_factory, reader, writer)


def main() -> None:
    proto = isolate_stdout()
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s %(message)s"
    )
    from . import runtime

    asyncio.run(
        _serve_pipes(lambda actor: runtime.operator_deps(runtime.build_poller(), actor), proto)
    )


if __name__ == "__main__":  # pragma: no cover - subprocess entry
    main()
