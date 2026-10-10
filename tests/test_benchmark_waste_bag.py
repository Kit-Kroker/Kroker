from datetime import datetime, timedelta

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    QualityScore,
    SpeedBag,
    WasteBag,
)
from sdlc.core.models import (
    HarnessKind,
)
from sdlc.harness.models import SessionDigest

T = datetime(2026, 8, 3, 10)


def _digest(**kw):
    base = dict(
        tool_calls=12,
        file_reads=8,
        file_rereads=3,
        files_written=4,
        rewrite_churn=2,
        failed_commands=1,
        model_turns=6,
        denials=1,
        escalations=2,
        compacted=True,
        input_tokens=100,
        output_tokens=20,
        decision_skeleton=["Read a.py", "Edit a.py"],
    )
    base.update(kw)
    return SessionDigest(**base)


def test_from_digest_copies_every_waste_field():
    bag = WasteBag.from_digest(_digest())
    assert bag == WasteBag(
        tool_calls=12,
        file_reads=8,
        file_rereads=3,
        files_written=4,
        rewrite_churn=2,
        failed_commands=1,
        model_turns=6,
        denials=1,
        escalations=2,
        compacted=True,
    )


def test_from_digest_drops_skeleton_and_tokens():
    """decision_skeleton is up to 200 strings and tokens live on CostBag;
    neither belongs in a file scanned repeatedly."""
    bag = WasteBag.from_digest(_digest())
    assert not hasattr(bag, "decision_skeleton")
    assert not hasattr(bag, "input_tokens")


def test_from_digest_returns_none_when_unmeasured():
    """An absent session is 'not measured', never 'measured zero'."""
    assert WasteBag.from_digest(None) is None


def test_record_waste_defaults_to_none():
    rec = _record()
    assert rec.waste is None


def test_record_written_before_this_change_still_parses():
    """Backward-compatibility invariant: a records.jsonl line with no
    `waste` key must keep parsing."""
    legacy = (
        '{"run_id":"r1","bench_run_id":"b1","case_id":"c1","scope":"stage",'
        '"stage":"code","role":"dev","harness":"opencode","model":"m",'
        '"prompt_sha":"","quality":{"score":1.0,"judge":"contract"},'
        '"cost":{},"speed":{"wall_clock_s":1.0,'
        '"started_at":"2026-08-03T10:00:00","ended_at":"2026-08-03T10:00:01"},'
        '"outcome":"pass","fix_attempts":0}'
    )
    rec = BenchmarkRecord.model_validate_json(legacy)
    assert rec.waste is None
    assert rec.model == "m"


def test_record_round_trips_waste():
    rec = _record(waste=WasteBag(tool_calls=5))
    again = BenchmarkRecord.model_validate_json(rec.model_dump_json())
    assert again.waste is not None and again.waste.tool_calls == 5


def _record(**kw):
    base = dict(
        run_id="r1",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage="code",
        role="dev",
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T, ended_at=T + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
    )
    base.update(kw)
    return BenchmarkRecord(**base)


# --- 013 T014 (R-15): the capture mark and waste_measured ----------------------


def test_from_digest_copies_capture_rev():
    bag = WasteBag.from_digest(_digest(capture_rev=1))
    assert bag.capture_rev == 1


def test_stored_shape_bag_reads_capture_rev_none():
    """A bag written before the field existed must keep parsing."""
    bag = WasteBag.model_validate_json('{"tool_calls": 3, "model_turns": 5}')
    assert bag.tool_calls == 3
    assert bag.capture_rev is None


def test_waste_measured_rule():
    """Contract 10.1 / R-15: not measured when there is no bag, or when an
    unmarked zero-tool bag comes from a harness whose old parser counted no
    tool events -- opencode, and a crew cell, whose session is captured
    under the role's opencode CLI (baseline (f))."""
    from sdlc.benchmarks.models import waste_measured

    assert waste_measured(_record()) is False  # no bag
    assert waste_measured(_record(waste=WasteBag())) is False  # opencode, unmarked, 0 tools
    assert waste_measured(_record(waste=WasteBag(tool_calls=3))) is True
    assert waste_measured(_record(waste=WasteBag(capture_rev=1))) is True
    assert waste_measured(_record(harness=HarnessKind.CLAUDE_CODE, waste=WasteBag())) is True
    assert waste_measured(_record(harness=HarnessKind.CREW, waste=WasteBag())) is False
    assert waste_measured(_record(harness=HarnessKind.CREW, waste=WasteBag(capture_rev=1))) is True
    assert waste_measured(_record(harness=HarnessKind.CREW, waste=WasteBag(tool_calls=2))) is True
