"""The dashboard mock's read-route recordings equal what the real code
produces (018 T047; read-routes rule 4).

Compared PARSED, never as bytes: a CRLF checkout must not false-fail. A
code change that turns this red is a real wire change -- regenerate with
``python scripts/dump_read_fixtures.py``; never loosen this, never
hand-edit the fixtures.

The chaos section pins the check itself: on a hand-edited copy of the
fixtures dir the freshness check must fail.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "dump_read_fixtures", ROOT / "scripts" / "dump_read_fixtures.py"
)
assert _spec and _spec.loader
dump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dump)


def test_committed_recordings_equal_a_fresh_build():
    for rel, expected in dump.build().items():
        path = dump.OUT / rel
        assert path.exists(), f"missing {rel}: run python scripts/dump_read_fixtures.py"
        assert json.loads(path.read_text(encoding="utf-8")) == expected, (
            f"{rel} is stale: run python scripts/dump_read_fixtures.py"
        )


def test_no_stray_recordings():
    built = set(dump.build())
    on_disk = {p.relative_to(dump.OUT).as_posix() for p in dump.OUT.rglob("*.json")}
    assert on_disk - built == set(), f"stray read fixtures: {sorted(on_disk - built)}"


def test_the_recording_covers_every_wire_arm():
    """The fixture must exercise the summary's arms: shipped, custom, legacy
    and unreadable — a fixture that quietly lost an arm would leave the mock
    replaying a narrower contract than the route serves."""
    obj = json.loads((dump.OUT / "fleet-summary.json").read_text(encoding="utf-8"))
    by_id = {r["run_id"]: r for r in obj["runs"]}
    assert by_id["graph-run"]["graph_name"] == "default"
    assert by_id["custom-run"]["graph_name"] is None
    assert by_id["legacy-run"]["graph_sha"] is None
    assert obj["unreadable"] == ["unreadable-run"]


# --- chaos: the check above must actually catch a hand-edited fixture --------


@pytest.fixture
def out_copy(tmp_path, monkeypatch):
    """A throwaway copy of the committed fixtures dir, with dump.OUT aimed at
    it, so the tamper tests wreck the copy instead of the repo."""
    copy = tmp_path / "read"
    shutil.copytree(dump.OUT, copy)
    monkeypatch.setattr(dump, "OUT", copy)
    return copy


def test_pristine_copy_passes_the_record_check(out_copy):
    # Control for the tamper test: the harness is faithful, so a failure
    # below can only come from the tampering.
    test_committed_recordings_equal_a_fresh_build()


def test_hand_edited_recording_fails_with_the_stale_message(out_copy):
    rel = "fleet-summary.json"
    obj = json.loads((out_copy / rel).read_text(encoding="utf-8"))
    obj["runs"][0]["graph_name"] = "hand-edited"
    (out_copy / rel).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(AssertionError, match=r"stale: run python scripts/dump_read_fixtures.py"):
        test_committed_recordings_equal_a_fresh_build()
