"""D2/D7: the read-through. Findings are cited by identity, never copied, and
this half is derived in workflow code from an artifact already in hand."""

from __future__ import annotations

from sdlc.assessment.scan.inherit import inherited_halves
from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ,
    C_CI_PRESENT,
    C_CREDENTIAL_STORAGE,
    C_DIRECT_DEPS,
    C_FRAMEWORK_DEFAULTS,
    C_TESTS_PRESENT,
    ScanSignalId,
)
from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.models import (
    FixClass,
    Readiness,
    RepoTriage,
    SignalResult,
    TriageFinding,
    Verdict,
    finding_identity,
)


def _finding(signal: str, rule: str, path: str = "x.py", key: str = "") -> TriageFinding:
    return TriageFinding(
        signal=signal,
        rule=rule,
        severity="high",
        detail="d",
        path=path,
        fix_class=FixClass.MECHANICAL,
        key=key,
    )


def _triage(*signals: SignalResult, tests: float = 2.0) -> RepoTriage:
    ok = Measurement.measured(1.0)
    return RepoTriage(
        repo_dir="/r",
        commit_sha="a" * 40,
        toolchain="python",
        readiness=Readiness(
            buildable=ok,
            runnable=ok,
            tests_present=Measurement.measured(tests),
            structure_discernible=ok,
            verdict=Verdict.READY,
        ),
        signals=list(signals),
    )


def _sig(
    signal: str,
    version: int,
    findings: list[TriageFinding],
    metrics: dict[str, Measurement] | None = None,
) -> SignalResult:
    return SignalResult(
        signal=signal,
        version=version,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics=metrics or {},
    )


def test_five_signals_have_an_inherited_half():
    halves = inherited_halves(_triage())
    assert set(halves) == {
        ScanSignalId.SS1,
        ScanSignalId.SS2,
        ScanSignalId.SS3,
        ScanSignalId.QS1,
        ScanSignalId.QS4,
    }


def test_ss1_cites_secrets_findings_by_identity_and_copies_none():
    f = _finding("secrets", "aws_key", ".env", "abc")
    halves = inherited_halves(_triage(_sig("secrets", 2, [f])))
    producer = halves[ScanSignalId.SS1].producer
    assert finding_identity(f) in producer.finding_ids
    assert producer.version == 2
    assert "secrets" in producer.producer


def test_ss1_credential_storage_is_measured_with_the_finding_count():
    f = _finding("secrets", "aws_key", ".env", "abc")
    cats = inherited_halves(_triage(_sig("secrets", 2, [f])))[ScanSignalId.SS1].categories
    assert cats[C_CREDENTIAL_STORAGE].state is CollectionState.MEASURED
    assert cats[C_CREDENTIAL_STORAGE].value == 1.0


def test_a_missing_triage_signal_yields_not_collected_not_zero():
    """The signal never ran, so the category has no value (FR-915)."""
    cats = inherited_halves(_triage())[ScanSignalId.SS1].categories
    assert cats[C_CREDENTIAL_STORAGE].state is CollectionState.NOT_COLLECTED
    assert cats[C_CREDENTIAL_STORAGE].value is None
    assert "secrets" in cats[C_CREDENTIAL_STORAGE].reason


def test_a_not_collected_triage_signal_propagates_its_reason():
    sig = SignalResult(
        signal="secrets", version=2, collected=Measurement.not_collected("scan timed out")
    )
    cats = inherited_halves(_triage(sig))[ScanSignalId.SS1].categories
    assert cats[C_CREDENTIAL_STORAGE].state is CollectionState.NOT_COLLECTED
    assert "timed out" in cats[C_CREDENTIAL_STORAGE].reason


def test_only_inherited_categories_appear_in_the_half():
    """The computed categories (TLS, input validation) are the activity's, so
    the half must not claim them -- the workflow unions the two (D7)."""
    cats = inherited_halves(_triage(_sig("secrets", 2, [])))[ScanSignalId.SS1].categories
    assert set(cats) == {C_CREDENTIAL_STORAGE, C_AUTHN_AUTHZ}


def test_ss3_inherits_framework_defaults_from_misconfig():
    f = _finding("misconfig", "permissive_cors", "app.py", "x")
    cats = inherited_halves(_triage(_sig("misconfig", 2, [f])))[ScanSignalId.SS3].categories
    assert set(cats) == {C_FRAMEWORK_DEFAULTS}
    assert cats[C_FRAMEWORK_DEFAULTS].value == 1.0


def test_ss2_inherits_direct_dependencies_and_is_the_whole_signal():
    """D12 cut transitive deps, so SS2 has no computed half at all."""
    f = _finding("dependencies", "known_vulnerable", "poetry.lock", "pkg")
    half = inherited_halves(_triage(_sig("dependencies", 1, [f])))[ScanSignalId.SS2]
    assert set(half.categories) == {C_DIRECT_DEPS}
    assert half.categories[C_DIRECT_DEPS].value == 1.0


def test_qs1_inherits_the_test_count_from_baselines_metric_not_its_findings():
    """tests_present is a COUNT on baseline.metrics, not a finding tally."""
    sig = _sig("baseline", 2, [], {"tests_present": Measurement.measured(7.0)})
    cats = inherited_halves(_triage(sig))[ScanSignalId.QS1].categories
    assert set(cats) == {C_TESTS_PRESENT}
    assert cats[C_TESTS_PRESENT].value == 7.0


def test_qs4_ci_present_is_the_absence_of_baselines_no_ci_finding():
    """baseline reports a finding when CI is MISSING, so ci_present is 1.0
    when that finding is absent and 0.0 when it fires. This inversion is why
    the mapping is a declared function rather than a generic tally."""
    with_ci = inherited_halves(_triage(_sig("baseline", 2, [])))[ScanSignalId.QS4].categories
    assert with_ci[C_CI_PRESENT].value == 1.0

    without = inherited_halves(_triage(_sig("baseline", 2, [_finding("baseline", "no_ci")])))[
        ScanSignalId.QS4
    ].categories
    assert without[C_CI_PRESENT].value == 0.0


def test_qs4_ci_present_is_not_collected_when_baseline_did_not_run():
    sig = SignalResult(signal="baseline", version=2, collected=Measurement.not_collected("boom"))
    cats = inherited_halves(_triage(sig))[ScanSignalId.QS4].categories
    assert cats[C_CI_PRESENT].state is CollectionState.NOT_COLLECTED
