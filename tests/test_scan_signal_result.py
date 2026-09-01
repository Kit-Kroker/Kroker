"""D2/D3: an inherited row cites findings and copies none, and coverage is
tracked per category because a row cannot be half-measured."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.scan.models import (
    C_CREDENTIAL_STORAGE,
    C_INPUT_VALIDATION,
    CATEGORIES,
    InheritedProducer,
    ScanSignalId,
    ScanSignalResult,
    SignalFamily,
    SignalSource,
)
from sdlc.measurement import CollectionState, Measurement


def _producer() -> InheritedProducer:
    return InheritedProducer(
        producer="triage:secrets", version=2, finding_ids=["secrets:aws_key:.env:abc123"]
    )


def _row(source: SignalSource, **kw) -> ScanSignalResult:
    base = dict(
        signal=ScanSignalId.SS1,
        family=SignalFamily.SECURITY,
        version=1,
        source=source,
        collected=Measurement.measured(1.0),
        categories={k: Measurement.not_collected("plan 3") for k in CATEGORIES[ScanSignalId.SS1]},
    )
    return ScanSignalResult(**(base | kw))


def test_every_signal_declares_its_categories():
    assert set(CATEGORIES) == set(ScanSignalId)
    assert C_CREDENTIAL_STORAGE in CATEGORIES[ScanSignalId.SS1]
    assert C_INPUT_VALIDATION in CATEGORIES[ScanSignalId.SS1]


def test_computed_must_not_carry_a_producer():
    with pytest.raises(ValidationError, match="producer"):
        _row(SignalSource.COMPUTED, producer=_producer())


def test_inherited_and_extended_require_a_producer():
    for source in (SignalSource.INHERITED, SignalSource.EXTENDED):
        with pytest.raises(ValidationError, match="producer"):
            _row(source)


def test_extended_with_a_producer_constructs():
    row = _row(SignalSource.EXTENDED, producer=_producer())
    assert row.producer.producer == "triage:secrets"
    assert row.producer.version == 2


def test_a_missing_declared_category_is_refused():
    """The row-level analogue of compute_readiness filling an unreported
    dimension rather than leaving it absent."""
    with pytest.raises(ValidationError, match="categor"):
        _row(SignalSource.COMPUTED, categories={})


def test_an_undeclared_category_is_refused():
    cats = {k: Measurement.not_collected("x") for k in CATEGORIES[ScanSignalId.SS1]}
    with pytest.raises(ValidationError, match="undeclared"):
        _row(SignalSource.COMPUTED, categories=cats | {"invented": Measurement.measured(1.0)})


def test_producer_version_is_pinned_so_a_triage_bump_is_visible():
    p = _producer()
    assert p.version == 2, (
        "the producing signal's version is recorded, so a triage version bump "
        "changes the assessment visibly rather than silently"
    )


def test_not_collected_row_may_still_declare_its_categories():
    row = _row(SignalSource.COMPUTED, collected=Measurement.not_collected("scan stub (plan 2)"))
    assert row.collected.state is CollectionState.NOT_COLLECTED
    assert set(row.categories) == set(CATEGORIES[ScanSignalId.SS1])
