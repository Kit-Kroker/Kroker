"""parse_run_budget and budget_notice (011 T011, FR-007/FR-009). Pure
functions: no Temporal, no registry, fast tier. The module under test does
not exist yet -- these tests are its contract (data-model §2.2)."""

import pytest

from sdlc.core.models import PipelineConfig
from sdlc.run_budget import BUDGET_SCOPE_NOTE, BUDGET_ZERO_HINT, budget_notice, parse_run_budget

# --- 011 T011 (RED) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (5, 5.0),
        (5.5, 5.5),
        ("5", 5.0),
        (" 5 ", 5.0),  # stripped, not rejected
    ],
)
def test_parse_run_budget_accepts(raw, expected):
    assert parse_run_budget(raw) == expected


@pytest.mark.parametrize("raw", [0, "0", 0.0])
def test_parse_run_budget_zero_is_rejected_with_the_omit_hint(raw):
    with pytest.raises(ValueError) as excinfo:
        parse_run_budget(raw)
    assert str(excinfo.value) == BUDGET_ZERO_HINT


@pytest.mark.parametrize("raw", [-1, "abc", True, "nan", "inf", None, []])
def test_parse_run_budget_rejects(raw):
    # True is the bool trap: bool subclasses int, and int 1 would parse —
    # a flag must never smuggle a budget in as truthiness.
    with pytest.raises(ValueError) as excinfo:
        parse_run_budget(raw)
    assert str(excinfo.value) == "budget must be a number greater than 0"


def test_budget_notice_is_none_without_a_budget():
    assert budget_notice(PipelineConfig()) is None


def test_budget_notice_announces_the_budget_and_its_scope():
    cfg = PipelineConfig()
    cfg.run_budget_usd = 5
    notice = budget_notice(cfg)
    assert notice is not None
    assert notice.startswith("Budget $5.00 ")
    assert notice.count(BUDGET_SCOPE_NOTE) == 1


# --- 011 T011 (RED): the price probe names only what is missing --------------
# budget_notice probes the run's PLANNING roles (resolved_roles(cfg)) through
# compute_price; a planning role whose model has no known price appends
# ' No price found for: <sorted, comma-joined roles>.' The probe never says
# 'all priced', and harness roles (dev/test/devops) are never planning roles,
# so their models are never listed.

from sdlc.core.models import RoleConfig  # noqa: E402


def _budgeted_cfg() -> PipelineConfig:
    cfg = PipelineConfig()
    cfg.run_budget_usd = 5
    return cfg


def test_budget_notice_names_a_planning_role_with_an_unknown_model():
    cfg = _budgeted_cfg()
    cfg.roles["research"] = RoleConfig(model="totally:unknown-model")
    notice = budget_notice(cfg)
    assert notice is not None
    assert notice.endswith("No price found for: research.")


def test_budget_notice_lists_unpriced_roles_sorted():
    cfg = _budgeted_cfg()
    cfg.roles["research"] = RoleConfig(model="totally:unknown-model")
    cfg.roles["adversary"] = RoleConfig(model="totally:unknown-model")
    notice = budget_notice(cfg)
    assert notice is not None
    assert notice.endswith("No price found for: adversary, research.")


def test_budget_notice_with_registry_defaults_names_nothing_missing():
    """Best-effort pin of today's registry: every default planning model is
    priced. If this fails, some registry planning model is genuinely
    unpriced -- report it, do not weaken the probe."""
    notice = budget_notice(_budgeted_cfg())
    assert notice is not None
    assert "No price found" not in notice


def test_budget_notice_never_lists_a_harness_role():
    cfg = _budgeted_cfg()
    cfg.roles["dev"] = RoleConfig(model="totally:unknown-model")
    notice = budget_notice(cfg)
    assert notice is not None
    assert "No price found" not in notice
