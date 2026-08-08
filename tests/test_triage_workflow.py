"""E-42: TriageWorkflow pins a commit, fans out the signals, and computes the
verdict. The pure helpers are tested directly; sequencing is tested through
the workflow, following tests/test_deployment_workflow.py."""
from __future__ import annotations

from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.models import (
    M_BUILDABLE, M_RUNNABLE, SignalResult, Verdict, compute_readiness,
)
from sdlc.workflows.triage import TriageInput, skipped_signal


def test_skipped_signal_reports_its_owed_keys_as_not_collected():
    """D6/D8a: the skip is named, and the dimension is not merely absent."""
    r = skipped_signal("build_probe", "build probe not run (--no-build-probe)")
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert set(r.metrics) == {M_BUILDABLE, M_RUNNABLE}
    for m in r.metrics.values():
        assert m.state is CollectionState.NOT_COLLECTED
        # Measurement's field is `reason` (measurement.py:37), not `detail`,
        # and NOT_COLLECTED without one does not construct.
        assert "--no-build-probe" in m.reason


def test_skipped_signal_owing_nothing_carries_no_metrics():
    r = skipped_signal("secrets", "secrets activity failed: TimeoutError")
    assert r.metrics == {}
    assert r.collected.state is CollectionState.NOT_COLLECTED


def test_skipped_signal_carries_no_findings():
    """SignalResult's validator rejects findings on a NOT_COLLECTED result --
    those would be findings from a run that did not happen."""
    assert skipped_signal("secrets", "why").findings == []


def test_a_skipped_build_probe_forces_indeterminate():
    """D6: no change to compute_readiness is needed."""
    signals = [
        skipped_signal("build_probe", "build probe not run (--no-build-probe)"),
        SignalResult(signal="baseline", version=2,
                     collected=Measurement.measured(1.0),
                     metrics={"tests_present": Measurement.measured(3.0)}),
    ]
    assert compute_readiness(signals).verdict is Verdict.INDETERMINATE


def test_triage_input_defaults():
    inp = TriageInput(repo_dir="/r")
    assert inp.commit == "HEAD"
    assert inp.build_probe is True          # D6: on by default
    assert inp.advisory_source == "none"    # E-41a: declared egress, opt-in
    assert inp.gates.gates == {}            # so `readiness` falls back to HARD
    assert inp.max_gate_rounds == 2
