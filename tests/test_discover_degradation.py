"""FR-915 at the coverage ratio: a value that was never measured must not be
representable as a measured one."""

from __future__ import annotations

from sdlc.assessment.discover.attribution import attribute
from sdlc.assessment.discover.models import FileBucket
from sdlc.measurement import CollectionState

MEMBERS = {"BC-001": ["src/payments/api.py"]}


def test_an_empty_capability_set_is_not_collected():
    report = attribute({"src/a.py": "x = 1\n"}, [], {}, [])
    assert report.coverage.state is CollectionState.NOT_COLLECTED
    assert "no capabilities" in report.coverage.reason
    assert report.coverage.value is None
    assert report.meets_floor is False


def test_an_empty_denominator_is_not_collected_not_perfect():
    """A division by zero must never read as perfect coverage."""
    report = attribute({"README.md": "# hi\n"}, [], MEMBERS, [])
    assert report.coverage.state is CollectionState.NOT_COLLECTED
    assert "no source files" in report.coverage.reason
    assert report.coverage.value is None
    assert report.meets_floor is False


def test_a_not_collected_report_still_carries_every_bucket_count():
    report = attribute({}, [], MEMBERS, [])
    assert set(report.counts) == set(FileBucket)
    assert sum(report.counts.values()) == 0


def test_skipped_blobs_are_named_in_the_report():
    report = attribute(
        {"src/payments/api.py": "x = 1\n"}, ["src/broken.py", "notes.md"], MEMBERS, []
    )
    assert report.skipped == ("src/broken.py",)  # notes.md is not source
    assert report.counts[FileBucket.UNCLASSIFIED] == 1


def test_an_unreadable_tree_cannot_score_one():
    """Every source file skipped: the model attributed nothing, and dropping
    skipped files from the denominator would have scored 1.0."""
    report = attribute({}, ["src/a.py", "src/b.py"], MEMBERS, [])
    assert report.coverage.state is CollectionState.MEASURED
    assert report.coverage.value == 0.0
    assert report.meets_floor is False
