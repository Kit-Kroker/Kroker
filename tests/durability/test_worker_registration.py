"""Worker registration tests for the 003 durability seam (T020, FR-007).

After roles.py hands out plain capability-durable agents, the worker must
register every agent's durable activities via
`TemporalDurability.from_agent(a).temporal_activities` — exactly once, with
no hand-maintained name list. The frozen fixture
tests/replay/fixtures/agent_activities_pre_migration.json records the
PRE-migration registration surface; the post-migration surface may differ
ONLY by expected_registered_delta (event_stream_handler gone,
model_compact_messages and validate_args added).

RED right now: src/sdlc/worker.py still calls `ta.temporal_activities` on
plain Agents, so get_worker_activities() raises AttributeError.
"""

import json
from pathlib import Path

from sdlc.worker import get_worker_activities

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "replay"
    / "fixtures"
    / "agent_activities_pre_migration.json"
)


def _fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _registered_names() -> list[str]:
    """Every activity name the worker would register, as a LIST (order and
    duplicates preserved — exactly-once is the assertion, not a set trick)."""
    names: list[str] = []
    for fn in get_worker_activities():
        defn = getattr(fn, "__temporal_activity_definition", None)
        if defn is not None:  # temporalio's own decoration, as Worker resolves it
            names.append(defn.name)
    return names


def test_every_agent_activity_registered_exactly_once():
    """FR-007: no duplicate activity names across the whole worker, and every
    fixture agent's model_request lands exactly once — without any
    hand-maintained list in worker.py."""
    names = _registered_names()
    assert len(names) == len(set(names)), "duplicate activity registration"
    for agent_name in _fixture()["agents"]:
        assert names.count(f"agent__{agent_name}__model_request") == 1


def test_every_schedulable_name_from_the_fixture_is_registered():
    """Every name the pre-migration worker could SCHEDULE must still be
    schedulable: the union of the fixture's per-agent 'scheduled' lists is a
    subset of what the migrated worker registers."""
    scheduled: set[str] = set()
    for info in _fixture()["agents"].values():
        scheduled.update(info["scheduled"])
    assert scheduled <= set(_registered_names())


def test_registered_agent_delta_matches_expectation():
    """The post-migration surface differs from the fixture's pre-migration
    'registered' list ONLY by expected_registered_delta: every name that
    disappeared ends with a removed suffix, every new name ends with an
    added suffix, and every other name survives. research has TWO toolsets,
    so its __validate_args delta applies per toolset id — at least one must
    be present."""
    fixture = _fixture()
    delta = fixture["expected_registered_delta"]
    names = _registered_names()
    for agent_name, info in fixture["agents"].items():
        prefix = f"agent__{agent_name}__"
        actual = [n for n in names if n.startswith(prefix)]
        old = info["registered"]
        for gone in (n for n in old if n not in actual):
            assert any(gone.endswith(s) for s in delta["removed_suffixes"]), (
                f"{gone} disappeared without a removed_suffix"
            )
        for fresh in (n for n in actual if n not in old):
            assert any(fresh.endswith(s) for s in delta["added_suffixes"]), (
                f"{fresh} appeared without an added_suffix"
            )
        for kept in old:
            if not any(kept.endswith(s) for s in delta["removed_suffixes"]):
                assert kept in actual, f"{kept} did not survive the migration"
        if agent_name == "research_agent":
            assert sum(n.endswith("__validate_args") for n in actual) >= 1, (
                "research validate_args missing"
            )
