"""run_state() projects state the run already holds (spec D1). No new
bookkeeping: every field is read from existing workflow state."""

from datetime import UTC, datetime

import pytest

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
from sdlc.workflows.graph import GraphWorkflow

AT = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


@pytest.fixture(params=[FeatureWorkflow, GraphWorkflow], ids=["feature", "graph"])
def wf_cls(request):
    return request.param


def _wf(cls, **overrides):
    """A workflow instance with state set directly. __init__ touches
    no Temporal API, so this is safe outside a workflow environment."""
    wf = cls()
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


def _usage_event(seq, role, model, in_t, out_t, usd=None):
    """A MODEL_USAGE trace event (011 T003): token keys are string ints;
    cost_usd is present only when the call was priced."""
    data = {
        "role": role,
        "model": model,
        "calls": "1",
        "input_tokens": str(in_t),
        "output_tokens": str(out_t),
        "cache_read_tokens": "0",
        "cache_write_tokens": "0",
    }
    if usd is not None:
        data["cost_usd"] = str(usd)
    return RunEvent(seq=seq, at=AT, kind=RunEventKind.MODEL_USAGE, data=data)


def test_run_state_is_none_before_the_brief_is_stashed(wf_cls):
    wf = wf_cls()
    assert wf.run_state() is None


def test_run_state_projects_title_repo_and_mode_from_the_brief(wf_cls):
    s = _wf(wf_cls).run_state()
    assert s.title == "Add SSO"
    assert s.repo_url == "git@example:acme/portal"
    assert s.mode == "brownfield"


def test_run_state_reports_status_verbatim(wf_cls):
    wf = _wf(wf_cls)
    wf._status = "awaiting:architecture"
    assert wf.run_state().status == "awaiting:architecture"


def test_current_stage_is_the_last_stage_started(wf_cls):
    wf = _wf(
        wf_cls,
        _trace=[
            RunEvent(seq=1, at=AT, kind=RunEventKind.STAGE_STARTED, stage="clarify"),
            RunEvent(seq=2, at=AT, kind=RunEventKind.STAGE_ENDED, stage="clarify"),
            RunEvent(seq=3, at=AT, kind=RunEventKind.STAGE_STARTED, stage="architecture"),
        ],
    )
    assert wf.run_state().current_stage == "architecture"


def test_current_stage_is_none_when_no_stage_has_started(wf_cls):
    assert _wf(wf_cls).run_state().current_stage is None


def test_decisions_are_returned_in_insertion_order(wf_cls):
    a = GateDecision(gate="architecture", round=1, outcome=GateOutcome.APPROVE, decided_by="human")
    m = GateDecision(gate="merge", round=1, outcome=GateOutcome.APPROVE, decided_by="policy")
    wf = _wf(wf_cls)
    wf._gate_decisions = {"architecture#1": a, "merge#1": m}
    assert [d.gate for d in wf.run_state().decisions] == ["architecture", "merge"]


def test_cost_total_sums_priced_roles(wf_cls):
    wf = _wf(
        wf_cls,
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=1.5),
            "dev": RoleUsage(role="dev", model="m", cost_usd=2.25),
        },
        # 011 T003 intended edit: state reads roles/totals from the trace
        # rollup, so the trace must carry what the bag carries.
        _trace=[
            _usage_event(0, "architect", "m", 100, 10, usd=1.5),
            _usage_event(1, "dev", "m", 1000, 200, usd=2.25),
        ],
    )
    assert wf.run_state().cost_usd_total == 3.75


def test_cost_total_is_none_when_no_role_was_ever_priced(wf_cls):
    """A pricing miss must never read as a free run (RoleUsage.cost_usd)."""
    wf = _wf(
        wf_cls,
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=None),
        },
        _trace=[_usage_event(0, "architect", "m", 100, 10)],  # no cost_usd key
    )
    assert wf.run_state().cost_usd_total is None


def test_cost_total_sums_what_was_priced_when_some_roles_are_unpriced(wf_cls):
    wf = _wf(
        wf_cls,
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=1.5),
            "dev": RoleUsage(role="dev", model="m", cost_usd=None),
        },
        _trace=[
            _usage_event(0, "architect", "m", 100, 10, usd=1.5),
            _usage_event(1, "dev", "m", 1000, 200),  # unpriced
        ],
    )
    assert wf.run_state().cost_usd_total == 1.5


# --- 011 T003 (RED): roles and totals come from the trace rollup (FR-001a) ---
# The code stage writes MODEL_USAGE into the trace, not the _role_usage bag;
# run_state() must read the rollup so every recorded role is visible.


def test_trace_usage_lists_a_role_the_bag_never_saw(wf_cls):
    """FR-001a: a MODEL_USAGE event for dev must surface in roles even
    though the bag has no dev entry."""
    wf = _wf(
        wf_cls,
        _trace=[_usage_event(0, "dev", "m", 1000, 200)],  # unpriced call
        _role_usage={},
    )
    roles = {u.role: u for u in wf.run_state().roles}
    assert "dev" in roles
    assert roles["dev"].input_tokens == 1000
    assert roles["dev"].output_tokens == 200


