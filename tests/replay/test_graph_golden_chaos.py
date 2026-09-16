"""Chaos + edge-case characterization for E-74 Task 20 (golden equality).

Task 20 lands NO src module -- it is the golden-equality test itself -- so
this file has no import-RED phase: it characterizes the comparison machinery
the SG-3 stop-guard stands on, and it is green by design (every assertion
here holds against the landed harness, projections and golden files; if any
of them starts failing, a golden or a projection function has drifted).

Pins the edge behaviour the task specifies:
- every golden scenario's file exposes ALL of trace / commands / close (a
  golden with a missing entry can never silently pass equality), and
  load_golden rejects unknown names with FileNotFoundError
- the STORAGE side of the reproduction proof: for every golden scenario,
  command_projection(load_history(name)) and close_projection(...) equal the
  golden file's entries EXACTLY -- the recorded history and the committed
  golden are the same data
- a difference is DETECTABLE: renaming a single activity name in the raw
  history JSON changes the command projection at exactly the renamed
  command's index (the projection is an ordered list -- a set or multiset
  comparison would silently accept reorderings and duplicates)
- close_projection of a history with no terminal event is "OPEN": an
  unfinished capture can never masquerade as a real close
- golden traces carry exactly the two contract row shapes (2-field stage
  rows, 5-field gate rows) and are never empty -- a vacuous empty-vs-empty
  trace equality would be a fake reproduction proof
- the SG-3 contract is pinned in tests/replay/test_graph_golden.py itself:
  the three stop-guard messages, EXACT == comparisons (no normalization),
  and the trace check guarded to the unsandboxed mode
"""

from __future__ import annotations

import json

import pytest
from temporalio.client import WorkflowHistory

from tests.replay.harness import GOLDEN, HISTORIES, load_golden, load_history
from tests.replay.projection import close_projection, command_projection
from tests.replay.scenarios import GOLDEN_SCENARIOS

NAMES = [s.name for s in GOLDEN_SCENARIOS]


def test_every_golden_scenario_exposes_all_three_entries():
    for name in NAMES:
        golden = load_golden(name)
        assert set(golden) == {"workflow", "source_commit", "trace", "commands", "close"}, name
        assert isinstance(golden["commands"], list), name
        assert isinstance(golden["close"], str), name
        assert isinstance(golden["trace"], list), name


def test_load_golden_rejects_unknown_names():
    with pytest.raises(FileNotFoundError):
        load_golden("does_not_exist")


@pytest.mark.parametrize("name", NAMES)
def test_command_projection_matches_the_paired_history(name):
    assert command_projection(load_history(name)) == load_golden(name)["commands"]


@pytest.mark.parametrize("name", NAMES)
def test_close_projection_matches_the_paired_history(name):
    assert close_projection(load_history(name)) == load_golden(name)["close"]


def test_command_projection_detects_a_single_renamed_activity():
    path = HISTORIES / "greenfield_happy.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutated_raw = json.dumps(data["history"]).replace('"run_coding_task"', '"run_coding_task_X"', 1)

    mutated = WorkflowHistory.from_json(data["workflow_id"], mutated_raw)
    baseline = command_projection(load_history("greenfield_happy"))
    changed = command_projection(mutated)

    assert baseline != changed
    expected_index = baseline.index("activity:run_coding_task")
    diffs = [i for i, (a, b) in enumerate(zip(baseline, changed, strict=False)) if a != b]
    assert diffs == [expected_index]  # the FIRST difference is the renamed command
    assert (baseline[expected_index], changed[expected_index]) == (
        "activity:run_coding_task",
        "activity:run_coding_task_X",
    )


def test_close_projection_of_a_history_without_a_terminal_event_is_open():
    # partial_awaiting_architecture was terminated on capture... its history
    # ends without a close event, so the projection is the "OPEN" sentinel:
    # an unfinished run can never masquerade as a completed close string
    assert close_projection(load_history("partial_awaiting_architecture")) == "OPEN"


def test_trace_rows_carry_exactly_the_two_contract_shapes():
    for name in NAMES:
        trace = load_golden(name)["trace"]
        assert trace, f"an empty trace would make the equality vacuous: {name}"
        for row in trace:
            if row[0] == "stage":
                assert len(row) == 2, (name, row)
            else:
                assert row[0] == "gate", (name, row)
                assert len(row) == 5, (name, row)  # gate, round, decided_by, approved


def test_sg3_contract_is_pinned_in_the_golden_test_source():
    source = (GOLDEN.parent / "test_graph_golden.py").read_text(encoding="utf-8")

    # the three stop-guard messages: any mismatch fails loudly as SG-3
    assert "SG-3: command projection differs" in source
    assert "SG-3: close differs" in source
    assert "SG-3: stage/gate trace differs" in source
    # EXACT equality: no normalization, no set() -- a reordered command must fail
    assert 'captured.golden["commands"] == golden["commands"]' in source
    assert 'captured.golden["close"] == golden["close"]' in source
    # the trace is only compared under the unsandboxed runner (the recorder
    # cannot see a sandboxed worker's in-memory trace)
    assert "if not sandboxed:" in source
    assert 'captured.golden["trace"] == golden["trace"]' in source
