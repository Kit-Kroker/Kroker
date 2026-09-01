from __future__ import annotations

from sdlc.channels.inbox import Inbox, InboxError, RunInbox, render_inbox
from sdlc.pending import ClarifyPending, MergeGatePending, StageGatePending

ARCH = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="s")
MERGE = MergeGatePending(key="merge#2", gate="merge", round=2)
Q1 = ClarifyPending(key="Q1", question="Use OIDC or SAML?", why_it_matters="auth")


def test_render_inbox_reports_no_open_runs():
    assert render_inbox(Inbox(total_open_runs=0)) == "no open runs"


def test_render_inbox_reports_nothing_pending_plural():
    assert render_inbox(Inbox(total_open_runs=3)) == "nothing pending across 3 open runs"


def test_render_inbox_reports_nothing_pending_singular():
    assert render_inbox(Inbox(total_open_runs=1)) == "nothing pending across 1 open run"


def test_render_inbox_lists_runs_grouped_with_pending_items():
    inbox = Inbox(
        total_open_runs=2,
        runs=[
            RunInbox(run_id="feature-add-sso", pending=[ARCH]),
            RunInbox(run_id="feature-fix-bug", pending=[Q1, MERGE]),
        ],
    )
    text = render_inbox(inbox)
    assert text == (
        "feature-add-sso:\n"
        "  architecture (round 1)\n"
        "feature-fix-bug:\n"
        "  Q1: Use OIDC or SAML?\n"
        "  merge (round 2)"
    )


def test_render_inbox_appends_error_block_after_a_blank_line():
    inbox = Inbox(
        total_open_runs=2,
        runs=[
            RunInbox(run_id="feature-add-sso", pending=[ARCH]),
        ],
        errors=[
            InboxError(run_id="feature-stale-run", error="workflow not found"),
        ],
    )
    text = render_inbox(inbox)
    assert text == (
        "feature-add-sso:\n"
        "  architecture (round 1)\n"
        "\n"
        "1 run could not be queried:\n"
        "  feature-stale-run: workflow not found"
    )


def test_render_inbox_pluralizes_the_error_count():
    inbox = Inbox(
        total_open_runs=2,
        errors=[
            InboxError(run_id="a", error="e1"),
            InboxError(run_id="b", error="e2"),
        ],
    )
    text = render_inbox(inbox)
    assert text == ("2 runs could not be queried:\n  a: e1\n  b: e2")


def test_render_inbox_shows_only_errors_when_nothing_confirmed_pending():
    """No 'nothing pending' line when some runs are in an unknown state --
    we genuinely don't know whether the errored runs had pending items."""
    inbox = Inbox(
        total_open_runs=1,
        errors=[
            InboxError(run_id="a", error="e1"),
        ],
    )
    assert "nothing pending" not in render_inbox(inbox)


def test_render_inbox_output_is_ascii():
    inbox = Inbox(
        total_open_runs=1,
        runs=[
            RunInbox(run_id="r", pending=[Q1]),
        ],
    )
    render_inbox(inbox).encode("ascii")


from types import SimpleNamespace

import pytest

from sdlc.channels.inbox import fetch_inbox, list_open_run_ids


class _StubHandle:
    """Returns one scripted pending_decisions() result, or raises."""

    def __init__(self, response=None, error=None):
        self._response = response if response is not None else []
        self._error = error

    async def query(self, name):
        assert name == "pending_decisions"
        if self._error is not None:
            raise self._error
        return self._response


class _StubClient:
    def __init__(self, handles: dict[str, _StubHandle]):
        self._handles = handles

    async def list_workflows(self, query):
        assert "FeatureWorkflow" in query
        assert "Running" in query
        for run_id in self._handles:
            yield SimpleNamespace(id=run_id)

    def get_workflow_handle(self, run_id):
        return self._handles[run_id]


def _raw(*items):
    return [i.model_dump(mode="json") for i in items]


@pytest.mark.asyncio
async def test_list_open_run_ids_returns_ids_from_the_visibility_query():
    client = _StubClient({"run-a": _StubHandle(), "run-b": _StubHandle()})
    assert await list_open_run_ids(client) == ["run-a", "run-b"]


@pytest.mark.asyncio
async def test_fetch_inbox_aggregates_pending_across_runs_and_drops_empty_ones():
    client = _StubClient(
        {
            "run-a": _StubHandle(response=_raw(ARCH)),
            "run-b": _StubHandle(response=[]),  # nothing pending -> dropped
            "run-c": _StubHandle(response=_raw(Q1, MERGE)),
        }
    )
    inbox = await fetch_inbox(client)
    assert inbox.total_open_runs == 3
    assert {r.run_id for r in inbox.runs} == {"run-a", "run-c"}
    assert inbox.errors == []
    by_id = {r.run_id: r.pending for r in inbox.runs}
    assert [d.key for d in by_id["run-c"]] == ["Q1", "merge#2"]


@pytest.mark.asyncio
async def test_fetch_inbox_isolates_a_failing_run_from_the_rest():
    client = _StubClient(
        {
            "run-a": _StubHandle(response=_raw(ARCH)),
            "run-b": _StubHandle(error=RuntimeError("workflow not found")),
        }
    )
    inbox = await fetch_inbox(client)
    assert inbox.total_open_runs == 2
    assert [r.run_id for r in inbox.runs] == ["run-a"]
    assert inbox.errors[0].run_id == "run-b"
    assert "workflow not found" in inbox.errors[0].error
