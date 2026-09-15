"""Every scenario has a committed history + golden, captured from FeatureWorkflow."""

from __future__ import annotations

import pytest

from tests.replay.harness import load_golden, load_history
from tests.replay.scenarios import SCENARIOS

EXPECTED_CLOSES = {
    "greenfield_happy": "deployed:",
    "brownfield_happy": "deployed:",
    "intake_reject": "rejected:intake",
    "context_reject": "rejected:context",
    "arch_revise_final": "deployed:",
    "arch_timeout_reject": "rejected:architecture",
    "plan_revise_approve": "deployed:",
    "waves": "deployed:",
    "seeded": "deployed:",
    "budget_clarify_reject": "rejected:budget",
    "budget_arch_reject": "rejected:architecture",
    "research_greenfield": "deployed:",
    "delta_failed": "FAILED:",
    "cancel_during_code": "CANCELED",
    "max_gate_rounds_1": "deployed:",
    # history fetched before terminate: unfinished on purpose
    "partial_awaiting_architecture": "OPEN",
}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_fixture_is_present_and_from_feature_workflow(scenario):
    golden = load_golden(scenario.name)
    assert golden["workflow"] == "FeatureWorkflow"
    assert len(golden["source_commit"]) == 40
    assert golden["close"].startswith(EXPECTED_CLOSES[scenario.name]), golden["close"]
    assert load_history(scenario.name).events


def test_every_scenario_has_an_expected_close():
    assert sorted(EXPECTED_CLOSES) == sorted(s.name for s in SCENARIOS)
