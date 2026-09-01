"""Fan-out wiring: a dead probe degrades ALONE.

run_or_degrade exists because a timeout, a lost worker or an exhausted retry
happens OUTSIDE the activity, where its own try/except cannot keep it. A
clarifier that cannot ask about data semantics is degraded, not broken."""

import ast
import json
from dataclasses import dataclass

import pytest
from test_factory_purity import FEATURE_PY, _load_class, _methods

from sdlc.clarify.models import ClarifyRoute, ProbeResult
from sdlc.models import ClarificationDimension as CD
from sdlc.models import ClarifiedRequirements, OpenQuestion, ProjectMode
from sdlc.workflows.feature import (
    _clarify_fanout,
    _probe_results_from,
    _requirements_for_downstream,
)

C3, C4, C6 = (CD.TECHNICAL_CONTEXT, CD.INTERFACE_SPEC, CD.DATA_SEMANTICS)


def _ok(dim):
    return ProbeResult(
        dimension=dim,
        questions=[
            OpenQuestion(
                id=f"{dim.value}-1",
                question="q?",
                why_it_matters="w",
                dimension=dim,
                materiality=0.5,
                evidence="a.py",
            )
        ],
    )


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


# ---------------------------------------------------------------------
# The orchestration itself, driven with a fake egress: no Temporal, no
# network. This is what makes every call signature inside _clarify_fanout
# executable -- a kwarg rename in probe_prompt or merge_clarification must
# fail here rather than ship green.
# ---------------------------------------------------------------------


@dataclass
class _Run:
    """The .output-carrying shape _run_role returns (an AgentRunResult)."""

    output: object


class _Egress:
    """Stands in for the bound self._run_role. Records every (agent, prompt)
    it is handed so the test can count and inspect the calls."""

    def __init__(self, route, probes):
        self._route, self._probes = route, probes
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, agent, prompt):
        self.calls.append((agent, prompt))
        if agent == "route":
            return _Run(self._route)
        answer = self._probes.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return _Run(answer)

    @property
    def probe_prompts(self) -> list[str]:
        return [p for a, p in self.calls if a == "probe"]


def _route(dims, questions=()) -> ClarifyRoute:
    return ClarifyRoute(
        summary="a summary",
        functional_requirements=["fr1"],
        non_functional_requirements=["nfr1"],
        out_of_scope=["oos1"],
        questions=list(questions),
        live_dimensions=list(dims),
    )


async def _fanout(egress, dims, *, mode=ProjectMode.BROWNFIELD, cap=5):
    return await _clarify_fanout(
        egress,
        route_agent="route",
        probe_agent="probe",
        route_prompt="ROUTE PROMPT",
        idea_json='{"title": "x"}',
        grounding="CodebaseMap at commit abc\n- src/a.py",
        mode=mode,
        cap=cap,
    )


@pytest.mark.asyncio
async def test_the_route_runs_first_and_one_probe_runs_per_live_dimension():
    eg = _Egress(_route([C3, C4]), [_ok(C3), _ok(C4)])
    out = await _fanout(eg, [C3, C4])
    assert eg.calls[0][0] == "route"
    assert eg.calls[0][1] == "ROUTE PROMPT"
    assert len(eg.probe_prompts) == 2
    assert sorted(out.dimensions_probed, key=lambda d: d.value) == sorted(
        [C3, C4], key=lambda d: d.value
    )


@pytest.mark.asyncio
async def test_the_route_prompt_carries_no_codebase_content():
    """ROUTE_SCOPE tells the supervisor it cannot read the codebase. Handing
    it one anyway contradicts its own instructions; the map belongs to the
    probes, which are the ones told to cite it."""
    eg = _Egress(_route([C4]), [_ok(C4)])
    await _fanout(eg, [C4])
    assert eg.calls[0][1] == "ROUTE PROMPT"
    assert "CodebaseMap" not in eg.calls[0][1]


@pytest.mark.asyncio
async def test_every_probe_prompt_carries_the_grounding_it_must_cite():
    eg = _Egress(_route([C3, C4]), [_ok(C3), _ok(C4)])
    await _fanout(eg, [C3, C4])
    assert all("CodebaseMap at commit abc" in p for p in eg.probe_prompts)
    # ...and the supervisor's body, which they are told not to re-ask.
    assert all("a summary" in p for p in eg.probe_prompts)


