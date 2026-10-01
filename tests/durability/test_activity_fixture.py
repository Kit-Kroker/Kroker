"""Frozen-fixture verification for the MIGRATED durable agents (T024).

The migration landed in Phase 3, so these run GREEN — and are built to fail
LOUDLY if any frozen value drifted. The fixture
tests/replay/fixtures/agent_activities_pre_migration.json was dumped on
UNMODIFIED main (tests/replay/dump_agent_fixture.py documents the derivation
rules) and is never regenerated (SG-2 family rule): the migrated agents must
reproduce its scheduled names, toolset ids and model-command attributes
exactly, with the registered surface differing only by
expected_registered_delta.
"""

import inspect
import json
import re
from pathlib import Path

from pydantic_ai.durable_exec.temporal import TemporalDurability

from sdlc.agents.roles import ALL_TEMPORAL_AGENTS

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "replay"
    / "fixtures"
    / "agent_activities_pre_migration.json"
)

_FREEZE_COMMIT = "203e7dde4b86ae496319b6eb8ae2f55a110bb352"
_SCHEDULABLE = ("__model_request", "__call_tool")
_TOOLSET_RE = re.compile(r"__toolset__(.+)__call_tool$")

# The two inline fan-out agents (roles.py builds them directly with
# CLARIFY_FANOUT_ACTIVITY_CONFIG). The fixture pins their values too.
_FANOUT_AGENTS = ("clarify_route_agent", "clarify_probe_agent")
_FANOUT_MAX_ATTEMPTS = 3


def _fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _agents_by_name() -> dict:
    return {agent.name: agent for agent in ALL_TEMPORAL_AGENTS}


def _bound(agent) -> TemporalDurability:
    bound = TemporalDurability.from_agent(agent)
    assert bound is not None, f"{agent.name} lost its TemporalDurability capability"
    return bound


def _registered(bound) -> list[str]:
    """Sorted registered activity names (the dump sorted too — order matters
    for the exact-list comparisons)."""
    names = [getattr(fn, "__temporal_activity_definition").name for fn in bound.temporal_activities]
    return sorted(names)


def test_fixture_pins_the_freeze_commit():
    """The comparison target is the pre-migration capture, not a regenerated
    file: pin the commit it was dumped on."""
    assert _fixture()["base_commit"] == _FREEZE_COMMIT


def test_scheduled_and_toolset_ids_unchanged():
    """Per agent: the schedulable names (model_request + per-toolset
    call_tool, the dump's suffix rule) and the toolset ids derived from the
    registered names are EXACTLY the fixture's."""
    fixture = _fixture()
    agents = _agents_by_name()
    for name, entry in fixture["agents"].items():
        registered = _registered(_bound(agents[name]))  # KeyError = vanished agent
        scheduled = [n for n in registered if n.endswith(_SCHEDULABLE)]
        toolset_ids = sorted({m.group(1) for n in registered if (m := _TOOLSET_RE.search(n))})
        assert scheduled == entry["scheduled"], name
        assert toolset_ids == entry["toolset_ids"], name


def test_registered_delta_matches_expected_registered_delta():
    """Per agent: the migrated registered set differs from the fixture's ONLY
    by the fixture's own expected_registered_delta — removed suffixes absent,
    added suffixes present, every other name still registered."""
    fixture = _fixture()
    delta = fixture["expected_registered_delta"]
    agents = _agents_by_name()
    for name, entry in fixture["agents"].items():
        actual = set(_registered(_bound(agents[name])))
        old = set(entry["registered"])
        for gone in sorted(old - actual):
            assert any(gone.endswith(s) for s in delta["removed_suffixes"]), (name, gone)
        for fresh in sorted(actual - old):
            assert any(fresh.endswith(s) for s in delta["added_suffixes"]), (name, fresh)
        for kept in entry["registered"]:
            if not any(kept.endswith(s) for s in delta["removed_suffixes"]):
                assert kept in actual, (name, kept)


def test_model_command_attributes_equal():
    """Per agent: the bound capability's effective model-request command
    attributes equal the fixture's model_command exactly (full dict diff on
    drift)."""
    fixture = _fixture()
    agents = _agents_by_name()
    for name, entry in fixture["agents"].items():
        bound = _bound(agents[name])
        # _model_activity_config is private on installed pydantic_ai 2.51 and
        # is the ONLY surface carrying the effective MERGED model activity
        # config (base config + model overrides) — the same justification the
        # loader's heartbeat check in build_agents uses.
        cfg = bound._model_activity_config
        retry = cfg.get("retry_policy")
        heartbeat = cfg.get("heartbeat_timeout")
        actual = {
            "start_to_close_s": cfg["start_to_close_timeout"].total_seconds(),
            "heartbeat_s": heartbeat.total_seconds() if heartbeat is not None else 0,
            "max_attempts": retry.maximum_attempts if retry is not None else None,
            "non_retryable": (
                sorted(retry.non_retryable_error_types or []) if retry is not None else []
            ),
            "arg_count": len(inspect.signature(bound.request_activity).parameters),
        }
        assert actual == entry["model_command"], name


def test_no_cross_agent_duplicate_registration():
    """Every schedulable name from the fixture union is registered exactly
    once across ALL agents — no cross-agent duplicate Temporal activity
    registration."""
    fixture = _fixture()
    agents = _agents_by_name()
    every: list[str] = []
    for name in fixture["agents"]:
        every.extend(_registered(_bound(agents[name])))
    union = sorted({n for entry in fixture["agents"].values() for n in entry["scheduled"]})
    for n in union:
        assert every.count(n) == 1, n


def test_fanout_agents_keep_their_own_bounded_config():
    """The two inline fan-out agents keep the D3 bounded activity config: the
    bound activity_config's retry maximum_attempts is the fixture-pinned 3."""
    fixture = _fixture()
    agents = _agents_by_name()
    for name in _FANOUT_AGENTS:
        assert name in fixture["agents"], name  # the fixture pins them too
        retry = _bound(agents[name]).activity_config.get("retry_policy")
        assert retry is not None, name
        assert retry.maximum_attempts == _FANOUT_MAX_ATTEMPTS, name
