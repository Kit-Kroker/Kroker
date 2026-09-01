"""Averaging across the E-83 judge change must be visible, not implicit.

Same discipline WasteBag applies to not-measured: a number whose provenance
changed mid-corpus is not the same number."""

from datetime import UTC, datetime

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.score import judge_mix_notes

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _rec(case, judge, score=0.8):
    return BenchmarkRecord(
        run_id="r1",
        bench_run_id="b1",
        case_id=case,
        scope=BenchmarkScope.STAGE,
        stage="clarify",
        role="clarify",
        model="m",
        quality=QualityScore(score=score, judge=judge),
        speed=SpeedBag(wall_clock_s=1.0, started_at=_NOW, ended_at=_NOW),
        outcome=BenchmarkOutcome.PASS,
    )


def test_single_judge_kind_produces_no_note():
    assert judge_mix_notes([_rec("c1", "llm_judge"), _rec("c1", "llm_judge")]) == []


def test_mixed_judge_kinds_in_one_case_produce_a_note():
    notes = judge_mix_notes([_rec("c1", "llm_judge"), _rec("c1", "staged_rubric")])
    assert len(notes) == 1
    assert "c1" in notes[0]
    assert "llm_judge" in notes[0] and "staged_rubric" in notes[0]


def test_notes_are_per_case():
    notes = judge_mix_notes(
        [_rec("c1", "llm_judge"), _rec("c1", "staged_rubric"), _rec("c2", "staged_rubric")]
    )
    assert len(notes) == 1


def test_non_scoring_judges_do_not_count_as_a_mix():
    """'oracle', 'contract' and the lenses are different INSTRUMENTS, not
    two versions of one scale. Flagging them would cry wolf on every corpus."""
    assert (
        judge_mix_notes(
            [
                _rec("c1", "staged_rubric"),
                _rec("c1", "oracle"),
                _rec("c1", "deep_review"),
                _rec("c1", "contract"),
            ]
        )
        == []
    )


def test_unscored_records_are_ignored():
    assert judge_mix_notes([_rec("c1", "staged_rubric"), _rec("c1", "error", score=None)]) == []


def test_notes_are_ascii_only():
    """report.py:70-74 -- the notes block is ASCII."""
    notes = judge_mix_notes([_rec("c1", "llm_judge"), _rec("c1", "staged_rubric")])
    notes[0].encode("ascii")
