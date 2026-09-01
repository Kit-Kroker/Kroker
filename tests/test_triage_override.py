"""FR-903 (E-42 D1): an audited human decision to proceed despite a verdict
that is not READY, recorded ON the artifact so E-45 need not re-ask."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from sdlc.measurement import Measurement
from sdlc.triage.models import (
    Readiness,
    ReadinessOverride,
    RepoTriage,
    Verdict,
)


def _not_ready() -> Readiness:
    return Readiness(
        buildable=Measurement.measured(0.0),
        runnable=Measurement.measured(0.0),
        tests_present=Measurement.measured(1.0),
        structure_discernible=Measurement.measured(1.0),
        verdict=Verdict.NOT_READY,
    )


def test_repo_triage_defaults_to_no_override():
    t = RepoTriage(repo_dir="/r", commit_sha="abc", readiness=_not_ready())
    assert t.override is None


def test_override_records_the_class_of_approver_verbatim():
    """'policy' and 'timeout' must stay legible as non-human (spec section 7)."""
    o = ReadinessOverride(
        approved_by="policy",
        reason="gate off",
        decided_at=dt.datetime(2026, 8, 8, tzinfo=dt.UTC),
        gate_round=1,
    )
    t = RepoTriage(repo_dir="/r", commit_sha="abc", readiness=_not_ready(), override=o)
    assert t.override.approved_by == "policy"
    assert t.override.reviewer is None
    assert t.override.gate_round == 1


def test_approved_by_rejects_a_principal():
    """decided_by is a class of decider, not a name. An identity that looked
    like an approval class would make 'a human approved' unfalsifiable."""
    with pytest.raises(ValidationError):
        ReadinessOverride(
            approved_by="alice",
            reason="r",
            decided_at=dt.datetime(2026, 8, 8, tzinfo=dt.UTC),
            gate_round=1,
        )


def test_reviewer_carries_the_self_asserted_identity():
    """FR-1004's gap, mirrored rather than hidden."""
    o = ReadinessOverride(
        approved_by="human",
        reviewer="alice",
        reason="ok",
        decided_at=dt.datetime(2026, 8, 8, tzinfo=dt.UTC),
        gate_round=1,
    )
    assert o.approved_by == "human"
    assert o.reviewer == "alice"


def test_triage_models_stays_pure():
    """The module must not import models.py, activities.py or temporalio --
    a dependency there would appear as a reviewable import."""
    import pathlib

    src = pathlib.Path("src/sdlc/triage/models.py").read_text(encoding="utf-8")
    assert "import temporalio" not in src
    assert "from temporalio" not in src
    assert "from ..models" not in src
    assert "from ..activities" not in src
