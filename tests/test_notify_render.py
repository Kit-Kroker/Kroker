"""E-9 Task 3: notification text. Reuses E-6's default_render -- this module
adds the envelope (why you are being told, when it expires, how to reply)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sdlc.gate import CheckClass, CheckResult
from sdlc.notify.contract import NotifyReason
from sdlc.notify.render import render_notification
from sdlc.pending import ClarifyPending, MergeGatePending, gate_pending

T0 = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def _merge_pending() -> MergeGatePending:
    return MergeGatePending(
        key="merge#1",
        gate="merge",
        round=1,
        verdict="ready to merge",
        checks=[
            CheckResult(
                name="security_no_critical",
                passed=True,
                classification=CheckClass.ABSOLUTE,
                detail="",
            ),
            CheckResult(
                name="coverage", passed=False, classification=CheckClass.ADVISORY, detail="61%"
            ),
        ],
    )


def test_merge_notification_carries_check_table_and_cli_commands():
    text = render_notification(
        _merge_pending(),
        NotifyReason.OPENED,
        run_id="abc123",
        opened_at=T0,
        now=T0,
        deadline=T0 + timedelta(hours=48),
        base_url=None,
    )
    assert "run abc123" in text
    assert "security_no_critical" in text
    assert "coverage" in text and "61%" in text
    assert "sdlc approve abc123 --gate merge" in text
    assert "sdlc reject abc123 --gate merge" in text


def test_clarify_notification_offers_the_answer_verb_not_gate_verbs():
    pending = ClarifyPending(
        key="q1",
        question="Which datastore?",
        why_it_matters="Drives the schema.",
        suggested_answer="postgres",
    )
    text = render_notification(
        pending,
        NotifyReason.OPENED,
        run_id="abc123",
        opened_at=T0,
        now=T0,
        deadline=None,
        base_url=None,
    )
    assert "sdlc answer abc123" in text
    assert "--gate" not in text
    assert "postgres" in text


def test_reason_is_stated_and_expiry_is_relative():
    text = render_notification(
        _merge_pending(),
        NotifyReason.REMIND,
        run_id="abc123",
        opened_at=T0,
        now=T0 + timedelta(hours=24),
        deadline=T0 + timedelta(hours=48),
        base_url=None,
    )
    assert "reminder" in text.lower()
    assert "opened 24h ago" in text
    assert "expires in 24h" in text


def test_hold_gate_says_it_will_not_expire():
    text = render_notification(
        _merge_pending(),
        NotifyReason.OPENED,
        run_id="abc123",
        opened_at=T0,
        now=T0,
        deadline=None,
        base_url=None,
    )
    assert "does not expire" in text
    assert "expires in" not in text


def test_expire_reason_reads_as_terminal():
    text = render_notification(
        _merge_pending(),
        NotifyReason.EXPIRE,
        run_id="abc123",
        opened_at=T0,
        now=T0 + timedelta(hours=48),
        deadline=T0 + timedelta(hours=48),
        base_url=None,
    )
    assert "expired" in text.lower()


def test_base_url_adds_a_link_without_removing_the_commands():
    text = render_notification(
        _merge_pending(),
        NotifyReason.OPENED,
        run_id="abc123",
        opened_at=T0,
        now=T0,
        deadline=None,
        base_url="https://sdlc.example.com",
    )
    assert "https://sdlc.example.com/runs/abc123" in text
    assert "sdlc approve abc123 --gate merge" in text


def test_text_is_ascii_only():
    """The Windows console cannot print non-ASCII (transport.py:11)."""
    text = render_notification(
        _merge_pending(),
        NotifyReason.ESCALATE,
        run_id="abc123",
        opened_at=T0,
        now=T0 + timedelta(hours=38),
        deadline=T0 + timedelta(hours=48),
        base_url=None,
    )
    text.encode("ascii")  # raises UnicodeEncodeError on failure


def gate_pending_for(gate: str):
    return gate_pending(gate, 1, None)


def links_for(
    gate: str, *, base_url="http://localhost:8500/", project="acme", reason=NotifyReason.OPENED
) -> str:
    return render_notification(
        pending=gate_pending_for(gate),
        reason=reason,
        run_id="run-1",
        opened_at=T0,
        now=T0,
        deadline=None,
        base_url=base_url,
        project=project,
    )


def test_merge_gate_links_all_three_artifact_renders():
    text = links_for("merge")
    for key in ("requirements", "architecture", "plan"):
        assert f"/projects/acme/artifacts/{key}/current/markdown" in text


def test_architecture_gate_links_requirements_but_not_its_own_artifact():
    # requirements is published at feature.py:560, before this gate opens;
    # architecture is published only after it is decided (feature.py:585),
    # so linking it here would 404.
    text = links_for("architecture")
    assert "/artifacts/requirements/current/markdown" in text
    assert "/artifacts/architecture/current/markdown" not in text
    assert "/artifacts/plan/current/markdown" not in text


def test_plan_gate_links_the_two_earlier_artifacts_only():
    text = links_for("plan")
    assert "/artifacts/requirements/current/markdown" in text
    assert "/artifacts/architecture/current/markdown" in text
    assert "/artifacts/plan/current/markdown" not in text


def test_clarify_gate_links_nothing_because_nothing_is_published():
    assert "/markdown" not in links_for("clarify")


def test_task_escalation_gate_links_all_three():
    text = links_for("task:T01")
    for key in ("requirements", "architecture", "plan"):
        assert f"/artifacts/{key}/current/markdown" in text


def test_no_base_url_omits_the_links_without_erroring():
    text = links_for("merge", base_url=None)
    assert "/markdown" not in text
    assert "sdlc approve" in text  # the rest of the notification is intact


def test_no_project_omits_the_links_without_erroring():
    text = links_for("merge", project=None)
    assert "/markdown" not in text
    assert "sdlc approve" in text


def test_expired_notifications_carry_no_links():
    # EXPIRE already suppresses the command block; links follow it.
    assert "/markdown" not in links_for("merge", reason=NotifyReason.EXPIRE)
