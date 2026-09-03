"""RunState is RunSummary's live sibling: same field names where they
overlap, so the fleet view and the retro report cannot develop two
vocabularies for one concept (spec 4)."""

from datetime import UTC, datetime

from sdlc.core.models import (
    GateDecision,
    GateOutcome,
    RoleUsage,
    RunState,
    RunSummary,
)

AT = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


def test_run_state_defaults_to_an_unpriced_run():
    s = RunState(run_id="feature-x", title="X", mode="greenfield", status="running", started_at=AT)
    assert s.cost_usd_total is None
    assert s.budget_usd is None
    assert s.decisions == []
    assert s.roles == []
    assert s.current_stage is None


def test_run_state_carries_decisions_and_roles():
    d = GateDecision(gate="architecture", round=1, outcome=GateOutcome.APPROVE, decided_by="human")
    u = RoleUsage(role="architect", model="m", calls=1, cost_usd=0.5)
    s = RunState(
        run_id="r",
        title="T",
        mode="brownfield",
        status="running",
        started_at=AT,
        decisions=[d],
        roles=[u],
        cost_usd_total=0.5,
        budget_usd=40.0,
    )
    assert s.decisions[0].gate == "architecture"
    assert s.roles[0].role == "architect"


def test_run_state_mirrors_run_summary_field_names_where_they_overlap():
    """A rename on either side must break this test, not the dashboard."""
    shared = {
        "run_id",
        "mode",
        "started_at",
        "cost_usd_total",
        "budget_usd",
        "budget_crossings",
        "roles",
        "title",
        "repo_url",
    }
    assert shared <= set(RunState.model_fields)
    assert shared <= set(RunSummary.model_fields)


def test_run_summary_carries_title_and_repo_url_for_closed_runs():
    """D7: a closed run renders from run_summary(); without these it would
    render as a bare workflow id."""
    s = RunSummary(
        run_id="feature-add-sso",
        mode="brownfield",
        outcome="deployed:ok",
        terminal_stage="retro",
        started_at=AT,
        ended_at=AT,
        duration_s=1.0,
        title="Add SSO",
        repo_url="git@example:acme/portal",
    )
    assert s.title == "Add SSO"
    assert s.repo_url == "git@example:acme/portal"


def test_run_summary_title_defaults_empty_so_existing_callers_are_unaffected():
    s = RunSummary(
        run_id="r",
        mode="greenfield",
        outcome="done",
        terminal_stage="retro",
        started_at=AT,
        ended_at=AT,
        duration_s=1.0,
    )
    assert s.title == ""
    assert s.repo_url is None
