# tests/test_inbox_query.py
"""E-88 step 2 §E. The visibility filter has TWO callers that want different
answers: the inbox lists what a human owes a decision on, and a crew's gate
is exactly that; the fleet lists RUNS, and a crew child is part of a run
rather than one. Widening a shared constant would have silently changed
both."""
from __future__ import annotations

import asyncio

from sdlc.channels.inbox import _open_runs_query, list_open_run_ids


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


def test_the_query_defaults_to_feature_workflows_only():
    assert _open_runs_query("FeatureWorkflow") == (
        "(WorkflowType='FeatureWorkflow') AND ExecutionStatus='Running'")


def test_the_query_ors_every_named_type():
    q = _open_runs_query("FeatureWorkflow", "CrewTaskWorkflow")
    assert q == ("(WorkflowType='FeatureWorkflow' OR "
                 "WorkflowType='CrewTaskWorkflow') AND "
                 "ExecutionStatus='Running'")


def test_list_open_run_ids_stays_narrow_by_default():
    """dashboard/fleet.py calls this with no types and must keep the view it
    has: adding the parameter changes nothing for existing callers."""
    c = _Client()
    asyncio.run(list_open_run_ids(c))
    assert "CrewTaskWorkflow" not in c.queries[0]


def test_the_inbox_can_ask_for_crew_children_too():
    c = _Client()
    asyncio.run(list_open_run_ids(c, "FeatureWorkflow", "CrewTaskWorkflow"))
    assert "CrewTaskWorkflow" in c.queries[0]