def test_trace_only_totals_sum_the_priced_rows(wf_cls):
    """cost_usd_total is the sum of the rollup rows that carry a price; the
    unpriced role contributes tokens, never dollars."""
    wf = _wf(
        wf_cls,
        _trace=[
            _usage_event(0, "architect", "m", 100, 10, usd=1.5),
            _usage_event(1, "planner", "m", 50, 5, usd=0.25),
            _usage_event(2, "dev", "m", 1000, 200),  # unpriced
        ],
        _role_usage={},
    )
    assert wf.run_state().cost_usd_total == 1.75


def test_every_bag_role_still_appears_with_equal_tokens_and_dollars(wf_cls):
    """PIN: the trace rollup must reproduce what the bag recorded, role for
    role — tokens and dollars equal. Passes before the cutover (roles come
    from the bag) and after (roles come from the matching trace); a red PIN
    is a stop-guard."""
    wf = _wf(
        wf_cls,
        _trace=[
            _usage_event(0, "architect", "m", 100, 10, usd=0.5),
            _usage_event(1, "architect", "m", 50, 5, usd=0.1),
            _usage_event(2, "dev", "m", 1000, 200),  # unpriced
        ],
        _role_usage={
            "architect": RoleUsage(
                role="architect",
                model="m",
                calls=2,
                input_tokens=150,
                output_tokens=15,
                cost_usd=0.6,
            ),
            "dev": RoleUsage(
                role="dev", model="m", calls=1, input_tokens=1000, output_tokens=200, cost_usd=None
            ),
        },
    )
    roles = {u.role: u for u in wf.run_state().roles}
    assert roles["architect"].input_tokens == 150
    assert roles["architect"].output_tokens == 15
    assert roles["architect"].cost_usd == 0.6
    assert roles["dev"].input_tokens == 1000
    assert roles["dev"].output_tokens == 200
    assert roles["dev"].cost_usd is None


def test_budget_is_none_when_the_run_budget_is_off(wf_cls):
    cfg = PipelineConfig()
    cfg.run_budget_usd = 0.0
    assert _wf(wf_cls, cfg=cfg).run_state().budget_usd is None


def test_budget_is_reported_when_configured(wf_cls):
    cfg = PipelineConfig()
    cfg.run_budget_usd = 40.0
    assert _wf(wf_cls, cfg=cfg).run_state().budget_usd == 40.0


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


# --- 011 T003 (RED): budget threshold and counted on the live state -----------
# RunState gains budget_threshold_usd (the gate's current limit — it rises by
# one budget per approve) and budget_counted_usd (the priced sum over
# _role_usage, the bag the gate actually sums at role_host.py:280:
# sum(u.cost_usd or 0.0 for u in _role_usage.values())). With no budget both
# are None.


def test_budget_threshold_and_counted_are_reported_when_a_budget_is_on(wf_cls):
    cfg = PipelineConfig()
    cfg.run_budget_usd = 40.0
    wf = _wf(
        wf_cls,
        cfg=cfg,
        _budget_threshold=40.0,
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=31.0),
        },
        _trace=[_usage_event(0, "architect", "m", 100, 10, usd=31.0)],
    )
    s = wf.run_state()
    assert s.budget_threshold_usd == 40.0
    assert s.budget_counted_usd == 31.0


def test_budget_threshold_reports_the_current_limit_after_raises(wf_cls):
    """One approve raises the limit by one budget; the state must report the
    CURRENT limit (percent is counted over it), not the configured one."""
    cfg = PipelineConfig()
    cfg.run_budget_usd = 40.0
    wf = _wf(
        wf_cls,
        cfg=cfg,
        _budget_threshold=80.0,
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=31.0),
        },
        _trace=[_usage_event(0, "architect", "m", 100, 10, usd=31.0)],
    )
    assert wf.run_state().budget_threshold_usd == 80.0


def test_budget_threshold_and_counted_are_none_without_a_budget(wf_cls):
    cfg = PipelineConfig()
    cfg.run_budget_usd = 0.0
    s = _wf(wf_cls, cfg=cfg).run_state()  # _budget_threshold left at 0.0 default
    assert s.budget_threshold_usd is None
    assert s.budget_counted_usd is None


def test_budget_counted_is_zero_not_none_when_no_role_was_priced(wf_cls):
    """Edge: with a budget on but only unpriced roles, the gate compares a
    real 0.0 (its sum is cost_usd or 0.0), never None — 0 of 40 spent, not
    an unmeasured run."""
    cfg = PipelineConfig()
    cfg.run_budget_usd = 40.0
    wf = _wf(
        wf_cls,
        cfg=cfg,
        _budget_threshold=40.0,
        _role_usage={
            "architect": RoleUsage(role="architect", model="m", cost_usd=None),
        },
        _trace=[_usage_event(0, "architect", "m", 100, 10)],  # no cost_usd key
    )
    s = wf.run_state()
    assert s.budget_counted_usd == 0.0
    assert s.budget_threshold_usd == 40.0
