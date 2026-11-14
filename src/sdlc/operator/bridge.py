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
import inspect
import json
import logging
import os
import re
import sys
from collections.abc import Callable
from typing import Any, BinaryIO, get_type_hints

from pydantic import BaseModel, ValidationError, create_model

from . import tools
from .errors import ToolError

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

# Which writes need which confirmation flavour (plan T021; every WRITE_TOOLS
# member must appear here — the describe tests enforce it) and which tools
# emit progress frames while they run.
CONFIRM: dict[str, str] = {
    "start_run": "start",
    "answer_question": "pending",
    "decide_gate": "pending",
}
PROGRESS = {"follow"}


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
    return {"op": "result", "id": rid, "ok": False, "error": {"code": code, "message": message}}


def _result_frame(rid: Any, value: Any) -> dict[str, Any]:
    return {"op": "result", "id": rid, "ok": True, "value": value}


def _args_model(fn: Any) -> Any:
    """A pydantic model over the verb's signature minus `deps` (FR-002).

    tools.py uses `from __future__ import annotations`, so hints come from
    get_type_hints (resolved against tools' own globals, where GateOutcome
    and the typed result models live). *args/**kwargs parameters never
    become fields, so test doubles with ``**kwargs`` validate to ``{}``.
    """
    hints = get_type_hints(fn)
    fields: dict[str, Any] = {}
    for pname, param in inspect.signature(fn).parameters.items():
        if pname == "deps" or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        required = param.default is inspect.Parameter.empty
        fields[pname] = (hints.get(pname, Any), ... if required else param.default)
    return create_model(f"{fn.__name__}_args", **fields)


def _find_member(name: str) -> Any:
    """The membership tuple entry named `name`, or None."""
    for fn in (*tools.READ_TOOLS, *tools.WRITE_TOOLS):
        if fn.__name__ == name:
            return fn
    return None


def _validation_summary(exc: ValidationError) -> str:
    """loc + type only — a validation error must never echo values."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "(root)"
        parts.append(f"{loc}: {err['type']}")
    return "; ".join(parts)


def _descriptor(fn: Any, *, read_only: bool) -> dict[str, Any]:
    """One ToolDescriptor (data-model.md) from a verb's signature."""
    args_model = _args_model(fn)
    ret = get_type_hints(fn).get("return")
    output_schema = (
        ret.model_json_schema() if isinstance(ret, type) and issubclass(ret, BaseModel) else None
    )
    return {
        "name": fn.__name__,
        "description": inspect.getdoc(fn),
        "input_schema": args_model.model_json_schema(),
        "output_schema": output_schema,
        "read_only": read_only,
        "confirm": CONFIRM.get(fn.__name__, "none"),
        "progress": fn.__name__ in PROGRESS,
    }


def _tool_descriptors() -> list[dict[str, Any]]:
    """One ToolDescriptor per member of READ_TOOLS + WRITE_TOOLS, in the
    membership order (which the parity tests pin)."""
    return [_descriptor(fn, read_only=True) for fn in tools.READ_TOOLS] + [
        _descriptor(fn, read_only=False) for fn in tools.WRITE_TOOLS
    ]


class _FrameTooLarge(Exception):
    """A request line exceeded MAX_FRAME_BYTES. Carries the line's head
    (a few KiB) so the caller can salvage an id for the error frame."""

    def __init__(self, head: bytes) -> None:
        super().__init__("frame too large")
        self.head = head


_ID_RE = re.compile(rb'"id"\s*:\s*(?:"([^"\\\x00-\x1f]{0,128})"|(-?\d+))')


def _salvage_id(head: bytes) -> Any:
    """Best-effort request id from an oversize line's first bytes.

    The frame is unparsable by definition, but its id sits near the start
    in practice; echoing it lets the client correlate the refusal with the
    request it sent. Returns None when no id is recoverable.
    """
    m = _ID_RE.search(head)
    if m is None:
        return None
    if m.group(1) is not None:
        return m.group(1).decode("utf-8", "replace")
    return int(m.group(2))


class _LineReader:
    """Newline framing over a StreamReader, owning the 4 MiB cap.

    Why not StreamReader.readline(): its own limit (64 KiB by default) is
    far below the protocol ceiling, and on overrun the consumed bytes are
    lost to us. Chunked reads plus a local carry keep the oversize path in
    charge of its own bytes: the head is salvageable and the rest of the
    runaway line is consumed so the next line starts in sync.
    """

    def __init__(self, reader: asyncio.StreamReader) -> None:
        self._reader = reader
        self._carry = bytearray()

    async def readline(self) -> bytes | None:
        """One line without its newline; a partial final line at EOF is
        returned as-is; None only at a clean EOF. Raises _FrameTooLarge."""
        while True:
            nl = self._carry.find(b"\n")
            if nl >= 0:
                line = bytes(self._carry[:nl])
                del self._carry[: nl + 1]
                return line
            if len(self._carry) > MAX_FRAME_BYTES:
                head = bytes(self._carry[:4096])
                self._carry.clear()
                tail = bytearray()
                while b"\n" not in tail:
                    chunk = await self._reader.read(65536)
                    if not chunk:
                        break
                    del tail[:-65536]
                    tail += chunk
                raise _FrameTooLarge(head)
            chunk = await self._reader.read(65536)
            if not chunk:
                if self._carry:
                    line = bytes(self._carry)
                    self._carry.clear()
                    return line
                return None
            self._carry += chunk


