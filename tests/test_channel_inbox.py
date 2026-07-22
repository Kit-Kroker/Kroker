from __future__ import annotations

from sdlc.channels.inbox import Inbox, InboxError, RunInbox, render_inbox
from sdlc.pending import ClarifyPending, MergeGatePending, StageGatePending

ARCH = StageGatePending(key="architecture#1", gate="architecture", round=1,
                        spec_summary="s")
MERGE = MergeGatePending(key="merge#2", gate="merge", round=2)
Q1 = ClarifyPending(key="Q1", question="Use OIDC or SAML?",
                    why_it_matters="auth")


def test_render_inbox_reports_no_open_runs():
    assert render_inbox(Inbox(total_open_runs=0)) == "no open runs"


def test_render_inbox_reports_nothing_pending_plural():
    assert render_inbox(Inbox(total_open_runs=3)) == \
        "nothing pending across 3 open runs"


def test_render_inbox_reports_nothing_pending_singular():
    assert render_inbox(Inbox(total_open_runs=1)) == \
        "nothing pending across 1 open run"


def test_render_inbox_lists_runs_grouped_with_pending_items():
    inbox = Inbox(total_open_runs=2, runs=[
        RunInbox(run_id="feature-add-sso", pending=[ARCH]),
        RunInbox(run_id="feature-fix-bug", pending=[Q1, MERGE]),
    ])
    text = render_inbox(inbox)
    assert text == (
        "feature-add-sso:\n"
        "  architecture (round 1)\n"
        "feature-fix-bug:\n"
        "  Q1: Use OIDC or SAML?\n"
        "  merge (round 2)"
    )


def test_render_inbox_appends_error_block_after_a_blank_line():
    inbox = Inbox(total_open_runs=2, runs=[
        RunInbox(run_id="feature-add-sso", pending=[ARCH]),
    ], errors=[
        InboxError(run_id="feature-stale-run", error="workflow not found"),
    ])
    text = render_inbox(inbox)
    assert text == (
        "feature-add-sso:\n"
        "  architecture (round 1)\n"
        "\n"
        "1 run could not be queried:\n"
        "  feature-stale-run: workflow not found"
    )


def test_render_inbox_pluralizes_the_error_count():
    inbox = Inbox(total_open_runs=2, errors=[
        InboxError(run_id="a", error="e1"),
        InboxError(run_id="b", error="e2"),
    ])
    text = render_inbox(inbox)
    assert text == (
        "2 runs could not be queried:\n"
        "  a: e1\n"
        "  b: e2"
    )


def test_render_inbox_shows_only_errors_when_nothing_confirmed_pending():
    """No 'nothing pending' line when some runs are in an unknown state --
    we genuinely don't know whether the errored runs had pending items."""
    inbox = Inbox(total_open_runs=1, errors=[
        InboxError(run_id="a", error="e1"),
    ])
    assert "nothing pending" not in render_inbox(inbox)


def test_render_inbox_output_is_ascii():
    inbox = Inbox(total_open_runs=1, runs=[
        RunInbox(run_id="r", pending=[Q1]),
    ])
    render_inbox(inbox).encode("ascii")
