"""D4/D5: compute_delta is the only producer of a FindingState, and absence is
never read as resolution. Each honesty rule gets a test."""
import pytest

from sdlc.measurement import Measurement
from sdlc.triage.delta import FindingDelta, FindingState, compute_delta
from sdlc.triage.models import (
    FixClass, Readiness, RepoTriage, SignalResult, TriageFinding, Verdict,
)


def _finding(rule="gitignore_missing", key="", signal="baseline"):
    return TriageFinding(signal=signal, rule=rule, severity="medium",
                         detail="d", path=".gitignore", key=key,
                         fix_class=FixClass.MECHANICAL)


def _sig(signal="baseline", version=2, findings=(), collected=None):
    return SignalResult(
        signal=signal, version=version,
        collected=collected or Measurement.measured(float(len(findings))),
        findings=list(findings))


def _triage(*signals):
    m = Measurement.measured(1.0)
    return RepoTriage(
        repo_dir="/r", commit_sha="a" * 40,
        readiness=Readiness(buildable=m, runnable=m, tests_present=m,
                            structure_discernible=m, verdict=Verdict.READY),
        signals=list(signals))


def test_present_before_absent_after_is_resolved():
    out = compute_delta(_triage(_sig(findings=[_finding()])),
                        _triage(_sig(findings=[])))
    assert [d.state for d in out] == [FindingState.RESOLVED]


def test_present_in_both_is_persisted():
    out = compute_delta(_triage(_sig(findings=[_finding()])),
                        _triage(_sig(findings=[_finding()])))
    assert [d.state for d in out] == [FindingState.PERSISTED]


def test_present_only_after_is_new():
    out = compute_delta(_triage(_sig(findings=[])),
                        _triage(_sig(findings=[_finding()])))
    assert [d.state for d in out] == [FindingState.NEW]


def test_signal_not_collected_after_is_unverifiable_not_resolved():
    """D5 rule 1. The load-bearing one: a signal that timed out on the after
    side would otherwise read as having fixed everything it found."""
    after = _triage(_sig(findings=[],
                         collected=Measurement.not_collected("timed out")))
    out = compute_delta(_triage(_sig(findings=[_finding()])), after)
    assert [d.state for d in out] == [FindingState.UNVERIFIABLE]
    assert "timed out" in out[0].reason


def test_signal_not_collected_before_is_also_unverifiable():
    before = _triage(_sig(findings=[],
                          collected=Measurement.not_collected("git failed")))
    out = compute_delta(before, _triage(_sig(findings=[_finding()])))
    assert [d.state for d in out] == [FindingState.UNVERIFIABLE]


def test_signal_absent_from_the_after_side_is_unverifiable():
    out = compute_delta(_triage(_sig(findings=[_finding()])), _triage())
    assert [d.state for d in out] == [FindingState.UNVERIFIABLE]
    assert "did not report" in out[0].reason


def test_version_mismatch_is_unverifiable():
    """D5 rule 2: a rule that changed between the two triages did not measure
    the same thing twice."""
    out = compute_delta(
        _triage(_sig(version=2, findings=[_finding()])),
        _triage(_sig(version=3, findings=[])))
    assert [d.state for d in out] == [FindingState.UNVERIFIABLE]
    assert "version" in out[0].reason


def test_conflicted_identity_is_unverifiable_not_persisted():
    """D5 rule 3: the fix is real but absent from the tree we measured."""
    f = _finding()
    identity = "baseline:gitignore_missing:.gitignore:"
    out = compute_delta(_triage(_sig(findings=[f])),
                        _triage(_sig(findings=[f])),
                        conflicted=[identity])
    assert [d.state for d in out] == [FindingState.UNVERIFIABLE]
    assert "conflict" in out[0].reason


def test_after_is_none_marks_every_identity_unverifiable():
    """D5 rule 4: never an empty delta reading as 'nothing resolved'."""
    out = compute_delta(
        _triage(_sig(findings=[_finding(key="a"), _finding(key="b")])), None)
    assert len(out) == 2
    assert all(d.state is FindingState.UNVERIFIABLE for d in out)
    assert all(d.reason for d in out)


def test_output_is_sorted_by_identity():
    before = _triage(_sig(findings=[_finding(key="z"), _finding(key="a")]))
    out = compute_delta(before, _triage(_sig(findings=[])))
    assert [d.identity for d in out] == sorted(d.identity for d in out)


def test_delta_carries_the_findings_own_signal_rule_and_severity():
    out = compute_delta(_triage(_sig(findings=[_finding()])),
                        _triage(_sig(findings=[])))
    assert (out[0].signal, out[0].rule, out[0].severity) == (
        "baseline", "gitignore_missing", "medium")


def test_unverifiable_requires_a_reason():
    with pytest.raises(ValueError, match="reason"):
        FindingDelta(identity="i", signal="s", rule="r", severity="low",
                     state=FindingState.UNVERIFIABLE)


def test_a_measured_state_does_not_require_a_reason():
    d = FindingDelta(identity="i", signal="s", rule="r", severity="low",
                     state=FindingState.RESOLVED)
    assert d.reason == ""
