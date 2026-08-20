"""Fan-out wiring: a dead probe degrades ALONE.

run_or_degrade exists because a timeout, a lost worker or an exhausted retry
happens OUTSIDE the activity, where its own try/except cannot keep it. A
clarifier that cannot ask about data semantics is degraded, not broken."""
from sdlc.clarify.models import ProbeResult
from sdlc.models import ClarificationDimension as CD
from sdlc.models import OpenQuestion
from sdlc.workflows.feature import _probe_results_from

C3, C4, C6 = (CD.TECHNICAL_CONTEXT, CD.INTERFACE_SPEC, CD.DATA_SEMANTICS)


def _ok(dim):
    return ProbeResult(dimension=dim, questions=[
        OpenQuestion(id=f"{dim.value}-1", question="q?", why_it_matters="w",
                     dimension=dim, materiality=0.5, evidence="a.py")])


def test_all_successful_probes_pass_through():
    out = _probe_results_from([C4], [_ok(C4)])
    assert [p.dimension for p in out] == [C4]


def test_an_exception_drops_that_dimension_rather_than_raising():
    out = _probe_results_from([C4], [RuntimeError("worker died")])
    assert out == []


def test_one_failure_does_not_discard_its_siblings():
    out = _probe_results_from([C3, C4], [RuntimeError("boom"), _ok(C4)])
    assert [p.dimension for p in out] == [C4]


def test_a_dead_probe_is_absent_while_an_abstention_is_present():
    # The distinction is the whole point of dimensions_probed: absent means
    # "never ran", present-and-empty means "ran and had nothing to ask".
    abstained = ProbeResult(dimension=C3, questions=[])
    out = _probe_results_from([C3, C6], [abstained, RuntimeError("dead")])
    assert [p.dimension for p in out] == [C3]
    assert out[0].questions == []


def test_all_probes_failing_degrades_to_the_supervisor_alone():
    out = _probe_results_from([C3, C4], [RuntimeError("a"), RuntimeError("b")])
    assert out == []


def test_a_probe_answering_for_the_wrong_dimension_is_corrected():
    # The burst knows which probe was asked; the model's self-report is not
    # authoritative, and a mislabelled result would corrupt dimensions_probed.
    out = _probe_results_from([C4], [ProbeResult(dimension=C6, questions=[])])
    assert [p.dimension for p in out] == [C4]
