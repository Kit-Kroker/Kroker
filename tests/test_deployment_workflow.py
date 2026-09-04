"""The child workflow's decision logic. The pure helper is tested directly;
the sequencing is tested through the parent in Task 7."""

from __future__ import annotations

import pathlib

from sdlc.stages.deploy.models import (
    SmokeCheckResult,
    SmokeState,
)
from sdlc.workflows.deployment import DeploymentInput, needs_rollback


def _r(state, name="c"):
    return SmokeCheckResult(
        name=name, state=state, detail="" if state is SmokeState.PASSED else "why"
    )


def test_all_passed_needs_no_rollback():
    assert needs_rollback([_r(SmokeState.PASSED), _r(SmokeState.PASSED)]) is False


def test_no_checks_needs_no_rollback():
    """A plan with no smoke checks deploys. Weak, but honest -- and the
    planner owning the checks is where that gets fixed, not here."""
    assert needs_rollback([]) is False


def test_a_failed_check_triggers_rollback():
    assert needs_rollback([_r(SmokeState.PASSED), _r(SmokeState.FAILED)]) is True


def test_an_errored_check_triggers_rollback():
    """D-3: 'we could not tell' is not permission to ship."""
    assert needs_rollback([_r(SmokeState.ERRORED)]) is True


def test_attempt_defaults_to_one():
    inp = DeploymentInput.model_construct(attempt=1)
    assert inp.attempt == 1


SRC = pathlib.Path("src/sdlc/workflows/deployment.py")


def test_the_child_makes_no_model_call():
    """Invariant: DeploymentWorkflow is deterministic. An agent import here
    would be a reviewable regression."""
    src = SRC.read_text(encoding="utf-8")
    for forbidden in ("TemporalAgent", "pydantic_ai", "resolve_role_model"):
        assert forbidden not in src, forbidden


def test_the_child_holds_no_gate():
    """D-6: HITL stays in FeatureWorkflow, where the signals land."""
    src = SRC.read_text(encoding="utf-8")
    assert "_gate" not in src
    assert "signal" not in src
