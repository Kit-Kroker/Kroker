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