@pytest.mark.asyncio
async def test_no_live_dimensions_means_no_probe_calls_at_all():
    """An empty live_dimensions list is a correct and common answer; it must
    cost zero probe calls, not four."""
    eg = _Egress(_route([]), [])
    out = await _fanout(eg, [])
    assert eg.probe_prompts == []
    assert out.dimensions_probed == []


@pytest.mark.asyncio
async def test_a_dead_probe_drops_only_itself_and_the_run_still_merges():
    eg = _Egress(_route([C3, C4]), [RuntimeError("worker died"), _ok(C4)])
    out = await _fanout(eg, [C3, C4])
    assert out.dimensions_probed == [C4]
    assert [q.dimension for q in out.open_questions] == [C4]


@pytest.mark.asyncio
async def test_the_merged_result_carries_the_supervisors_body():
    eg = _Egress(
        _route(
            [C4],
            questions=[
                OpenQuestion(
                    id="c1-1",
                    question="what changes?",
                    why_it_matters="w",
                    dimension=CD.FUNCTIONAL_INTENT,
                    materiality=0.9,
                )
            ],
        ),
        [_ok(C4)],
    )
    out = await _fanout(eg, [C4])
    assert isinstance(out, ClarifiedRequirements)
    assert out.summary == "a summary"
    assert out.functional_requirements == ["fr1"]
    assert out.non_functional_requirements == ["nfr1"]
    assert out.out_of_scope == ["oos1"]
    # The supervisor's C1 question outranks the probe's 0.5 and both fit.
    assert [q.id for q in out.open_questions] == ["c1-1", "C4-1"]


@pytest.mark.asyncio
async def test_greenfield_never_dispatches_a_map_grounded_probe():
    """live_dimensions narrows the supervisor's request by mode in code, so
    a model asking for C3/C5 on a greenfield project cannot spend the call."""
    eg = _Egress(_route([C3, C4]), [_ok(C4)])
    out = await _fanout(eg, [C3, C4], mode=ProjectMode.GREENFIELD)
    assert len(eg.probe_prompts) == 1
    assert out.dimensions_probed == [C4]


@pytest.mark.asyncio
async def test_the_cap_is_honoured_and_the_overflow_is_recorded_as_dropped():
    probe = ProbeResult(
        dimension=C4,
        questions=[
            OpenQuestion(
                id=f"C4-{i}",
                question=f"q{i}?",
                why_it_matters="w",
                dimension=C4,
                materiality=0.9 - i / 100,
                evidence="a.py",
            )
            for i in range(4)
        ],
    )
    eg = _Egress(_route([C4]), [probe])
    out = await _fanout(eg, [C4], cap=2)
    assert len(out.open_questions) == 2
    assert len(out.dropped) == 2


# ---------------------------------------------------------------------
# What crosses the stage boundary. Spec §2's scope guard is "no change to
# any downstream role", and §9's cap only protects the pipeline if the
# capped-out questions stay inside the stage. `dropped` carries every cut
# question WITH its why_it_matters, suggested_answer and evidence, and it
# is unbounded -- merge keeps the entire remainder past the cap. Feeding it
# to the architect would hand the architect the uncapped set.
# ---------------------------------------------------------------------


def _reqs(**kw) -> ClarifiedRequirements:
    base = dict(
        summary="s",
        functional_requirements=["fr"],
        non_functional_requirements=["nfr"],
        out_of_scope=["oos"],
        open_questions=[],
    )
    return ClarifiedRequirements(**(base | kw))


def _cut(qid: str) -> OpenQuestion:
    return OpenQuestion(
        id=qid,
        question=f"{qid} SENTINEL-QUESTION?",
        why_it_matters="SENTINEL-WHY",
        suggested_answer="SENTINEL-ANSWER",
        dimension=C6,
        materiality=0.4,
        evidence="SENTINEL-EVIDENCE.py",
    )