async def _handle_request(
    op: str, rid: Any, req: dict[str, Any], deps: Any, send: Callable[[dict[str, Any]], Any]
) -> None:
    """One preview/call request -> exactly one terminal frame (T022/T027)."""
    tool = req.get("tool")
    if deps is None:
        await send(_error_frame(rid, "bad_request", sentence_bad_request(SENTENCE_INIT_FIRST)))
        return
    descriptor = next((d for d in _tool_descriptors() if d["name"] == tool), None)
    member = _find_member(tool) if isinstance(tool, str) else None
    fn = getattr(tools, tool, None) if isinstance(tool, str) else None
    if descriptor is None or member is None or fn is None:
        await send(_error_frame(rid, "bad_request", sentence_bad_request(f"unknown tool {tool!r}")))
        return
    if descriptor["confirm"] != "none":
        # Fail closed (FR-005): the preview/expect_digest handshake lands
        # in T027/T029; until then no write verb may run over this path.
        digest = req.get("expect_digest")
        if not isinstance(digest, str) or not digest:
            await send(
                _error_frame(
                    rid, "bad_request", sentence_bad_request("confirm tools require expect_digest")
                )
            )
        else:
            await send(
                _error_frame(rid, "bad_request", sentence_bad_request("confirm is not wired yet"))
            )
        return
    if op == "preview":
        await send(
            _error_frame(rid, "bad_request", sentence_bad_request("preview is for confirm tools"))
        )
        return
    # Validate with the SAME schema describe published (the member's), then
    # call the module attribute so tests (and future wrappers) can patch it.
    raw = req.get("args")
    args = raw if isinstance(raw, dict) else {}
    try:
        validated = dict(_args_model(member).model_validate(args))
    except ValidationError as exc:
        await send(_error_frame(rid, "bad_request", sentence_bad_request(_validation_summary(exc))))
        return
    try:
        value = await fn(deps, **validated)
    except asyncio.CancelledError:
        await send(_error_frame(rid, "cancelled", "cancelled"))
        return
    except ToolError as exc:
        await send(_error_frame(rid, "tool_error", exc.message))
        return
    except Exception as exc:
        _log.exception("bridge call %r failed", tool)
        await send(_error_frame(rid, "internal", sentence_internal(exc)))
        return
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    await send(_result_frame(rid, value))


async def serve(
    deps_factory: DepsFactory,
    reader: asyncio.StreamReader,
    writer: Any,
    *,
    progress_interval_s: float | None = None,
) -> None:
    """Serve newline-delimited JSON requests until stdin EOF.

    One task per request id (the contract allows concurrency); writes are
    serialised behind a lock. On EOF in-flight tasks get a brief grace to
    finish, then are cancelled, and the deps' poller (when present) is
    closed before returning.
    """
    del progress_interval_s  # used from T035
    lock = asyncio.Lock()
    deps: Any = None
    tasks: dict[Any, asyncio.Task] = {}
    lines = _LineReader(reader)

    async def send(frame: dict[str, Any]) -> None:
        data = (json.dumps(frame, separators=(",", ":")) + "\n").encode("utf-8")
        async with lock:
            writer.write(data)
            await writer.drain()

    while True:
        try:
            line = await lines.readline()
        except _FrameTooLarge as e:
            await send(
                _error_frame(
                    _salvage_id(e.head), "bad_request", sentence_bad_request(SENTENCE_OVERSIZE)
                )
            )
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
            try:
                deps = deps_factory(actor)
            except Exception as exc:  # the operator must learn the type only
                _log.exception("deps factory failed")
                await send(_error_frame(rid, "internal", sentence_internal(exc)))
                continue
            await send(
                {"op": "describe", "protocol": BRIDGE_PROTOCOL, "tools": _tool_descriptors()}
            )
        elif op == "cancel":
            task = tasks.get(rid)
            if task is not None and not task.done():
                task.cancel()  # the task emits its own terminal frame; it
                # stays in `tasks` so EOF cleanup awaits that frame
        elif op in ("preview", "call"):
            if rid in tasks:
                await send(
                    _error_frame(rid, "bad_request", sentence_bad_request("duplicate request id"))
                )
                continue
            tasks[rid] = asyncio.create_task(_handle_request(op, rid, req, deps, send))
            # Give the task its first slice now: a buffered cancel for this
            # id must land inside the verb await, not on an unstarted task
            # (whose body would never run and never emit a terminal frame).
            await asyncio.sleep(0)
        else:
            await send(_error_frame(rid, "bad_request", sentence_bad_request(SENTENCE_UNKNOWN_OP)))

    # EOF: give in-flight tasks a brief grace to finish normally, then
    # cancel the stragglers (the contract's cancel-on-EOF) and close the
    # poller. The grace is what lets a call whose reply is already in
    # flight complete cleanly instead of answering "cancelled".
    if tasks:
        await asyncio.wait(set(tasks.values()), timeout=0.25)
    for task in tasks.values():
        task.cancel()
    await asyncio.gather(*tasks.values(), return_exceptions=True)
    poller = getattr(deps, "poller", None) if deps is not None else None
    aclose = getattr(poller, "aclose", None)
    if aclose is not None:
        try:
            await aclose()
        except Exception:
            _log.exception("poller aclose failed at EOF")  # must not propagate


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
