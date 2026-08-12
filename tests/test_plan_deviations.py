"""Plan deviations ride the deep_review lens and obey its evidence rule.

An accusation must quote a line the transcript actually contains. Dropping,
never failing -- this lens must never fail delivery."""
from sdlc.handoff import verified_plan_deviations
from sdlc.models import PlanDeviation

_TRANSCRIPT = (
    "file_read src/app.py\n"
    "file_write src/billing.py\n"
    "command pytest -q exit=0\n"
)


def _dev(evidence, kind="unplanned_scope"):
    return PlanDeviation(kind=kind, detail="d", evidence=evidence)


def test_deviation_with_real_evidence_is_kept():
    kept, dropped = verified_plan_deviations(
        [_dev("file_write src/billing.py")], _TRANSCRIPT)
    assert len(kept) == 1
    assert dropped == 0


def test_deviation_with_invented_evidence_is_dropped():
    kept, dropped = verified_plan_deviations(
        [_dev("file_write src/nowhere.py")], _TRANSCRIPT)
    assert kept == []
    assert dropped == 1


def test_paraphrased_evidence_is_dropped():
    kept, dropped = verified_plan_deviations(
        [_dev("the agent wrote to the billing module")], _TRANSCRIPT)
    assert kept == []
    assert dropped == 1


def test_empty_evidence_survives():
    """Same three rules as verified_integrity_flags: an empty quote survives."""
    kept, dropped = verified_plan_deviations([_dev("")], _TRANSCRIPT)
    assert len(kept) == 1
    assert dropped == 0


def test_missing_transcript_skips_verification():
    kept, dropped = verified_plan_deviations([_dev("anything")], None)
    assert len(kept) == 1
    assert dropped == 0


def test_report_defaults_to_no_deviations():
    from sdlc.models import DeepReviewReport
    assert DeepReviewReport().plan_deviations == []
