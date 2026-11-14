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
    frame = {"op": "init", "id": request_id, "protocol": 1, "actor": actor}
    return (json.dumps(frame) + "\n").encode()


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


# --- reads — parity (T021 happy half) ---------------------------------------
#
# Each text read, called over the bridge `call` op, must return a value that
# is byte-identical to awaiting the verb directly. Two identical deps are
# built from two temp dirs so neither call sees the other's board writes.
# 8 verbs, 10 cases (list_runs x3, get_run x2).

from sdlc.operator import tools  # noqa: E402  (after the framing helpers)
from tests.operator_fakes import RUN_A, build_fake_deps  # noqa: E402


async def _serve_until_reply(lines: list[bytes], factory, reply_id: str) -> _FakeWriter:
    """Serve with stdin held open until the terminal frame for reply_id lands.

    serve() cancels in-flight calls on EOF, so closing stdin right after the
    call frame would race the reply away. Here EOF is fed only once the
    reply exists (or after a 10 s ceiling, so a hang fails instead of stalling).
    """
    bridge = _bridge()
    reader = asyncio.StreamReader()
    for line in lines:
        reader.feed_data(line)
    writer = _FakeWriter()
    task = asyncio.ensure_future(bridge.serve(factory, reader, writer))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 10
    while loop.time() < deadline:
        if any(f.get("id") == reply_id for f in writer.frames()):
            break
        await asyncio.sleep(0.01)
    reader.feed_eof()
    await asyncio.wait_for(task, timeout=10)
    return writer


