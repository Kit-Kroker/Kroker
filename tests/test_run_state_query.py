"""run_state() projects state the run already holds (spec D1). No new
bookkeeping: every field is read from existing workflow state."""

from datetime import UTC, datetime

from sdlc.core.models import (
    GateDecision,
    GateOutcome,
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
    RoleUsage,
)
from sdlc.observability.trace import RunEvent, RunEventKind
from sdlc.workflows.feature import FeatureWorkflow

AT = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


def _wf(**overrides):
    """A FeatureWorkflow instance with state set directly. __init__ touches
    no Temporal API, so this is safe outside a workflow environment."""
    wf = FeatureWorkflow()
    wf._idea = overrides.pop(
        "idea",
        IdeaBrief(
            title="Add SSO",
            description="d",
            mode=ProjectMode.BROWNFIELD,
            repo_url="git@example:acme/portal",
        ),
    )
    wf._cfg = overrides.pop("cfg", PipelineConfig())
    wf._started_at = overrides.pop("started_at", AT)
    for k, v in overrides.items():
        setattr(wf, k, v)
    return wf


def test_run_state_is_none_before_the_brief_is_stashed():
    wf = FeatureWorkflow()
    assert wf.run_state() is None


def test_run_state_projects_title_repo_and_mode_from_the_brief():
    s = _wf().run_state()
    assert s.title == "Add SSO"
    assert s.repo_url == "git@example:acme/portal"
    assert s.mode == "brownfield"


def test_run_state_reports_status_verbatim():
    wf = _wf()
    wf._status = "awaiting:architecture"
    assert wf.run_state().status == "awaiting:architecture"


def test_current_stage_is_the_last_stage_started():
    wf = _wf(
        _trace=[
            RunEvent(seq=1, at=AT, kind=RunEventKind.STAGE_STARTED, stage="clarify"),
            RunEvent(seq=2, at=AT, kind=RunEventKind.STAGE_ENDED, stage="clarify"),
            RunEvent(seq=3, at=AT, kind=RunEventKind.STAGE_STARTED, stage="architecture"),
        ]
    )
    assert wf.run_state().current_stage == "architecture"


def test_current_stage_is_none_when_no_stage_has_started():
    assert _wf().run_state().current_stage is None


def test_decisions_are_returned_in_insertion_order():
    a = GateDecision(gate="architecture", round=1, outcome=GateOutcome.APPROVE, decided_by="human")
    m = GateDecision(gate="merge", round=1, outcome=GateOutcome.APPROVE, decided_by="policy")
    wf = _wf()
    wf._gate_decisions = {"architecture#1": a, "merge#1": m}
    assert [d.gate for d in wf.run_state().decisions] == ["architecture", "merge"]


def test_cost_total_sums_priced_roles():
    wf = _wf(
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=1.5),
            "dev": RoleUsage(role="dev", model="m", cost_usd=2.25),
        }
    )
    assert wf.run_state().cost_usd_total == 3.75


def test_cost_total_is_none_when_no_role_was_ever_priced():
    """A pricing miss must never read as a free run (RoleUsage.cost_usd)."""
    wf = _wf(
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=None),
        }
    )
    assert wf.run_state().cost_usd_total is None


def test_cost_total_sums_what_was_priced_when_some_roles_are_unpriced():
    wf = _wf(
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=1.5),
            "dev": RoleUsage(role="dev", model="m", cost_usd=None),
        }
    )
    assert wf.run_state().cost_usd_total == 1.5


def test_budget_is_none_when_the_run_budget_is_off():
    cfg = PipelineConfig()
    cfg.run_budget_usd = 0.0
    assert _wf(cfg=cfg).run_state().budget_usd is None


def test_budget_is_reported_when_configured():
    cfg = PipelineConfig()
    cfg.run_budget_usd = 40.0
    assert _wf(cfg=cfg).run_state().budget_usd == 40.0


def test_stage_started_emits_canonical_stage_names():
    """STAGE_STARTED must speak the canonical noun vocabulary (heatmap's
    CANONICAL_STAGES) -- STAGE_ENDED, terminal_stage, and the frontend's
    stage strip already do; a gerund here parks every run at intake."""
    import re
    from pathlib import Path

    import sdlc.workflows.feature as feature_mod
    from sdlc.benchmarks.heatmap import CANONICAL_STAGES

    src = Path(feature_mod.__file__).read_text(encoding="utf-8")
    calls = re.findall(r'_stage\("(\w+)"(?:,\s*"(\w+)")?\)', src)
    assert calls, "no _stage call sites found -- helper renamed?"
    for status, trace in calls:
        assert (trace or status) in CANONICAL_STAGES, (
            f"_stage({status!r}, {trace!r}): not a canonical stage name"
        )
