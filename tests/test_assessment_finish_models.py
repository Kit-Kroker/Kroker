# tests/test_assessment_finish_models.py
"""FR-918 (E-51): FinishReport's structural rules and the 14-criterion
manifest. Contracts only -- the criteria themselves and the cross-reference
walk arrive in later tasks."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from sdlc.assessment.finish.models import CRITERIA_MANIFEST, FinishReport
from sdlc.gate import CheckClass, CheckResult
from sdlc.measurement import Measurement


def _check(
    name: str, passed: bool = True, classification: CheckClass = CheckClass.ABSOLUTE
) -> CheckResult:
    return CheckResult(name=name, passed=passed, classification=classification)


def _report(**overrides) -> FinishReport:
    fields: dict = {"collected": Measurement.measured(1.0)}
    fields.update(overrides)
    return FinishReport(**fields)


def test_manifest_has_the_fourteen():
    """The manifest is the 14 wire names, unique, in c01..c14 id order."""
    assert len(CRITERIA_MANIFEST) == 14
    assert len(set(CRITERIA_MANIFEST)) == 14
    for name in CRITERIA_MANIFEST:
        assert re.fullmatch(r"c\d{2}_.+", name)
    assert [name[:3] for name in CRITERIA_MANIFEST] == [f"c{i:02d}" for i in range(1, 15)]


def test_manifest_is_frozen_tuple():
    assert isinstance(CRITERIA_MANIFEST, tuple)
    assert not isinstance(CRITERIA_MANIFEST, list)


def test_unsorted_rows_raise():
    """criteria and exits sort by row name; owed sorts as strings."""
    with pytest.raises(ValidationError, match="sorted"):
        _report(criteria=(_check("c02_qa_context"), _check("c01_security_context")))
    with pytest.raises(ValidationError, match="sorted"):
        _report(exits=(_check("exit:scan:z"), _check("exit:scan:a")))
    with pytest.raises(ValidationError, match="sorted"):
        _report(
            owed=(
                "c13_five_reports: not collected (E-52)",
                "c07_unified_drivers: deferred (E-56)",
            )
        )


def test_duplicate_names_raise():
    with pytest.raises(ValidationError, match="duplicate"):
        _report(criteria=(_check("c01_security_context"), _check("c01_security_context")))
    with pytest.raises(ValidationError, match="duplicate"):
        _report(exits=(_check("exit:scan:a"), _check("exit:scan:a")))
    with pytest.raises(ValidationError, match="deduped"):
        _report(owed=("c13_five_reports: not collected (E-52)",) * 2)


def test_passed_reads_only_absolute_rows():
    """Owed rows are not rows -- they never fail `passed`; an empty report
    has nothing evaluated and nothing failed."""
    advisory_fail = _report(
        criteria=(
            _check("c01_security_context"),
            _check("c10_coverage_floor", passed=False, classification=CheckClass.ADVISORY),
        )
    )
    assert advisory_fail.passed is True

    absolute_fail = _report(criteria=(_check("c14_cross_reference_integrity", passed=False),))
    assert absolute_fail.passed is False

    assert _report().passed is True
