"""Deterministic merge of the supervisor's and the probes' questions. Pure --
no model, no I/O.

The cap is load-bearing: MAC raised task success WHILE CUTTING dialogue turns
(6.53 -> 4.86), and six dimensions sweeping in parallel is a direct assault on
that. `dropped` is what keeps capping distinguishable from incuriosity."""
from sdlc.clarify.merge import merge_clarification
from sdlc.clarify.models import ClarifyRoute, ProbeResult
from sdlc.models import ClarificationDimension as CD
from sdlc.models import OpenQuestion

GROUNDED = frozenset({CD.TECHNICAL_CONTEXT, CD.INTERFACE_SPEC,
                      CD.CODE_STRUCTURE, CD.DATA_SEMANTICS})


def _q(qid, text="q?", *, dim=None, mat=None, ev=None, asked_by="probe:C4"):
    return OpenQuestion(id=qid, question=text, why_it_matters="w",
                        dimension=dim, materiality=mat, evidence=ev,
                        asked_by=asked_by)


def _route(*questions):
    return ClarifyRoute(summary="s", functional_requirements=["fr"],
                        non_functional_requirements=["nfr"],
                        out_of_scope=["oos"], questions=list(questions),
                        live_dimensions=[])


def _merge(route, probes, cap=5, grounded=GROUNDED):
    return merge_clarification(route, probes, cap=cap, grounded=grounded)


def test_the_requirements_body_comes_from_the_route():
    out = _merge(_route(), [])
    assert out.summary == "s"
    assert out.functional_requirements == ["fr"]
    assert out.non_functional_requirements == ["nfr"]
    assert out.out_of_scope == ["oos"]


def test_no_probes_yields_only_supervisor_questions():
    sup = _q("S1", dim=CD.FUNCTIONAL_INTENT, mat=0.8, asked_by="supervisor")
    out = _merge(_route(sup), [])
    assert [q.id for q in out.open_questions] == ["S1"]
    assert out.dropped == []


def test_probe_questions_join_the_supervisors():
    sup = _q("S1", "sup?", dim=CD.FUNCTIONAL_INTENT, mat=0.5,
             asked_by="supervisor")
    probe = ProbeResult(dimension=CD.INTERFACE_SPEC, questions=[
        _q("P1", "probe?", dim=CD.INTERFACE_SPEC, mat=0.9, ev="api.py")])
    out = _merge(_route(sup), [probe])
    assert {q.id for q in out.open_questions} == {"S1", "P1"}


def test_ranking_is_by_materiality_descending():
    probe = ProbeResult(dimension=CD.INTERFACE_SPEC, questions=[
        _q("P1", "low?", dim=CD.INTERFACE_SPEC, mat=0.2, ev="a.py"),
        _q("P2", "high?", dim=CD.INTERFACE_SPEC, mat=0.95, ev="b.py")])
    out = _merge(_route(), [probe])
    assert [q.id for q in out.open_questions] == ["P2", "P1"]


def test_a_question_without_materiality_sorts_last():
    probe = ProbeResult(dimension=CD.INTERFACE_SPEC, questions=[
        _q("P1", "unscored?", dim=CD.INTERFACE_SPEC, ev="a.py"),
        _q("P2", "scored?", dim=CD.INTERFACE_SPEC, mat=0.1, ev="b.py")])
    out = _merge(_route(), [probe])
    assert [q.id for q in out.open_questions] == ["P2", "P1"]


def test_ties_break_by_dimension_before_id_so_replays_are_stable():
    # Ids run counter to dimension order here on purpose: TECHNICAL_CONTEXT
    # (C3) gets the *later* id "Z" and DATA_SEMANTICS (C6) gets the *earlier*
    # id "A". If an implementation dropped the dimension component from the
    # sort key, id-ascending alone would put "A" first -- the wrong answer --
    # so this catches that bug where the old same-direction fixture couldn't.
    probes = [
        ProbeResult(dimension=CD.DATA_SEMANTICS, questions=[
            _q("A", "d?", dim=CD.DATA_SEMANTICS, mat=0.5, ev="d.py")]),
        ProbeResult(dimension=CD.TECHNICAL_CONTEXT, questions=[
            _q("Z", "t?", dim=CD.TECHNICAL_CONTEXT, mat=0.5, ev="t.py")]),
    ]
    out = _merge(_route(), probes)
    assert [q.id for q in out.open_questions] == ["Z", "A"]


def test_id_is_the_final_tiebreak_when_materiality_and_dimension_tie():
    probes = [
        ProbeResult(dimension=CD.DATA_SEMANTICS, questions=[
            _q("Z", "z?", dim=CD.DATA_SEMANTICS, mat=0.5, ev="z.py"),
            _q("A", "a?", dim=CD.DATA_SEMANTICS, mat=0.5, ev="a.py")]),
    ]
    out = _merge(_route(), probes)
    assert [q.id for q in out.open_questions] == ["A", "Z"]


