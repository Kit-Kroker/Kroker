"""The golden re-baseline gate (020 T019, plan T042, FR-011, SC-003).

Every test here drives the pure core -- ALLOWED_KEYS and golden_diffs -- so
none of them touch git or write to the tree. The gate's only permitted change
to a golden is the provenance pair (workflow, source_commit); any other key
that differs is a STOP.
"""

from __future__ import annotations

import copy

from scripts.check_golden_rebaseline import ALLOWED_KEYS, golden_diffs

# Mirrors the shape of tests/replay/golden/greenfield_happy.json: provenance
# keys plus the three projections (commands, trace, close).
GOLDEN = {
    "workflow": "FeatureWorkflow",
    "source_commit": "076db3633802c5612449fed1f64413fe3e2770ea",
    "commands": ["activity:classify_repo", "activity:price_usage"],
    "trace": [["stage", "intake"], ["stage", "clarify"], ["gate", "architecture"]],
    "close": "deployed:https://example.test/pr/1",
}


def _with(**changes) -> dict:
    new = copy.deepcopy(GOLDEN)
    new.update(changes)
    return new


def test_allowed_keys_are_exactly_the_provenance_pair():
    assert ALLOWED_KEYS == frozenset({"workflow", "source_commit"})


def test_identical_goldens_have_no_diffs():
    assert golden_diffs(GOLDEN, copy.deepcopy(GOLDEN)) == []


def test_only_provenance_changing_is_allowed():
    new = _with(workflow="GraphWorkflow", source_commit="deadbeef")
    assert golden_diffs(GOLDEN, new) == []


def test_a_trace_change_deep_inside_a_list_is_reported():
    new = copy.deepcopy(GOLDEN)
    new["trace"][1][1] = "plan"  # one element, two levels down
    assert golden_diffs(GOLDEN, new) == ["trace"]


def test_a_commands_change_is_reported():
    new = _with(commands=["activity:classify_repo"])
    assert golden_diffs(GOLDEN, new) == ["commands"]


def test_a_close_change_is_reported():
    new = _with(close="rolled-back:https://example.test/pr/1")
    assert golden_diffs(GOLDEN, new) == ["close"]


def test_a_key_removed_in_the_new_golden_is_reported():
    new = copy.deepcopy(GOLDEN)
    del new["trace"]
    assert golden_diffs(GOLDEN, new) == ["trace"]


def test_a_key_added_in_the_new_golden_is_reported():
    new = _with(extra=["unexpected"])
    assert golden_diffs(GOLDEN, new) == ["extra"]


def test_several_offending_keys_are_all_reported_sorted():
    new = _with(
        commands=["activity:classify_repo"],
        close="rolled-back:https://example.test/pr/1",
        workflow="GraphWorkflow",
    )
    assert golden_diffs(GOLDEN, new) == ["close", "commands"]


def test_a_json_type_change_is_reported():
    """Python says 1 == True, 1 == 1.0 and 0 == False, but the goldens are
    JSON: a type change is a changed projection and must STOP the gate."""
    assert golden_diffs(_with(trace=[["stage", 1]]), _with(trace=[["stage", True]])) == ["trace"]
    assert golden_diffs(_with(commands=[1]), _with(commands=[1.0])) == ["commands"]
    assert golden_diffs(_with(close={"x": 0}), _with(close={"x": False})) == ["close"]


def test_key_order_inside_a_value_is_not_a_diff():
    """Guards against an over-strict canonicalisation: reordering the keys of
    a dict inside a value is not a behavioural change."""
    old = _with(close={"a": 1, "b": [2, 3]})
    new = _with(close={"b": [2, 3], "a": 1})
    assert golden_diffs(old, new) == []


def test_an_allowed_key_present_on_only_one_side_is_ignored():
    """The provenance pair is exempt even one-sided: write_fixtures always
    writes both keys, so a golden that drops workflow is not a projection
    change."""
    new = copy.deepcopy(GOLDEN)
    del new["workflow"]
    assert golden_diffs(GOLDEN, new) == []


def test_nan_values_are_not_a_diff_when_identical():
    """json.loads accepts NaN and NaN != NaN in Python, but two identical
    goldens must not STOP the round."""
    old = _with(close=[float("nan")])
    new = _with(close=[float("nan")])
    assert golden_diffs(old, new) == []
