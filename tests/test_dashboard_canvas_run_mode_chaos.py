"""RED chaos contracts for the canvas run-mode flip (E75-OQ-1, option (a)).

The ruled change is ONE atomic move: the `validate` and `run_graph` Field
defaults in graph_wire.Capabilities flip to True, the dashboard mock's
fixtures regenerate to match (catalog.json), and the hand-written
provisional recordings are deleted in favour of the final run_state/*
ones the TS mirror parses. Until it lands, every test here is RED ON
PURPOSE -- each names the side that drifted.

Axes covered, and why the others do not apply:
- stale state: every declaration site (the Field defaults, catalog(),
  the shipped catalog.json fixture) is pinned to the SAME ruled set, so
  a half-landed flip -- defaults flipped without regenerating, fixture
  regenerated from an unflipped runtime, an override at a call site --
  fails exactly the test that names the stale side.
- boundary: the ruled set is exactly four alias keys; a fifth capability,
  a dropped one, or a `can_validate` spelling fails the dict equality.
- error path: the swapped-in catalog.json must stay parseable JSON that
  CatalogWire accepts, so a mangled regeneration errors loudly here.
- concurrency: N/A. The catalog is a pure function of the node registry
  and the fixtures are committed static files; the flip touches no
  shared mutable state. Run-graph query caching is landed E-75/E-77
  surface, out of scope for this wiring.

The /graphs/catalog route needs no test here: it serves catalog() live
(api.py) and test_dashboard_graph_routes.py already pins route == runtime.

Deterministic on any machine: reads committed files and calls pure
functions only. Compared parsed, never as bytes (no .gitattributes).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from sdlc.dashboard import graph_wire

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "dump_graph_fixtures", ROOT / "scripts" / "dump_graph_fixtures.py"
)
assert _spec and _spec.loader
dump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dump)

# E75-OQ-1 resolution (a): the canvas runs against live data, so the
# server declares validate and run_graph alongside E-77's save/load.
RULED = {"validate": True, "save": True, "load": True, "run_graph": True}


def test_capability_defaults_are_the_ruled_flip():
    # The change site is the two Field defaults; overriding caps at a
    # call site instead of flipping them leaves this red.
    caps = graph_wire.Capabilities().model_dump(mode="json", by_alias=True)
    assert caps == RULED, f"E75-OQ-1 (a): flip the defaults, got {caps}"


def test_runtime_catalog_declares_the_ruled_capabilities():
    caps = graph_wire.catalog().capabilities.model_dump(mode="json", by_alias=True)
    assert caps == RULED, f"E75-OQ-1 (a): catalog must declare the flip, got {caps}"


def test_shipped_catalog_fixture_declares_the_ruled_capabilities():
    # The frontend mock replays catalog.json; a flip without regeneration
    # leaves the server declaring what the mock denies.
    text = (dump.OUT / "catalog.json").read_text(encoding="utf-8")
    served = graph_wire.CatalogWire.model_validate(json.loads(text))
    caps = served.capabilities.model_dump(mode="json", by_alias=True)
    assert caps == RULED, "catalog.json is stale: run python scripts/dump_graph_fixtures.py"


def test_no_provisional_recordings_survive_the_swap():
    # The ruling swaps the provisional recordings for the final
    # run_state/* ones; a leftover is a stale second contract.
    left = [p.relative_to(dump.OUT).as_posix() for p in dump.OUT.rglob("*.provisional.json")]
    assert left == [], f"provisional recordings must be deleted in the swap: {left}"
