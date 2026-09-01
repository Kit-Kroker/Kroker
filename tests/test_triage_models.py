"""E-41 contracts: a signal that did not run must not carry findings."""

import pytest
from pydantic import ValidationError

from sdlc.measurement import Measurement
from sdlc.triage.models import (
    FixClass,
    Readiness,
    RepoTriage,
    SignalResult,
    TriageFinding,
    Verdict,
)


def _finding(**kw):
    base = dict(
        signal="secrets", rule="r", severity="high", detail="d", fix_class=FixClass.JUDGEMENT
    )
    base.update(kw)
    return TriageFinding(**base)


def test_not_collected_may_not_carry_findings():
    with pytest.raises(ValidationError) as exc:
        SignalResult(
            signal="secrets",
            version=1,
            collected=Measurement.not_collected("crashed"),
            findings=[_finding()],
        )
    assert "did not happen" in str(exc.value)


def test_unknown_may_carry_partial_findings():
    r = SignalResult(
        signal="secrets",
        version=1,
        collected=Measurement.unknown("partial read"),
        findings=[_finding()],
    )
    assert len(r.findings) == 1


def test_measured_carries_findings():
    r = SignalResult(
        signal="secrets", version=1, collected=Measurement.measured(1.0), findings=[_finding()]
    )
    assert r.findings[0].fix_class is FixClass.JUDGEMENT


def test_signal_result_defaults_are_empty():
    r = SignalResult(signal="baseline", version=1, collected=Measurement.measured(0.0))
    assert r.findings == []
    assert r.metrics == {}


def test_repo_triage_holds_readiness_and_signals():
    readiness = Readiness(
        buildable=Measurement.measured(1.0),
        runnable=Measurement.measured(1.0),
        tests_present=Measurement.measured(3.0),
        structure_discernible=Measurement.measured(1.0),
        verdict=Verdict.READY,
    )
    t = RepoTriage(repo_dir="/r", commit_sha="abc123", toolchain="python", readiness=readiness)
    assert t.readiness.verdict is Verdict.READY
    assert t.signals == []
