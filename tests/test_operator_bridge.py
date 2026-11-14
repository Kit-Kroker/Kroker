"""T010 (framing) and T012 (describe) for the Rust<->Python verb bridge.

Contract: .specify/specs/022-mcp-channel-adapter/contracts/bridge-protocol.md
Data model: .specify/specs/022-mcp-channel-adapter/data-model.md

RED until src/sdlc/operator/bridge.py exists. The bridge module is imported
inside helpers, so each test fails on its own for the missing feature.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FOUR_MIB = 4 * 1024 * 1024


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


def _factory_recording(calls: list[str]):
    def factory(actor: str):
        calls.append(actor)
        poller = SimpleNamespace(aclose=_async_noop)
        return SimpleNamespace(poller=poller, actor=actor)

    return factory


async def _async_noop() -> None:
    return None


async def _serve_lines(lines: list[bytes], factory) -> _FakeWriter:
    bridge = _bridge()
    reader = asyncio.StreamReader()
    for line in lines:
        reader.feed_data(line)
    reader.feed_eof()
    writer = _FakeWriter()
    await asyncio.wait_for(bridge.serve(factory, reader, writer), timeout=10)
    return writer


def _init(actor: str, request_id: str = "1") -> bytes:
    return (json.dumps({"op": "init", "id": request_id, "protocol": 1, "actor": actor}) + "\n").encode()


# --- framing (T010) ---------------------------------------------------------


@pytest.mark.asyncio
async def test_init_with_valid_actor_replies_describe_protocol_1():
    calls: list[str] = []
    writer = await _serve_lines([_init("mcp:test")], _factory_recording(calls))

    frames = writer.frames()
    assert frames, "serve() must reply to init"
    assert frames[0]["op"] == "describe"
    assert frames[0]["protocol"] == 1
    assert calls == ["mcp:test"]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_actor", ["chat:x", "mcp:" + "a" * 41, "mcp:Bad", ""])
async def test_init_with_invalid_actor_is_bad_request_and_builds_no_deps(bad_actor):
    calls: list[str] = []
    writer = await _serve_lines([_init(bad_actor)], _factory_recording(calls))

    frames = writer.frames()
    assert calls == [], "no OperatorDeps may be built for a refused actor"
    assert len(frames) == 1
    assert frames[0]["ok"] is False
    assert frames[0]["error"]["code"] == "bad_request"


@pytest.mark.asyncio
async def test_frame_over_4_mib_is_bad_request():
    calls: list[str] = []
    oversized = b'{"op":"init","id":"1","protocol":1,"actor":"' + b"a" * (FOUR_MIB + 16) + b'"}\n'
    writer = await _serve_lines([oversized], _factory_recording(calls))

    frames = writer.frames()
    assert frames and frames[-1]["ok"] is False
    assert frames[-1]["error"]["code"] == "bad_request"


@pytest.mark.asyncio
async def test_unknown_op_is_bad_request():
    calls: list[str] = []
    lines = [
        _init("mcp:test"),
        (json.dumps({"op": "frobnicate", "id": "2"}) + "\n").encode(),
    ]
    writer = await _serve_lines(lines, _factory_recording(calls))

    results = [f for f in writer.frames() if f.get("id") == "2"]
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert results[0]["error"]["code"] == "bad_request"


@pytest.mark.asyncio
async def test_eof_awaits_poller_aclose():
    closed: list[bool] = []

    async def aclose() -> None:
        closed.append(True)

    def factory(actor: str):
        return SimpleNamespace(poller=SimpleNamespace(aclose=aclose), actor=actor)

    await _serve_lines([_init("mcp:test")], factory)
    assert closed == [True]


def test_bridge_import_loads_no_web_or_worker_modules():
    probe = (
        "import sys, sdlc.operator.bridge; "
        "bad = [m for m in ('fastapi', 'starlette', 'pydantic_ai', "
        "'sdlc.worker') if m in sys.modules]; "
        "print(','.join(bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == ""


@pytest.mark.xfail(
    strict=True,
    reason=(
        "T023 creates tests/mcp_fake_bridge.py; RED until then "
        "(missing file -> non-zero exit). Remove this xfail when T023 lands."
    ),
)
def test_fake_bridge_print_in_verb_keeps_stdout_pure_json(tmp_path):
    marker = "HYGIENE-MARKER-7f3a"
    init = {"op": "init", "id": "1", "protocol": 1, "actor": "mcp:test"}
    call = {"op": "call", "id": "2", "tool": "list_projects", "args": {}}
    stdin = "".join(json.dumps(f) + "\n" for f in (init, call))
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tests" / "mcp_fake_bridge.py"),
            str(tmp_path / "db"),
            str(tmp_path / "record.json"),
            "--print-in-verb",
        ],
        input=stdin,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    for line in result.stdout.splitlines():
        if line.strip():
            json.loads(line)  # every stdout line must be a bridge frame
    assert marker not in result.stdout
    assert marker in result.stderr


# --- describe (T012)--------------------------------------------------------

def _tools():
    # Lazy: READ_TOOLS/WRITE_TOOLS move into sdlc.operator.tools under T007.
    from sdlc.operator import tools

    return tools


def _all_verbs():
    t = _tools()
    return list(t.READ_TOOLS) + list(t.WRITE_TOOLS)


OUTPUT_SCHEMA_TOOLS = {"read_artifact", "follow", "answer_question", "decide_gate"}


async def _describe() -> list[dict]:
    writer = await _serve_lines([_init("mcp:test")], _factory_recording([]))
    frames = writer.frames()
    assert frames[0]["op"] == "describe"
    return frames[0]["tools"]


@pytest.fixture(scope="module")
def descriptors() -> list[dict]:
    return asyncio.run(_describe())


def _by_name(descriptors: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in descriptors}


def test_describe_lists_all_twelve_verbs_in_order(descriptors):
    assert [d["name"] for d in descriptors] == [f.__name__ for f in _all_verbs()]
    assert len(descriptors) == 12


def test_description_is_verbatim_docstring(descriptors):
    by = _by_name(descriptors)
    for fn in _all_verbs():
        assert by[fn.__name__]["description"] == inspect.getdoc(fn)


def test_no_input_schema_exposes_deps(descriptors):
    for d in descriptors:
        assert "deps" not in json.dumps(d["input_schema"]), d["name"]


def test_decide_gate_has_no_thaw_tests_and_start_run_has_no_budget(descriptors):
    by = _by_name(descriptors)
    assert "thaw_tests" not in json.dumps(by["decide_gate"]["input_schema"])
    assert "budget_usd" not in json.dumps(by["start_run"]["input_schema"])


def test_output_schema_present_exactly_for_typed_verbs(descriptors):
    for d in descriptors:
        has = d["output_schema"] is not None
        assert has == (d["name"] in OUTPUT_SCHEMA_TOOLS), d["name"]


def test_read_only_is_true_exactly_for_read_tools(descriptors):
    by = _by_name(descriptors)
    read_names = {fn.__name__ for fn in _tools().READ_TOOLS}
    for name, d in by.items():
        assert d["read_only"] is (name in read_names), name


def test_confirm_values_per_verb(descriptors):
    by = _by_name(descriptors)
    assert by["start_run"]["confirm"] == "start"
    assert by["answer_question"]["confirm"] == "pending"
    assert by["decide_gate"]["confirm"] == "pending"
    for fn in _tools().READ_TOOLS:
        assert by[fn.__name__]["confirm"] == "none", fn.__name__
    for fn in _tools().WRITE_TOOLS:
        assert by[fn.__name__]["confirm"] != "none", fn.__name__


def test_progress_true_only_for_follow(descriptors):
    for d in descriptors:
        assert d["progress"] is (d["name"] == "follow"), d["name"]


def test_enum_schemas_expose_gate_outcome_and_project_mode(descriptors):
    by = _by_name(descriptors)
    decide = json.dumps(by["decide_gate"]["input_schema"])
    start = json.dumps(by["start_run"]["input_schema"])
    assert "GateOutcome" in decide or '"enum"' in decide
    assert "ProjectMode" in start or '"enum"' in start
