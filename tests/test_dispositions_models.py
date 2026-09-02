# tests/test_dispositions_models.py
"""FR-304 (E-50): FindingDisposition is an audited decision, and `kind` is
an explicit discriminator, not a key-prefix sniff (GD7)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sdlc.dispositions.models import Disposition, FindingDisposition


def _fd(**kw) -> FindingDisposition:
    base = dict(
        kind="vulnerability",
        key="SS1:hardcoded-secret:src/a.py:",
        disposition=Disposition.ACCEPTED_RISK,
        approved_by="maks",
        reason="reviewed, tolerated for this release",
        decided_at=datetime.now(UTC),
    )
    base.update(kw)
    return FindingDisposition(**base)


def test_round_trips_a_vulnerability_disposition():
    d = _fd()
    assert d.kind == "vulnerability"
    assert d.disposition is Disposition.ACCEPTED_RISK


def test_a_testability_disposition_uses_the_testability_identity_shape():
    d = _fd(kind="testability", key="QS3:static-clock-access:src/a.py:")
    assert d.kind == "testability"


def test_an_unattributed_disposition_is_refused():
    with pytest.raises(ValidationError, match="approved_by"):
        _fd(approved_by="")


def test_a_disposition_with_no_reason_is_refused():
    with pytest.raises(ValidationError, match="reason"):
        _fd(reason="   ")


def test_a_disposition_with_no_key_is_refused():
    with pytest.raises(ValidationError, match="key"):
        _fd(key="")


def test_kind_is_restricted_to_the_two_finding_families():
    with pytest.raises(ValidationError):
        _fd(kind="capability")


def test_disposition_has_exactly_the_three_fr917_values():
    assert {d.value for d in Disposition} == {
        "false_positive",
        "mitigated_elsewhere",
        "accepted_risk",
    }