def test_a_dimensionless_question_sorts_after_a_dimensioned_one_at_equal_materiality():
    # Only a supervisor question can reach merge with dimension=None: every
    # probe question gets its probe's dimension stamped on unconditionally.
    sup = _q("S1", "sup?", dim=None, mat=0.5, asked_by="supervisor")
    probe = ProbeResult(dimension=CD.INTERFACE_SPEC, questions=[
        _q("P1", "probe?", dim=CD.INTERFACE_SPEC, mat=0.5, ev="a.py")])
    out = _merge(_route(sup), [probe])
    assert [q.id for q in out.open_questions] == ["P1", "S1"]


def test_the_cap_truncates_and_the_remainder_is_recorded_as_dropped():
    probe = ProbeResult(dimension=CD.INTERFACE_SPEC, questions=[
        _q(f"P{i}", f"q{i}?", dim=CD.INTERFACE_SPEC, mat=1.0 - i / 10,
           ev="a.py") for i in range(8)])
    out = _merge(_route(), [probe], cap=3)
    assert [q.id for q in out.open_questions] == ["P0", "P1", "P2"]
    assert [q.id for q in out.dropped] == ["P3", "P4", "P5", "P6", "P7"]


def test_nothing_is_dropped_when_the_batch_fits():
    probe = ProbeResult(dimension=CD.INTERFACE_SPEC, questions=[
        _q("P1", dim=CD.INTERFACE_SPEC, mat=0.5, ev="a.py")])
    assert _merge(_route(), [probe], cap=5).dropped == []


def test_duplicate_questions_collapse_keeping_the_higher_materiality():
    probes = [
        ProbeResult(dimension=CD.INTERFACE_SPEC, questions=[
            _q("P1", "Does it cascade?", dim=CD.INTERFACE_SPEC, mat=0.4,
               ev="a.py")]),
        ProbeResult(dimension=CD.DATA_SEMANTICS, questions=[
            _q("P2", "  does it CASCADE?  ", dim=CD.DATA_SEMANTICS, mat=0.8,
               ev="b.py")]),
    ]
    out = _merge(_route(), probes)
    assert len(out.open_questions) == 1
    assert out.open_questions[0].id == "P2"
    assert out.dropped == [], "a dedup is not a cap drop"


def test_a_grounded_question_without_evidence_is_discarded():
    # Spec §13: a question about code that cannot point at the code is
    # speculation and never reaches a human.
    probe = ProbeResult(dimension=CD.INTERFACE_SPEC, questions=[
        _q("P1", dim=CD.INTERFACE_SPEC, mat=0.9, ev=None)])
    out = _merge(_route(), [probe])
    assert out.open_questions == []
    assert out.dropped == [], "speculation is discarded, not recorded as cut"


def test_an_ungrounded_dimension_needs_no_evidence():
    probe = ProbeResult(dimension=CD.INTERFACE_SPEC, questions=[
        _q("P1", dim=CD.INTERFACE_SPEC, mat=0.9, ev=None)])
    out = _merge(_route(), [probe], grounded=frozenset())
    assert [q.id for q in out.open_questions] == ["P1"]


def test_a_supervisor_question_never_needs_evidence():
    sup = _q("S1", dim=CD.FUNCTIONAL_INTENT, mat=0.9, asked_by="supervisor",
             ev=None)
    assert [q.id for q in _merge(_route(sup), []).open_questions] == ["S1"]


def test_a_probe_dimension_is_recorded_even_when_it_abstained():
    # Abstaining and failing must be distinguishable: an abstention is
    # present in dimensions_probed with no questions; a dead probe is absent.
    out = _merge(_route(), [ProbeResult(dimension=CD.DATA_SEMANTICS,
                                        questions=[])])
    assert out.dimensions_probed == [CD.DATA_SEMANTICS]
    assert out.open_questions == []


def test_dimensions_probed_is_in_canonical_order():
    probes = [ProbeResult(dimension=CD.DATA_SEMANTICS, questions=[]),
              ProbeResult(dimension=CD.TECHNICAL_CONTEXT, questions=[])]
    out = _merge(_route(), probes)
    assert out.dimensions_probed == [CD.TECHNICAL_CONTEXT, CD.DATA_SEMANTICS]


def test_question_ids_are_unique_after_merge():
    probes = [
        ProbeResult(dimension=CD.INTERFACE_SPEC, questions=[
            _q("Q1", "a?", dim=CD.INTERFACE_SPEC, mat=0.9, ev="a.py")]),
        ProbeResult(dimension=CD.DATA_SEMANTICS, questions=[
            _q("Q1", "b?", dim=CD.DATA_SEMANTICS, mat=0.8, ev="b.py")]),
    ]
    out = _merge(_route(), probes)
    ids = [q.id for q in out.open_questions]
    assert len(ids) == len(set(ids)), "collided ids break answer_question"
