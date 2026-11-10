# tests/test_inbox_query.py
"""E-88 step 2 §E. The visibility filter has TWO callers that want different
answers: the inbox lists what a human owes a decision on, and a crew's gate
is exactly that; the fleet lists RUNS, and a crew child is part of a run
rather than one. Widening a shared constant would have silently changed
both."""

from __future__ import annotations

import asyncio

from sdlc.channels.inbox import _open_runs_query, fetch_inbox, list_open_run_ids


class _WF:
    def __init__(self, id):
        self.id = id


class _Client:
    def __init__(self):
        self.queries = []

    def list_workflows(self, query):
        self.queries.append(query)

        async def _gen():
            yield _WF("run-1")

        return _gen()


def test_the_query_wraps_a_single_type():
    assert _open_runs_query("GraphWorkflow") == (
        "(WorkflowType='GraphWorkflow') AND ExecutionStatus='Running'"
    )


def test_the_query_ors_every_named_type():
    q = _open_runs_query("FeatureWorkflow", "CrewTaskWorkflow")
    assert q == (
        "(WorkflowType='FeatureWorkflow' OR "
        "WorkflowType='CrewTaskWorkflow') AND "
        "ExecutionStatus='Running'"
    )


def test_list_open_run_ids_stays_narrow_by_default():
    """The default is GraphWorkflow only (020 T024, FR-005): FeatureWorkflow
    is no longer an open-run type, and a crew child is not a run."""
    c = _Client()
    asyncio.run(list_open_run_ids(c))
    assert "GraphWorkflow" in c.queries[0]
    assert "FeatureWorkflow" not in c.queries[0]
    assert "CrewTaskWorkflow" not in c.queries[0]


def test_the_inbox_can_ask_for_crew_children_too():
    c = _Client()
    asyncio.run(list_open_run_ids(c, "GraphWorkflow", "CrewTaskWorkflow"))
    assert "CrewTaskWorkflow" in c.queries[0]


def test_fetch_inbox_asks_for_graph_and_crew_only():
    """fetch_inbox names GraphWorkflow and CrewTaskWorkflow, never
    FeatureWorkflow (020 T024, FR-005)."""
    c = _Client()
    asyncio.run(fetch_inbox(c))
    query = c.queries[0]
    assert "WorkflowType='GraphWorkflow'" in query
    assert "WorkflowType='CrewTaskWorkflow'" in query
    assert "FeatureWorkflow" not in query