def test_the_downstream_view_omits_every_dropped_question():
    reqs = _reqs(open_questions=[_cut("kept")], dropped=[_cut("cut1"), _cut("cut2")])
    view = _requirements_for_downstream(reqs)
    assert "kept" in view
    for lost in ("cut1", "cut2"):
        assert lost not in view
    # ...and nothing a dropped question carried leaks by another route.
    assert view.count("SENTINEL-EVIDENCE.py") == 1
    assert "dropped" not in json.loads(view)


def test_the_downstream_view_omits_the_stage_telemetry():
    """dimensions_probed records which probes ran. That is a measurement of
    the clarify stage, not a fact about the requirement."""
    view = json.loads(_requirements_for_downstream(_reqs(dimensions_probed=[C3, C4, C6])))
    assert "dimensions_probed" not in view


def test_the_downstream_view_keeps_the_requirement_itself():
    reqs = _reqs(open_questions=[_cut("q1")], dropped=[_cut("cut")])
    view = json.loads(_requirements_for_downstream(reqs))
    assert view["summary"] == "s"
    assert view["functional_requirements"] == ["fr"]
    assert view["non_functional_requirements"] == ["nfr"]
    assert view["out_of_scope"] == ["oos"]
    assert [q["id"] for q in view["open_questions"]] == ["q1"]


def test_the_flag_off_downstream_view_has_the_pre_e85_envelope():
    """With the flag off both artifact-level E-85 fields are EMPTY, but an
    empty list still serializes -- and pre-E-85 neither key existed at all.
    Excluding them restores the exact pre-E-85 envelope.

    (The per-question E-85 fields still serialize as nulls; that is a
    separate, bounded, contentless addition and is deliberately left as it
    shipped -- see the next test, which pins it so it stays deliberate.)"""
    view = json.loads(_requirements_for_downstream(_reqs()))
    assert list(view) == [
        "summary",
        "functional_requirements",
        "non_functional_requirements",
        "out_of_scope",
        "open_questions",
        "spec_ref",
    ]


def test_the_per_question_e85_fields_are_null_not_absent_with_the_flag_off():
    """Documented, not fixed. `dimension`/`asked_by`/`materiality`/
    `evidence` are additive with None defaults, so a flag-off question
    carries four nulls the architect did not see pre-E-85. They are
    contentless and bounded -- unlike `dropped`, they cannot defeat the cap
    or grow without limit -- so they stay. This test exists so that stops
    being an accident."""
    q = json.loads(_requirements_for_downstream(_reqs(open_questions=[_cut("q1")])))[
        "open_questions"
    ][0]
    assert set(q) >= {"dimension", "asked_by", "materiality", "evidence"}


def test_dropped_still_survives_on_the_artifact_itself():
    """The exclusion is a VIEW. `dropped` is the benchmark's record of
    "material question that was never asked" (§5) and must not be deleted
    from the artifact that is persisted, judged and published."""
    reqs = _reqs(dropped=[_cut("cut")], dimensions_probed=[C6])
    full = json.loads(reqs.model_dump_json())
    assert [q["id"] for q in full["dropped"]] == ["cut"]
    assert full["dimensions_probed"] == [C6.value]


def test_the_architect_reads_the_downstream_view_not_the_raw_artifact():
    """AST, because the leak was a `reqs.model_dump_json()` in the
    architect's prompt AND in its cache key. Nothing else in the suite
    inspects those two expressions."""
    tree = ast.parse(FEATURE_PY.read_text(encoding="utf-8"), filename=str(FEATURE_PY))
    src = ast.unparse(_methods(_load_class(tree, "FeatureWorkflow"))["_pipeline"])
    assert "reqs_for_architect = _requirements_for_downstream(reqs)" in src
    # the prompt...
    assert r"f'mode={idea.mode.value}\n{reqs_for_architect}'" in src
    # ...and the memo key, which must key on exactly what it prompted with.
    assert "cache_key = reqs_for_architect +" in src
    # The clarify stage's own uses still read the FULL artifact: `dropped`
    # is the measurement record and must reach disk and the board.
    assert "self._judge(cfg, reqs.model_dump_json(), 'clarifier'" in src
    assert "self._board_publish(cfg, 'requirements', reqs.model_dump_json())" in src