READ_PARITY_CASES = [
    ("list_runs_open", "list_runs", {"status": "open"}),
    ("list_runs_closed", "list_runs", {"status": "closed"}),
    ("list_runs_all", "list_runs", {"status": "all"}),
    ("get_run_open", "get_run", {"run_id": RUN_A}),
    ("get_run_closed", "get_run", {"run_id": "feature-old-thing"}),
    ("inbox", "inbox", {}),
    ("list_projects", "list_projects", {}),
    ("get_project", "get_project", {"project": "kroker"}),
    ("list_tasks", "list_tasks", {"project": "kroker"}),
    ("project_events", "project_events", {"project": "kroker"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_id", "tool", "args"),
    READ_PARITY_CASES,
    ids=[c[0] for c in READ_PARITY_CASES],
)
async def test_read_call_value_is_byte_identical_to_direct_verb(tmp_path, case_id, tool, args):
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()

    factory = lambda actor: build_fake_deps(shared_dir, actor)  # noqa: E731
    writer = await _serve_until_reply(
        [
            _init("mcp:test"),
            (json.dumps({"op": "call", "id": "2", "tool": tool, "args": args}) + "\n").encode(),
        ],
        factory,
        reply_id="2",
    )
    result_frames = [f for f in writer.frames() if f.get("id") == "2"]

    assert len(result_frames) == 1, f"expected one terminal frame for {case_id}"
    frame = result_frames[0]
    assert frame["ok"] is True, frame
    assert isinstance(frame["value"], str)

    direct_deps = build_fake_deps(shared_dir, "mcp:test")
    expected = await getattr(tools, tool)(direct_deps, **args)

    assert frame["value"] == expected


# --- pending (US2 happy half: preview + call for confirm=pending verbs) -----
#
# RED until T027 lands: preview currently replies "confirm is not wired yet",
# and call without expect_digest replies "confirm tools require expect_digest".
# Every test name carries "pending" so `pytest -k pending` selects this section.

import logging  # noqa: E402
import re  # noqa: E402

from sdlc.channels.contract import default_render  # noqa: E402
from tests.operator_fakes import GATE, Q1, RUN_B  # noqa: E402

GATE_KEY = "architecture#2"


async def _serve_until_all(lines: list[bytes], factory, reply_ids: list[str]) -> _FakeWriter:
    """Serve with stdin open until every reply id has a terminal frame.

    Same rationale as _serve_until_reply: EOF cancels in-flight calls, so
    stdin closes only after the replies it is waiting for have landed.
    """
    bridge = _bridge()
    reader = asyncio.StreamReader()
    for line in lines:
        reader.feed_data(line)
    writer = _FakeWriter()
    task = asyncio.ensure_future(bridge.serve(factory, reader, writer))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 10
    while loop.time() < deadline:
        seen = {f.get("id") for f in writer.frames()}
        if all(rid in seen for rid in reply_ids):
            break
        await asyncio.sleep(0.01)
    reader.feed_eof()
    await asyncio.wait_for(task, timeout=10)
    return writer


def _frame_for(writer: _FakeWriter, rid: str) -> dict:
    found = [f for f in writer.frames() if f.get("id") == rid]
    assert len(found) == 1, f"expected one terminal frame for id {rid!r}, got {found}"
    return found[0]


def _line(frame: dict) -> bytes:
    return (json.dumps(frame) + "\n").encode()


def _preview(rid: str, tool: str, args: dict) -> bytes:
    return _line({"op": "preview", "id": rid, "tool": tool, "args": args})


def _call(rid: str, tool: str, args: dict, digest: str | None = None) -> bytes:
    frame = {"op": "call", "id": rid, "tool": tool, "args": args}
    if digest is not None:
        frame["expect_digest"] = digest
    return _line(frame)


DECIDE_APPROVE = {"run_id": RUN_A, "key": GATE_KEY, "outcome": "approve"}
ANSWER_Q1 = {"run_id": RUN_B, "key": "Q1", "text": "use redis"}


def _holder_factory(tmp_path, holder: dict):
    def factory(actor: str):
        tmp_path.mkdir(parents=True, exist_ok=True)
        holder["deps"] = build_fake_deps(tmp_path, actor)
        return holder["deps"]

    return factory


async def _preview_digest(tmp_path, tool: str, args: dict) -> str:
    holder: dict = {}
    writer = await _serve_until_all(
        [_init("mcp:test"), _preview("2", tool, args)],
        _holder_factory(tmp_path, holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is True, frame
    return frame["value"]["digest"]


@pytest.mark.asyncio
async def test_pending_preview_decide_gate_message_renders_gate_and_proposal(tmp_path):
    holder: dict = {}
    writer = await _serve_until_all(
        [_init("mcp:test"), _preview("2", "decide_gate", DECIDE_APPROVE)],
        _holder_factory(tmp_path, holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is True, frame

    value = frame["value"]
    rendered = default_render(GATE)
    assert rendered.title in value["message"]
    assert rendered.body in value["message"]
    for label, text in rendered.rows:
        assert label in value["message"] and text in value["message"]
    assert "Proposed: approve" in value["message"]
    assert re.fullmatch(r"[0-9a-f]{64}", value["digest"]), value["digest"]


@pytest.mark.asyncio
async def test_pending_preview_digest_is_stable_across_calls(tmp_path):
    first = await _preview_digest(tmp_path / "a", "decide_gate", DECIDE_APPROVE)
    second = await _preview_digest(tmp_path / "b", "decide_gate", DECIDE_APPROVE)
    assert first == second


@pytest.mark.asyncio
async def test_pending_preview_digest_differs_when_outcome_changes(tmp_path):
    approve = await _preview_digest(tmp_path / "a", "decide_gate", DECIDE_APPROVE)
    reject = await _preview_digest(
        tmp_path / "b", "decide_gate", {**DECIDE_APPROVE, "outcome": "reject"}
    )
    assert approve != reject


@pytest.mark.asyncio
async def test_pending_preview_digest_differs_when_text_changes(tmp_path):
    plain = await _preview_digest(tmp_path / "a", "decide_gate", DECIDE_APPROVE)
    with_text = await _preview_digest(
        tmp_path / "b", "decide_gate", {**DECIDE_APPROVE, "text": "looks good"}
    )
    assert plain != with_text


@pytest.mark.asyncio
async def test_pending_call_decide_gate_sends_one_signal_with_reviewer(tmp_path):
    digest = await _preview_digest(tmp_path / "preview", "decide_gate", DECIDE_APPROVE)

    holder: dict = {}
    writer = await _serve_until_all(
        [_init("mcp:test"), _call("2", "decide_gate", DECIDE_APPROVE, digest)],
        _holder_factory(tmp_path / "call", holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is True, frame
    assert frame["value"]["confirmed"] is True

    signals = holder["deps"].recorder.handles[RUN_A].signals
    assert len(signals) == 1, signals
    name, payload = signals[0]
    assert name == "submit_gate_decision"
    decision = payload[0] if isinstance(payload, (list, tuple)) else payload
    assert decision.reviewer == "mcp:test"
    assert decision.decided_by == "human"


@pytest.mark.asyncio
async def test_pending_call_answer_question_sends_key_and_text(tmp_path):
    digest = await _preview_digest(tmp_path / "preview", "answer_question", ANSWER_Q1)

    holder: dict = {}
    writer = await _serve_until_all(
        [_init("mcp:test"), _call("2", "answer_question", ANSWER_Q1, digest)],
        _holder_factory(tmp_path / "call", holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is True, frame
    assert frame["value"]["confirmed"] is True

    signals = holder["deps"].recorder.handles[RUN_B].signals
    assert len(signals) == 1, signals
    name, payload = signals[0]
    assert name == "answer_question"
    assert list(payload) == [Q1.key, "use redis"]


@pytest.mark.asyncio
async def test_pending_call_logs_mcp_write_line_at_info(tmp_path, caplog):
    digest = await _preview_digest(tmp_path / "preview", "decide_gate", DECIDE_APPROVE)

    caplog.set_level(logging.INFO, logger="sdlc.operator.bridge")
    writer = await _serve_until_all(
        [_init("mcp:test"), _call("2", "decide_gate", DECIDE_APPROVE, digest)],
        _holder_factory(tmp_path / "call", {}),
        reply_ids=["2"],
    )
    assert _frame_for(writer, "2")["ok"] is True

    expected = (
        "mcp write actor=mcp:test tool=decide_gate run=feature-add-sso "
        "key=architecture#2 confirmed=True"
    )
    messages = [r.getMessage() for r in caplog.records if r.name == "sdlc.operator.bridge"]
    assert any(re.search(re.escape(expected), m) for m in messages), messages


@pytest.mark.asyncio
async def test_pending_follow_brake_survives_an_intervening_preview(tmp_path):
    # Ten real follow waits would each block up to 60s, so the streak is
    # preset to the brake limit instead: the next follow is already refused.
    holder: dict = {}

    def factory(actor: str):
        deps = build_fake_deps(tmp_path, actor)
        deps.follow_calls = deps.max_follow_calls
        holder["deps"] = deps
        return deps

    writer = await _serve_until_all(
        [
            _init("mcp:test"),
            _line({"op": "call", "id": "2", "tool": "follow", "args": {}}),
            _preview("3", "decide_gate", DECIDE_APPROVE),
            _line({"op": "call", "id": "4", "tool": "follow", "args": {}}),
        ],
        factory,
        reply_ids=["2", "3", "4"],
    )
    first = _frame_for(writer, "2")
    assert first["ok"] is False and first["error"]["code"] == "tool_error", first
    assert "consecutive wait" in first["error"]["message"]

    after = _frame_for(writer, "4")
    assert after["ok"] is False and after["error"]["code"] == "tool_error", after
    assert "consecutive wait" in after["error"]["message"]


# --- pending (T026 error half: refusals and fail-closed confirm) -------------


@pytest.mark.asyncio
async def test_pending_preview_decide_gate_on_question_key_is_tool_error_with_check_kind_sentence(
    tmp_path,
):
    holder: dict = {}
    writer = await _serve_until_all(
        [
            _init("mcp:test"),
            _preview("2", "decide_gate", {"run_id": RUN_B, "key": "Q1", "outcome": "approve"}),
        ],
        _holder_factory(tmp_path, holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is False
    assert frame["error"]["code"] == "tool_error"
    assert (
        frame["error"]["message"]
        == "key 'Q1' on feature-fix-cache takes a text reply; use answer_question"
    )


@pytest.mark.asyncio
async def test_pending_preview_stale_key_is_tool_error_with_nomatch_translation(tmp_path):
    holder: dict = {}
    writer = await _serve_until_all(
        [
            _init("mcp:test"),
            _preview("2", "decide_gate", {**DECIDE_APPROVE, "key": "architecture#99"}),
        ],
        _holder_factory(tmp_path, holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is False
    assert frame["error"]["code"] == "tool_error"
    assert frame["error"]["message"].endswith(
        "This key is no longer pending; re-read the inbox or the run and use a current key."
    )


@pytest.mark.asyncio
async def test_pending_call_without_expect_digest_is_bad_request_and_sends_nothing(tmp_path):
    holder: dict = {}
    writer = await _serve_until_all(
        [_init("mcp:test"), _call("2", "decide_gate", DECIDE_APPROVE)],
        _holder_factory(tmp_path, holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is False
    assert frame["error"]["code"] == "bad_request"
    assert holder["deps"].recorder.handles[RUN_A].signals == []


@pytest.mark.asyncio
async def test_pending_call_with_stale_expect_digest_is_changed_verbatim_and_sends_nothing(
    tmp_path,
):
    digest = await _preview_digest(tmp_path / "p", "decide_gate", DECIDE_APPROVE)

    holder: dict = {}

    def factory(actor: str):
        deps = build_fake_deps(tmp_path / "c", actor)
        handle = deps.recorder.handles[RUN_A]
        handle._pending[0] = handle._pending[0].model_copy(
            update={"spec_summary": "changed underneath you"}
        )
        holder["deps"] = deps
        return deps

    writer = await _serve_until_all(
        [_init("mcp:test"), _call("2", "decide_gate", DECIDE_APPROVE, digest)],
        factory,
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is False
    assert frame["error"]["code"] == "changed"
    assert (
        frame["error"]["message"]
        == "the pending item changed while you were confirming; re-read the inbox and retry"
    )
    assert holder["deps"].recorder.handles[RUN_A].signals == []


@pytest.mark.asyncio
async def test_pending_call_confirmed_false_when_handle_keeps_item_pending(tmp_path):
    digest = await _preview_digest(tmp_path / "p", "decide_gate", DECIDE_APPROVE)

    def factory(actor: str):
        deps = build_fake_deps(tmp_path / "c", actor)
        deps.recorder.handles[RUN_A].drop_on_signal = False
        return deps

    writer = await _serve_until_all(
        [_init("mcp:test"), _call("2", "decide_gate", DECIDE_APPROVE, digest)],
        factory,
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is True
    assert frame["value"]["confirmed"] is False


# --- start (US3 happy half: preview + call for confirm=start, start_run) ----
#
# RED until T032 wires confirm=="start": today both preview and call refuse
# with bad_request "confirm is not wired yet", so _preview_digest fails first.
# qa-chaos appends the error half below this section.
# Every test name carries "start" so `pytest -k start` selects this section.

START_BF = {
    "title": "Add SSO",
    "mode": "brownfield",
    "description": "single sign-on",
    "repo": "https://github.com/acme/api",
}
FLEET_CAP_ENV = "SDLC_FLEET_PENDING_CAP"


@pytest.mark.asyncio
async def test_start_preview_message_lists_title_mode_repo_description(tmp_path, monkeypatch):
    monkeypatch.delenv(FLEET_CAP_ENV, raising=False)
    holder: dict = {}
    writer = await _serve_until_all(
        [_init("mcp:test"), _preview("2", "start_run", START_BF)],
        _holder_factory(tmp_path, holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is True, frame

    message = frame["value"]["message"]
    for needle in ("Add SSO", "brownfield", "https://github.com/acme/api", "single sign-on"):
        assert needle in message, (needle, message)
    assert "fleet:" not in message


@pytest.mark.asyncio
async def test_start_preview_includes_fleet_line_when_cap_set(tmp_path, monkeypatch):
    monkeypatch.setenv(FLEET_CAP_ENV, "3")
    holder: dict = {}
    writer = await _serve_until_all(
        [_init("mcp:test"), _preview("2", "start_run", START_BF)],
        _holder_factory(tmp_path, holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is True, frame
    assert "fleet: 2/3" in frame["value"]["message"], frame["value"]["message"]


@pytest.mark.asyncio
async def test_start_preview_digest_is_stable_and_ignores_the_fleet_cap(tmp_path, monkeypatch):
    monkeypatch.delenv(FLEET_CAP_ENV, raising=False)
    digest_a = await _preview_digest(tmp_path / "a", "start_run", START_BF)

    monkeypatch.setenv(FLEET_CAP_ENV, "3")
    digest_b = await _preview_digest(tmp_path / "b", "start_run", START_BF)

    assert re.fullmatch(r"[0-9a-f]{64}", digest_a), digest_a
    assert re.fullmatch(r"[0-9a-f]{64}", digest_b), digest_b
    assert digest_a == digest_b

    monkeypatch.delenv(FLEET_CAP_ENV, raising=False)
    other_title = await _preview_digest(
        tmp_path / "c", "start_run", {**START_BF, "title": "Add OIDC"}
    )
    assert other_title != digest_a


@pytest.mark.asyncio
async def test_start_call_starts_run_and_returns_the_starter_id(tmp_path, monkeypatch):
    monkeypatch.delenv(FLEET_CAP_ENV, raising=False)
    digest = await _preview_digest(tmp_path / "p", "start_run", START_BF)

    holder: dict = {}
    writer = await _serve_until_all(
        [_init("mcp:test"), _call("2", "start_run", START_BF, digest)],
        _holder_factory(tmp_path / "c", holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is True, frame
    assert frame["value"] == "feature-add-sso"
    assert holder["deps"].recorder.started == [
        {
            "wf_id": "feature-add-sso",
            "title": "Add SSO",
            "mode": "brownfield",
            "description": "single sign-on",
        }
    ]


# --- start (T031 error half: refusals, cap, duplicate, digest swap) ----------


@pytest.mark.asyncio
async def test_start_call_brownfield_without_repo_is_tool_error_and_starter_not_called(
    tmp_path, monkeypatch
):
    monkeypatch.delenv(FLEET_CAP_ENV, raising=False)
    args = {"title": "Add SSO", "mode": "brownfield", "description": "single sign-on"}
    digest = await _preview_digest(tmp_path / "p", "start_run", args)

    holder: dict = {}
    writer = await _serve_until_all(
        [_init("mcp:test"), _call("2", "start_run", args, digest)],
        _holder_factory(tmp_path / "c", holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is False
    assert frame["error"]["code"] == "tool_error"
    assert frame["error"]["message"] == (
        "a brownfield run needs repo set to the repository url; "
        "ask the operator which repository this is for"
    )
    assert holder["deps"].recorder.started == []


@pytest.mark.asyncio
async def test_start_call_fleet_at_cap_is_b4_sentence_and_starter_not_called(tmp_path, monkeypatch):
    monkeypatch.setenv(FLEET_CAP_ENV, "2")  # fleet holds 2 pending runs: AT cap is refused
    args = {"title": "Add SSO", "mode": "greenfield", "description": "single sign-on"}
    digest = await _preview_digest(tmp_path / "p", "start_run", args)

    holder: dict = {}
    writer = await _serve_until_all(
        [_init("mcp:test"), _call("2", "start_run", args, digest)],
        _holder_factory(tmp_path / "c", holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is False
    assert frame["error"]["code"] == "tool_error"
    assert frame["error"]["message"] == (
        "the fleet is at capacity: 2 run(s) are already awaiting a human "
        "decision and the cap is 2. Do not retry; tell the operator to "
        "clear some pending decisions first (the inbox lists them)."
    )
    assert holder["deps"].recorder.started == []


@pytest.mark.asyncio
async def test_start_call_slugless_title_is_slug_sentence_and_starter_not_called(
    tmp_path, monkeypatch
):
    monkeypatch.delenv(FLEET_CAP_ENV, raising=False)
    args = {"title": "!!!", "mode": "greenfield", "description": "punctuation only"}
    digest = await _preview_digest(tmp_path / "p", "start_run", args)

    holder: dict = {}
    writer = await _serve_until_all(
        [_init("mcp:test"), _call("2", "start_run", args, digest)],
        _holder_factory(tmp_path / "c", holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is False
    assert frame["error"]["code"] == "tool_error"
    assert frame["error"]["message"] == (
        "title '!!!' has no letters or digits to build a run id from; "
        "ask the operator for a descriptive title"
    )
    assert holder["deps"].recorder.started == []


@pytest.mark.asyncio
async def test_start_call_duplicate_start_is_duplicate_sentence(tmp_path, monkeypatch):
    monkeypatch.delenv(FLEET_CAP_ENV, raising=False)
    args = {"title": "Add SSO", "mode": "greenfield", "description": "single sign-on"}
    digest = await _preview_digest(tmp_path / "p", "start_run", args)

    holder: dict = {}

    def factory(actor: str):
        deps = build_fake_deps(tmp_path / "c", actor)
        holder["deps"] = deps

        async def already_started(*a, **kw):
            raise Exception("workflow execution already started")

        deps.starter = already_started  # OperatorDeps is a mutable dataclass
        return deps

    writer = await _serve_until_all(
        [_init("mcp:test"), _call("2", "start_run", args, digest)],
        factory,
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is False
    assert frame["error"]["code"] == "tool_error"
    assert frame["error"]["message"] == (
        "a run with id 'feature-add-sso' already exists; call get_run on it, "
        "or start this one under a different title"
    )
    assert holder["deps"].recorder.started == []


@pytest.mark.asyncio
async def test_start_call_swapped_args_expect_digest_is_changed_and_starter_not_called(
    tmp_path, monkeypatch
):
    monkeypatch.delenv(FLEET_CAP_ENV, raising=False)
    digest = await _preview_digest(tmp_path / "p", "start_run", START_BF)

    holder: dict = {}
    writer = await _serve_until_all(
        [
            _init("mcp:test"),
            _call("2", "start_run", {**START_BF, "title": "Add OIDC"}, digest),
        ],
        _holder_factory(tmp_path / "c", holder),
        reply_ids=["2"],
    )
    frame = _frame_for(writer, "2")
    assert frame["ok"] is False
    assert frame["error"]["code"] == "changed"
    assert frame["error"]["message"] == (
        "the pending item changed while you were confirming; re-read the inbox and retry"
    )
    assert holder["deps"].recorder.started == []
