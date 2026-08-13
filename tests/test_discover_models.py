"""E-47b: the report's validators, which are the artifact's real contract."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.models import (
    ACCOUNTED_FOR, BUCKET_PRECEDENCE, DEFAULT_COVERAGE_FLOOR,
    AttributionReport, FileAttribution, FileBucket, ReferenceGraph,
)
from sdlc.measurement import Measurement

EMPTY_GRAPH = ReferenceGraph(
    unresolved_relative_rate=Measurement.not_collected("no relative imports"))


def _report(files, coverage, *, floor=DEFAULT_COVERAGE_FLOOR,
            meets=None, tripped=False):
    counts = {b: sum(1 for f in files if f.bucket is b) for b in FileBucket}
    if meets is None:
        meets = coverage.value is not None and coverage.value >= floor
    return AttributionReport(
        files=tuple(files), counts=counts, coverage=coverage, floor=floor,
        meets_floor=meets, dead_guard_tripped=tripped, graph=EMPTY_GRAPH)


def test_precedence_is_declaration_order():
    assert BUCKET_PRECEDENCE == (
        FileBucket.MEMBER, FileBucket.INFRASTRUCTURE, FileBucket.ATTACHED,
        FileBucket.DEAD, FileBucket.UNCLASSIFIED)
    assert ACCOUNTED_FOR == frozenset(BUCKET_PRECEDENCE[:3])


def test_member_must_cite_a_capability():
    with pytest.raises(ValidationError, match="must cite"):
        FileAttribution(path="a.py", bucket=FileBucket.MEMBER,
                        rule="capability_member")


def test_dead_must_not_cite_a_capability():
    with pytest.raises(ValidationError, match="must not cite"):
        FileAttribution(path="a.py", bucket=FileBucket.DEAD,
                        rule="no_static_inbound_reference",
                        capabilities=("BC-001",))


def test_capabilities_must_be_sorted_and_deduped():
    with pytest.raises(ValidationError, match="sorted"):
        FileAttribution(path="a.py", bucket=FileBucket.MEMBER,
                        rule="capability_member",
                        capabilities=("BC-002", "BC-001"))


def test_counts_must_agree_with_files():
    good = FileAttribution(path="a.py", bucket=FileBucket.MEMBER,
                           rule="capability_member", capabilities=("BC-001",))
    with pytest.raises(ValidationError, match="counts"):
        AttributionReport(
            files=(good,),
            counts={b: 0 for b in FileBucket},
            coverage=Measurement.measured(1.0), meets_floor=True,
            dead_guard_tripped=False, graph=EMPTY_GRAPH)


def test_counts_must_carry_every_bucket_including_zeros():
    with pytest.raises(ValidationError, match="every bucket"):
        AttributionReport(
            files=(), counts={FileBucket.MEMBER: 0},
            coverage=Measurement.not_collected("no source files"),
            meets_floor=False, dead_guard_tripped=False, graph=EMPTY_GRAPH)


def test_meets_floor_is_derived_not_assigned():
    files = [FileAttribution(path="a.py", bucket=FileBucket.MEMBER,
                             rule="capability_member",
                             capabilities=("BC-001",))]
    with pytest.raises(ValidationError, match="derived"):
        _report(files, Measurement.measured(1.0), meets=False)


def test_not_collected_coverage_never_meets_the_floor():
    with pytest.raises(ValidationError, match="derived"):
        _report([], Measurement.not_collected("no capabilities"), meets=True)


def test_not_collected_coverage_with_meets_false_constructs():
    report = _report([], Measurement.not_collected("no capabilities"),
                     meets=False)
    assert report.meets_floor is False


def test_exactly_the_floor_meets_it():
    files = [
        FileAttribution(path=f"m{i}.py", bucket=FileBucket.MEMBER,
                        rule="capability_member", capabilities=("BC-001",))
        for i in range(9)
    ] + [FileAttribution(path="d.py", bucket=FileBucket.DEAD,
                         rule="no_static_inbound_reference")]
    assert _report(files, Measurement.measured(0.90)).meets_floor is True
