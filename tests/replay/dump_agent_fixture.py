"""Dump the pre-migration agent-activity fixture (spec 003, T003).

Run on UNMODIFIED main (203e7dd), before any TemporalDurability migration
change lands:

    uv run --no-sync python tests/replay/dump_agent_fixture.py

The output (``fixtures/agent_activities_pre_migration.json``) is frozen
evidence for FR-005.5c / FR-019 / SC-006a: it records, per durable agent,
the toolset ids, the REGISTERED activity names, the names a Kroker workflow
can SCHEDULE, and the model-request command attributes the old
``TemporalAgent`` wrapper would splat into ``workflow.start_activity``.
It must never be regenerated from migrated code (SG-2 family rule); T024
compares the migrated agents against this file without regenerating it.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Mirror tests/conftest.py: agent construction at import time reads these.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy")
os.environ.setdefault("OPENAI_API_KEY", "test-dummy")
os.environ.setdefault("EXA_API_KEY", "test-dummy")
if not Path(os.environ.get("SDLC_GRAPH_STORE", "")).is_absolute():
    os.environ["SDLC_GRAPH_STORE"] = str(Path(tempfile.gettempdir()) / "sdlc-test-graphs")

from sdlc.agents import roles  # noqa: E402

OUT = Path(__file__).parent / "fixtures" / "agent_activities_pre_migration.json"

# Names a Kroker workflow can actually schedule (research.md R2/R5): the
# non-streaming model request, and per-toolset tool calls for tool-bearing
# agents. event_stream_handler needs a configured handler (Kroker registers
# none), model_request_stream is rejected inside workflows,
# model_cancel_suspended_response is only scheduled for a suspended
# (streamed/deferred) response, which Kroker never creates.
_SCHEDULABLE_SUFFIXES = ("__model_request", "__call_tool")

# Registered-set deltas the capability migration is ALLOWED to make
# (research.md R2, FR-005.3): suffix form, embedded per agent name.
EXPECTED_REGISTERED_DELTA = {
    "removed_suffixes": ["__event_stream_handler"],
    "added_suffixes": ["__model_compact_messages", "__validate_args"],
}


def _activity_name(fn: Any) -> str:
    return fn.__temporal_activity_definition.name


def _model_command(ta: Any) -> dict[str, Any]:
    """The command attributes the wrapper sends with a model-request schedule."""
    model = ta._temporal_model
    cfg = model.activity_config
    retry = cfg.get("retry_policy")
    heartbeat = cfg.get("heartbeat_timeout")
    return {
        "start_to_close_s": cfg["start_to_close_timeout"].total_seconds(),
        "heartbeat_s": heartbeat.total_seconds() if heartbeat is not None else 0,
        "max_attempts": retry.maximum_attempts if retry is not None else None,
        "non_retryable": sorted(retry.non_retryable_error_types or []) if retry is not None else [],
        "arg_count": len(inspect.signature(model.request_activity).parameters),
    }


def _agent_entry(ta: Any) -> dict[str, Any]:
    registered = sorted(_activity_name(fn) for fn in ta.temporal_activities)
    # Toolset ids derive from the registered `toolset__<id>__call_tool` names:
    # `ta.toolsets` both double-lists toolsets (original + temporalized wrapper)
    # and hides leaf toolsets added post-construction (exa), while the frozen
    # names are the identity that matters (FR-002).
    toolset_ids = sorted(
        {m.group(1) for n in registered if (m := re.search(r"__toolset__(.+)__call_tool$", n))}
    )
    return {
        "toolset_ids": toolset_ids,
        "registered": registered,
        "scheduled": [n for n in registered if n.endswith(_SCHEDULABLE_SUFFIXES)],
        "model_command": _model_command(ta),
    }


def _source_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def main() -> None:
    agents = {ta.name: _agent_entry(ta) for ta in roles.ALL_TEMPORAL_AGENTS}
    fixture = {
        "base_commit": _source_commit(),
        "expected_registered_delta": EXPECTED_REGISTERED_DELTA,
        "agents": agents,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(fixture, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    # Dump-time sanity checks (T004): 16 agents; every registered list still
    # carries event_stream_handler; the old wrapper sets no model heartbeat.
    assert len(agents) == 16, f"expected 16 durable agents, got {len(agents)}"
    for name, entry in agents.items():
        assert any(n.endswith("__event_stream_handler") for n in entry["registered"]), name
        assert entry["model_command"]["heartbeat_s"] == 0, name
    print(f"wrote {OUT} ({len(agents)} agents, base {fixture['base_commit'][:7]})")


if __name__ == "__main__":
    main()
