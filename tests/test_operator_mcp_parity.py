"""End-to-end MCP reads parity: the real kroker-mcp binary over stdio (022 T024).

The server spawns tests/mcp_fake_bridge.py through --bridge-cmd. The bridge
seeds ONE board in shared_dir at init. Direct verb calls run on deps built
over the same shared_dir, so both sides read the same seeded rows (two
separately seeded boards render different seed-time timestamps).

Skipped unless SDLC_MCP_BIN names an executable kroker-mcp binary.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from sdlc.operator import tools
from sdlc.operator.errors import ToolError
from tests.mcp_stdio_client import McpStdioClient
from tests.operator_fakes import RUN_A, build_fake_deps

pytestmark = pytest.mark.mcp

_BIN = os.environ.get("SDLC_MCP_BIN", "")
if not _BIN or not Path(_BIN).is_file() or not os.access(_BIN, os.X_OK):
    pytest.skip("set SDLC_MCP_BIN to a built kroker-mcp binary", allow_module_level=True)

REPO_ROOT = Path(__file__).resolve().parent.parent
FAKE_BRIDGE = REPO_ROOT / "tests" / "mcp_fake_bridge.py"
CLIENT_NAME = "parity-client"
ACTOR = f"mcp:{CLIENT_NAME}"

READ_NAMES = [
    "list_runs",
    "get_run",
    "follow",
    "inbox",
    "list_projects",
    "get_project",
    "list_tasks",
    "project_events",
    "read_artifact",
]

TEXT_CASES = [
    ("list_runs_open", "list_runs", {"status": "open"}),
    ("list_runs_all", "list_runs", {"status": "all"}),
    ("get_run_open", "get_run", {"run_id": RUN_A}),
    ("inbox", "inbox", {}),
    ("list_projects", "list_projects", {}),
    ("get_project", "get_project", {"project": "kroker"}),
    ("list_tasks", "list_tasks", {"project": "kroker"}),
    ("project_events", "project_events", {"project": "kroker"}),
]


@pytest.fixture(scope="module")
def shared_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("parity-board")


@pytest.fixture(scope="module")
def mcp(shared_dir, tmp_path_factory):
    record = tmp_path_factory.mktemp("parity-record") / "record.json"
    argv = [
        _BIN,
        "--repo",
        str(REPO_ROOT),
        "--bridge-cmd",
        sys.executable,
        str(FAKE_BRIDGE),
        str(shared_dir),
        str(record),
    ]
    client = McpStdioClient(argv)
    try:
        client.initialize(client_name=CLIENT_NAME)
        yield client
    finally:
        client.close()


@pytest.fixture(scope="module")
def tool_list(mcp) -> list[dict]:
    # First tools/list awaits the bridge's describe, which seeds the board.
    return mcp.list_tools()["tools"]


@pytest.fixture(scope="module")
def direct(shared_dir):
    return build_fake_deps(shared_dir, ACTOR)


def _text(result: dict) -> str:
    blocks = result["content"]
    assert len(blocks) == 1, blocks
    assert blocks[0]["type"] == "text", blocks[0]
    return blocks[0]["text"]


# --- reads ------------------------------------------------------------------


def test_reads_tools_list_names_match_python_verb_order(tool_list):
    expected = [f.__name__ for f in tools.READ_TOOLS + tools.WRITE_TOOLS]
    assert [t["name"] for t in tool_list] == expected


def test_reads_no_schema_leaks_deps_or_forbidden_fields(tool_list):
    by = {t["name"]: t for t in tool_list}
    for t in tool_list:
        assert "deps" not in t["inputSchema"].get("properties", {}), t["name"]
    assert "thaw_tests" not in json.dumps(by["decide_gate"]["inputSchema"])
    assert "budget_usd" not in json.dumps(by["start_run"]["inputSchema"])


def test_reads_every_read_tool_is_annotated_read_only(tool_list):
    by = {t["name"]: t for t in tool_list}
    for name in READ_NAMES:
        assert by[name]["annotations"]["readOnlyHint"] is True, name


@pytest.mark.parametrize(
    ("case_id", "tool", "args"),
    TEXT_CASES,
    ids=[c[0] for c in TEXT_CASES],
)
def test_reads_text_read_over_mcp_is_byte_identical_to_direct_verb(
    mcp, direct, case_id, tool, args
):
    result = mcp.call_tool(tool, args)
    assert result.get("isError") in (False, None), result
    expected = asyncio.run(getattr(tools, tool)(direct, **args))
    assert _text(result) == expected


def test_reads_read_artifact_structured_content_matches_direct_model(mcp, tool_list, direct):
    by = {t["name"]: t for t in tool_list}
    assert by["read_artifact"]["outputSchema"] is not None

    result = mcp.call_tool("read_artifact", {"project": "kroker", "key": "spec"})
    assert result.get("isError") in (False, None), result

    expected = asyncio.run(tools.read_artifact(direct, "kroker", "spec"))
    assert result["structuredContent"] == expected.model_dump(mode="json")
    assert result["structuredContent"]["truncated"] is True
    assert result["structuredContent"]["next_offset"] == 32768


def test_reads_get_run_unknown_id_is_iserror_with_verbatim_tool_error(mcp, direct):
    result = mcp.call_tool("get_run", {"run_id": "nope"})
    assert result["isError"] is True

    with pytest.raises(ToolError) as exc:
        asyncio.run(tools.get_run(direct, "nope"))
    assert _text(result) == exc.value.message


# --- decide_or_answer (US2 acceptance over the real binary, T030) -----------
#
# Each test spawns its own server + fake bridge so the signal record can be
# read after the bridge exits (it is written on exit, not on signal).

from contextlib import contextmanager  # noqa: E402

from sdlc.channels.contract import default_render  # noqa: E402
from tests.mcp_stdio_client import MRTR_PROTOCOL, OLD_PROTOCOL  # noqa: E402
from tests.operator_fakes import GATE  # noqa: E402

E1_CAPS = {"elicitation": {"form": {}}}
MRTR_META = {
    "io.modelcontextprotocol/protocolVersion": MRTR_PROTOCOL,
    "io.modelcontextprotocol/clientCapabilities": E1_CAPS,
}
ACCEPT = {"action": "accept", "content": {"confirm": True}}
DECIDE_ARGS = {"run_id": "feature-add-sso", "key": "architecture#2", "outcome": "approve"}
ANSWER_ARGS = {"run_id": "feature-fix-cache", "key": "Q1", "text": "use redis"}
NOT_CONFIRMED = "the operator did not confirm; nothing was changed"
NO_PATH = (
    "this write needs a human confirmation that this MCP client did not provide; "
    "nothing was changed. Use the dashboard or `python -m sdlc.cli` instead."
)
INVALID = (
    "this confirmation is invalid or was already used; nothing was changed — call the tool again"
)


@contextmanager
def _session(tmp_path, *, protocol=OLD_PROTOCOL, caps=E1_CAPS, env=None):
    """Spawn the real binary + fake bridge; yield (client, record_path).

    The record is written when the bridge exits, so read it only after this
    context has closed the client.
    """
    shared = tmp_path / "board"
    shared.mkdir(parents=True, exist_ok=True)
    record = tmp_path / "record.json"
    argv = [
        _BIN,
        "--repo",
        str(REPO_ROOT),
        "--bridge-cmd",
        sys.executable,
        str(FAKE_BRIDGE),
        str(shared),
        str(record),
    ]
    client = McpStdioClient(argv, env=env)
    try:
        client.initialize(protocol_version=protocol, capabilities=caps, client_name=CLIENT_NAME)
        yield client, record
    finally:
        client.close()


def _signals(record: Path) -> list[dict]:
    return json.loads(record.read_text(encoding="utf-8"))["signals"]


def test_decide_or_answer_e1_accept_confirms_and_signals(tmp_path):
    with _session(tmp_path) as (client, record):
        result = client.call_tool("decide_gate", DECIDE_ARGS)
    assert not result.get("isError")
    assert result["structuredContent"]["confirmed"] is True

    signals = _signals(record)
    assert len(signals) == 1, signals
    assert signals[0]["name"] == "submit_gate_decision"
    assert signals[0]["run_id"] == "feature-add-sso"
    assert '"reviewer": "mcp:parity-client"' in json.dumps(signals[0]["args"])

    assert default_render(GATE).title in client.elicited[0]["message"]


def test_decide_or_answer_e1_decline_sends_nothing(tmp_path):
    with _session(tmp_path) as (client, record):
        client.elicitation = ("decline",)
        result = client.call_tool("decide_gate", DECIDE_ARGS)
    assert result["isError"] is True
    assert _text(result) == NOT_CONFIRMED
    assert _signals(record) == []


def test_decide_or_answer_no_capability_fails_closed(tmp_path):
    with _session(tmp_path, caps={}) as (client, record):
        result = client.call_tool("decide_gate", DECIDE_ARGS)
    assert result["isError"] is True
    assert _text(result) == NO_PATH
    assert _signals(record) == []
    assert client.elicited == []


def test_decide_or_answer_e2_accept_then_replay_is_refused(tmp_path):
    with _session(tmp_path, protocol=MRTR_PROTOCOL) as (client, record):
        first = client.call_tool("decide_gate", DECIDE_ARGS, meta=MRTR_META)
        assert first.get("resultType") == "input_required", first
        state = first["requestState"]

        accepted = client.call_tool_retry(
            "decide_gate", DECIDE_ARGS, {"confirm": ACCEPT}, state, meta=MRTR_META
        )
        assert not accepted.get("isError")
        assert accepted["structuredContent"]["confirmed"] is True

        replay = client.call_tool_retry(
            "decide_gate", DECIDE_ARGS, {"confirm": ACCEPT}, state, meta=MRTR_META
        )
    assert replay["isError"] is True
    assert _text(replay) == INVALID

    signals = _signals(record)
    assert len(signals) == 1, signals
    assert signals[0]["name"] == "submit_gate_decision"


def test_decide_or_answer_answer_question_e1_signals_key_and_text(tmp_path):
    with _session(tmp_path) as (client, record):
        result = client.call_tool("answer_question", ANSWER_ARGS)
    assert not result.get("isError")
    assert result["structuredContent"]["confirmed"] is True

    signals = _signals(record)
    assert len(signals) == 1, signals
    assert signals[0]["name"] == "answer_question"
    assert signals[0]["run_id"] == "feature-fix-cache"
    dumped = json.dumps(signals[0]["args"])
    assert '"Q1"' in dumped and '"use redis"' in dumped


def test_decide_or_answer_keep_pending_reports_confirmed_false(tmp_path):
    with _session(tmp_path, env={"SDLC_FAKE_KEEP_PENDING": "1"}) as (client, record):
        result = client.call_tool("decide_gate", DECIDE_ARGS)
    assert not result.get("isError")
    assert result["structuredContent"]["confirmed"] is False
    assert len(_signals(record)) == 1


def test_decide_or_answer_write_tool_annotations(tmp_path):
    with _session(tmp_path) as (client, _record):
        listed = client.list_tools()["tools"]
    by = {t["name"]: t for t in listed}
    for name in ("start_run", "answer_question", "decide_gate"):
        ann = by[name]["annotations"]
        assert ann["destructiveHint"] is True, name
        assert ann["readOnlyHint"] is False, name


# --- start (US3 acceptance over the real binary, T033) ----------------------
#
# Reuses _session (E1 caps, OLD protocol, client "parity-client"). The record
# carries "started" entries as well as "signals"; read it only after the
# session context has closed the client.

START_ARGS = {"title": "Add SSO", "mode": "greenfield", "description": "single sign-on"}
BF_NO_REPO = {"title": "Add SSO", "mode": "brownfield", "description": "single sign-on"}
BROWNFIELD_SENTENCE = (
    "a brownfield run needs repo set to the repository url; "
    "ask the operator which repository this is for"
)


def _started(record: Path) -> list[dict]:
    return json.loads(record.read_text(encoding="utf-8"))["started"]


def test_start_accept_elicits_and_records_one_start(tmp_path):
    with _session(tmp_path) as (client, record):
        result = client.call_tool("start_run", START_ARGS)
    assert not result.get("isError")
    assert _text(result) == "feature-add-sso"

    assert "Add SSO" in client.elicited[0]["message"]
    assert "greenfield" in client.elicited[0]["message"]

    assert _started(record) == [
        {
            "wf_id": "feature-add-sso",
            "title": "Add SSO",
            "mode": "greenfield",
            "description": "single sign-on",
        }
    ]
    assert _signals(record) == []


def test_start_decline_records_nothing(tmp_path):
    with _session(tmp_path) as (client, record):
        client.elicitation = ("decline",)
        result = client.call_tool("start_run", START_ARGS)
    assert result["isError"] is True
    assert _text(result) == NOT_CONFIRMED
    assert _started(record) == []
    assert _signals(record) == []


def test_start_brownfield_without_repo_refused_after_confirmation(tmp_path):
    with _session(tmp_path) as (client, record):
        result = client.call_tool("start_run", BF_NO_REPO)
    assert result["isError"] is True
    assert _text(result) == BROWNFIELD_SENTENCE
    assert client.elicited, "a human must be asked before the refusal"
    assert _started(record) == []
