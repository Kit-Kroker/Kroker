"""Record the v5 read-route fixtures the dashboard mock replays (018 T047;
read-routes rule 4).

    python scripts/dump_read_fixtures.py

Built from the T045 test inputs (the same fakes, never live data): the
recorded ``fleet-summary.json`` is what the real ``fleet_summary()`` code
produces over those handles, and tests/test_read_fixtures_fresh.py fails
when the committed JSON no longer equals what ``build()`` produces.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# The registry reads provider keys at construction (the test tier's conftest
# does the same for imports); offline dummies, exactly like tests/conftest.py.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy")
os.environ.setdefault("OPENAI_API_KEY", "test-dummy")
os.environ.setdefault("EXA_API_KEY", "test-dummy")
os.environ.setdefault("ZAI_API_KEY", "test-dummy")

OUT = ROOT / "interfaces" / "dashboard" / "frontend" / "src" / "api" / "__fixtures__" / "read"

from temporalio.client import WorkflowExecutionStatus  # noqa: E402

from sdlc.core.models import GateConfig, PipelineConfig  # noqa: E402
from sdlc.dashboard.catalog_wire import shipped_graphs  # noqa: E402
from sdlc.dashboard.compare_wire import compare  # noqa: E402
from sdlc.dashboard.fleet_summary import fleet_summary  # noqa: E402
from sdlc.dashboard.interfaces_wire import interfaces  # noqa: E402
from sdlc.dashboard.run_graph import RunGraphs  # noqa: E402
from sdlc.graph.store import GraphStore  # noqa: E402
from sdlc.workflows.graph_catalog import build_run_input  # noqa: E402
from tests.fakes.canned import greenfield_idea  # noqa: E402
from tests.graph.fixtures.registries import graph as ggraph  # noqa: E402
from tests.graph.fixtures.registries import node as gnode  # noqa: E402
from tests.test_dashboard_fleet_summary import _InputHandle, _Poller  # noqa: E402
from tests.test_dashboard_run_graph_routes import RUN_INPUT, _Client, _Handle  # noqa: E402

_OPEN_RUNS = ["graph-run", "gated-run", "custom-run", "legacy-run"]
_CLOSED_RUNS = ["closed-run"]

# 018 T083: module scope on purpose. The Temporal replay tests rebind
# sdlc.graph.validate to the SUBMODULE through the workflow sandbox
# importer; a runtime import then picks up the module (not callable).
from sdlc.graph import NODE_TYPES, GraphRunView, validate  # noqa: E402


def _build_inputs() -> tuple[_Poller, RunGraphs]:
    """The T045 fixture inputs, rebuilt without pytest: the same handles and
    poller seam the route tests drive."""
    gated_input = build_run_input(
        greenfield_idea(), PipelineConfig(gates={"architecture": GateConfig()})
    )
    custom_input = RUN_INPUT.model_copy(
        update={"graph": ggraph([gnode("custom_a", "intake"), gnode("custom_b", "code")], [])}
    )

    def _view_for(run_input):
        topology = validate(run_input.graph, NODE_TYPES, roles=run_input.roles).topology
        if topology is None:
            return None
        from sdlc.graph import GraphRouter

        return GraphRunView(
            graph_sha=run_input.graph.content_sha(), state=GraphRouter(topology).start().state
        )

    handles = {
        "graph-run": _Handle(view=_view_for(RUN_INPUT)),
        "gated-run": _InputHandle(gated_input, view=_view_for(gated_input)),
        "custom-run": _InputHandle(custom_input, view=None),
        "closed-run": _InputHandle(
            RUN_INPUT, status=WorkflowExecutionStatus.COMPLETED, view=_view_for(RUN_INPUT)
        ),
        "legacy-run": _Handle(wf_type="FeatureWorkflow"),
    }
    poller = _Poller(open_ids=_OPEN_RUNS + ["unreadable-run"], closed_ids=_CLOSED_RUNS)
    # A throwaway store under the system temp: the read route never writes
    # (the readonly source guarantees it), so the store stays empty.
    store = GraphStore(Path(os.environ.get("TEMP", "/tmp")) / "kroker-read-fixture-store")
    client = _Client(handles)

    async def get_client():
        return client

    return poller, RunGraphs(get_client, store=store)


def build() -> dict[str, Any]:
    poller, run_graphs = _build_inputs()
    wire = asyncio.run(fleet_summary(poller, run_graphs))
    # 018 T068 (R-9): the compare recording reads the same fixture tree the
    # route tests drive (tests/fixtures/compare - never live data).
    compare_wire = compare(runs_root=str(ROOT / "tests" / "fixtures" / "compare"))
    return {
        "fleet-summary.json": json.loads(wire.model_dump_json()),
        "graphs-shipped.json": json.loads(shipped_graphs().model_dump_json()),
        "compare.json": json.loads(compare_wire.model_dump_json()),
        # 018 T075 (R-8): the interfaces recording over the shipped policy
        # and the repo's own registry - the same read the route serves.
        "interfaces.json": json.loads(interfaces().model_dump_json()),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for rel, obj in build().items():
        (OUT / rel).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {OUT / rel}")


if __name__ == "__main__":
    main()
