"""The committed fleet-snapshot fixture equals what the real models build
(006-B3: spec 8's drift guard, made checkable -- the generator is
importable and the fixture is freshness-tested in the fast tier, mirroring
tests/test_graph_fixtures_fresh.py).

Compared PARSED, never as bytes: the repo has no .gitattributes, so a CRLF
checkout must not false-fail. A model change that alters the snapshot JSON
turns this red ON PURPOSE -- the served shape really changed. Regenerate
with `python scripts/dump_dashboard_fixtures.py`; never hand-edit.

The second test pins the project_key teaching in build(): exactly three
rows stay key-ABSENT (the dashboard mapper maps absent and null alike, and
its absent -> null path needs a live example), the two kroker rows carry
the string, and the two graph rows carry an explicit null. Deleting the
omission list turns this red instead of silently un-teaching the cases.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "dump_dashboard_fixtures", ROOT / "scripts" / "dump_dashboard_fixtures.py"
)
assert _spec and _spec.loader
dump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dump)

# The R-2 teaching build() pins next to the fixture: these rows stay
# key-ABSENT on purpose, the kroker rows carry the string, and the graph
# rows carry an explicit null -- three states the TS mapper must tell
# apart. A renamed run must break this test, not silently un-teach it.
OMITTED: set[str] = {"feature-unpriced", "fix-payment-retry", "feature-flag-cleanup"}
KROKER_ROWS: set[str] = {"feature-add-sso", "feature-dark-mode"}
GRAPH_ROWS: set[str] = {"graph-run-live", "graph-run-closed"}


def test_committed_fleet_snapshot_equals_a_fresh_build():
    path = dump.OUT / "fleet-snapshot.json"
    assert path.exists(), f"missing {path.name}: run python scripts/dump_dashboard_fixtures.py"
    assert json.loads(path.read_text(encoding="utf-8")) == dump.build(), (
        f"{path.name} is stale: run python scripts/dump_dashboard_fixtures.py"
    )


def test_project_key_states_are_exactly_as_taught():
    built = dump.build()
    rows = {r["run_id"]: r for r in [*built["runs"], *built["closed"]]}
    lacking = {rid for rid, r in rows.items() if "project_key" not in r}
    kroker = {rid for rid, r in rows.items() if r.get("project_key") == "kroker"}
    # get() cannot tell absent from null -- the explicit-null check needs
    # the key-present guard, that distinction IS the teaching.
    nulls = {rid for rid, r in rows.items() if "project_key" in r and r["project_key"] is None}
    assert lacking == OMITTED
    assert kroker == KROKER_ROWS
    assert nulls == GRAPH_ROWS
    assert lacking | kroker | nulls == set(rows)  # every row in exactly one state
