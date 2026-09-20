"""The dashboard mock's graph recordings equal what the real code produces
(E-76 spec §6.3, §10.1).

Compared PARSED, never as bytes: the repo has no .gitattributes, so a CRLF
checkout must not false-fail. A pydantic upgrade that changes JSON Schema
output turns this red ON PURPOSE -- the served schema really changed.
Regenerate with `python scripts/dump_graph_fixtures.py`; never loosen this.

The chaos section below pins the checks themselves: on a tampered copy of
the fixtures dir they must fail, with the operator-facing message.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "dump_graph_fixtures", ROOT / "scripts" / "dump_graph_fixtures.py"
)
assert _spec and _spec.loader
dump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dump)

PROVISIONAL = {"validation.provisional.json", "run_graphs.provisional.json"}


def test_committed_recordings_equal_a_fresh_build():
    for rel, expected in dump.build().items():
        path = dump.OUT / rel
        assert path.exists(), f"missing {rel}: run python scripts/dump_graph_fixtures.py"
        assert json.loads(path.read_text(encoding="utf-8")) == expected, (
            f"{rel} is stale: run python scripts/dump_graph_fixtures.py"
        )


def test_no_stray_recordings():
    built = set(dump.build())
    on_disk = {p.relative_to(dump.OUT).as_posix() for p in dump.OUT.rglob("*.json")}
    assert on_disk - built == PROVISIONAL


# --- canvas run-mode (E75-OQ-1, bug canvas-run-mode) -- RED contracts --------


def test_committed_catalog_fixture_declares_run_mode_capabilities():
    """The dashboard mock serves the committed catalog.json; canvas run mode
    against it needs run_graph/validate declared true (the committed file
    still serves the pre-flip caps). Regenerate with
    `python scripts/dump_graph_fixtures.py` after the flip -- never hand-edit."""
    caps = json.loads((dump.OUT / "catalog.json").read_text(encoding="utf-8"))["capabilities"]
    assert caps == {"validate": True, "save": True, "load": True, "run_graph": True}


def test_the_provisional_run_fixtures_are_swapped_for_the_recorded_contract():
    """E-75 design §7.4 (F10): the Python-recorded fixtures are the FINAL
    contract the TS mirror catches up to; the mock's hand-written
    *.provisional.json data is swapped out, leaving the fixtures dir exactly
    the fresh build -- no provisional strays remain."""
    on_disk = {p.relative_to(dump.OUT).as_posix() for p in dump.OUT.rglob("*.json")}
    strays = on_disk - set(dump.build())
    assert strays == set(), (
        f"canvas run-mode swap incomplete: {sorted(strays)} must go -- the recorded "
        "fixtures replace the provisional mock data (E-75 design 7.4, E75-OQ-1 (a))"
    )


def test_scenarios_cover_both_parse_outcomes():
    built = dump.build()
    outcomes = {
        rel: obj["parse"]["ok"] for rel, obj in built.items() if rel.startswith("scenarios/")
    }
    assert outcomes["scenarios/pre_code.json"] is True
    assert outcomes["scenarios/bad_yaml.json"] is False
    assert outcomes["scenarios/dangling_edge.json"] is True  # legality is validate's
    assert built["objects/pre_code_intake_renamed_invalid.json"]["parse"]["ok"] is False


# --- chaos: the checks above must actually catch a broken fixtures dir --------


@pytest.fixture
def out_copy(tmp_path, monkeypatch):
    """A throwaway copy of the committed fixtures dir, with dump.OUT aimed at
    it, so the tamper tests wreck the copy instead of the repo."""
    copy = tmp_path / "graph"
    shutil.copytree(dump.OUT, copy)
    monkeypatch.setattr(dump, "OUT", copy)
    return copy


def test_pristine_copy_passes_both_record_checks(out_copy):
    # Control for the tamper tests below: the copy harness itself is faithful,
    # so a tamper test's failure can only come from the tampering.
    test_committed_recordings_equal_a_fresh_build()
    test_no_stray_recordings()


def test_drifted_recording_fails_with_the_stale_message(out_copy):
    rel = "scenarios/pre_code.json"
    obj = json.loads((out_copy / rel).read_text(encoding="utf-8"))
    obj["parse"]["sha"] = "0" * 64
    (out_copy / rel).write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(AssertionError) as excinfo:
        test_committed_recordings_equal_a_fresh_build()
    # pytest's rewriting appends a diff explanation to the raised assert, so
    # pin the check's own message by containment, not the whole str.
    assert f"{rel} is stale: run python scripts/dump_graph_fixtures.py" in str(excinfo.value)


def test_missing_recording_fails_with_the_missing_message(out_copy):
    (out_copy / "catalog.json").unlink()
    with pytest.raises(AssertionError) as excinfo:
        test_committed_recordings_equal_a_fresh_build()
    assert "missing catalog.json: run python scripts/dump_graph_fixtures.py" in str(excinfo.value)


def test_corrupt_recording_fails_loudly(out_copy):
    # Not valid JSON: the check must error, never pass silently.
    (out_copy / "catalog.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        test_committed_recordings_equal_a_fresh_build()


@pytest.mark.parametrize("stray", ["rogue.json", "scenarios/rogue.json"])
def test_stray_recording_fails_the_stray_check(out_copy, stray):
    test_no_stray_recordings()  # the un-tampered copy alone passes
    (out_copy / stray).write_text("{}", encoding="utf-8")
    with pytest.raises(AssertionError):
        test_no_stray_recordings()


# --- chaos: what the recordings themselves promise ----------------------------


@pytest.mark.parametrize(
    "name", ["bad_yaml", "bad_schema_version", "duplicate_top_level_key", "role_typo"]
)
def test_parse_broken_scenarios_record_well_formed_shape_errors(name):
    rec = dump.build()[f"scenarios/{name}.json"]
    parse = rec["parse"]
    assert parse["ok"] is False
    assert parse["shape_errors"], "a parse failure must name at least one shape error"
    for err in parse["shape_errors"]:
        assert isinstance(err["loc"], list)
        assert err["msg"]
        assert err["line"] is None or err["line"] >= 1  # PyYAML marks are 1-based here
        assert err["column"] is None or err["column"] >= 1
    assert rec["serialize"] is None


def test_bad_yaml_shape_error_points_at_line_3_column_1():
    err = dump.build()["scenarios/bad_yaml.json"]["parse"]["shape_errors"][0]
    assert (err["line"], err["column"]) == (3, 1)


@pytest.mark.parametrize("name", ["dangling_edge", "duplicate_node_id", "incompatible_ports"])
def test_legality_broken_scenarios_still_parse(name):
    # Parse is shape-only (spec: duplicate node ids and duplicate edges parse);
    # rejecting these is E-73 validate's legality call, not the loader's.
    rec = dump.build()[f"scenarios/{name}.json"]
    assert rec["parse"]["ok"] is True
    assert rec["parse"]["sha"]
    assert rec["serialize"]["ok"] is True


def test_run_state_recordings_cover_every_outcome_state():
    built = dump.build()
    states = built["run_state/graph_state.recorded.json"]
    assert {name: s["outcome"]["state"] for name, s in states.items()} == {
        "blocked_at_architecture": "running",
        "completed": "completed",
        "escalated_revise_exhausted": "escalated",
        "interrupted": "failed",
        "not_started": "running",
        "rejected_at_architecture": "rejected",
        "unrouted_fail": "failed",
    }
    assert {s["outcome"]["state"] for s in states.values()} == {
        "running",
        "completed",
        "rejected",
        "escalated",
        "failed",
    }
    assert built["run_state/graph_response.recorded.json"]["kind"] == "graph"
    severities = {i["severity"] for i in built["run_state/validation.recorded.json"]["issues"]}
    assert "not_executable" in severities
