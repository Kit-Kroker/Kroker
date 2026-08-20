"""Fan-out wiring: a dead probe degrades ALONE.

run_or_degrade exists because a timeout, a lost worker or an exhausted retry
happens OUTSIDE the activity, where its own try/except cannot keep it. A
clarifier that cannot ask about data semantics is degraded, not broken."""
from dataclasses import dataclass

import pytest

from sdlc.clarify.models import ClarifyRoute, ProbeResult
from sdlc.models import ClarificationDimension as CD
from sdlc.models import ClarifiedRequirements, OpenQuestion, ProjectMode
from sdlc.workflows.feature import _clarify_fanout, _probe_results_from

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
    return ClarifyRoute(summary="a summary", functional_requirements=["fr1"],
                        non_functional_requirements=["nfr1"],
                        out_of_scope=["oos1"], questions=list(questions),
                        live_dimensions=list(dims))


async def _fanout(egress, dims, *, mode=ProjectMode.BROWNFIELD, cap=5):
    return await _clarify_fanout(
        egress, route_agent="route", probe_agent="probe",
        route_prompt="ROUTE PROMPT", idea_json='{"title": "x"}',
        grounding="CodebaseMap at commit abc\n- src/a.py", mode=mode, cap=cap)


@pytest.mark.asyncio
async def test_the_route_runs_first_and_one_probe_runs_per_live_dimension():
    eg = _Egress(_route([C3, C4]), [_ok(C3), _ok(C4)])
    out = await _fanout(eg, [C3, C4])
    assert eg.calls[0][0] == "route"
    assert eg.calls[0][1] == "ROUTE PROMPT"
    assert len(eg.probe_prompts) == 2
    assert sorted(out.dimensions_probed, key=lambda d: d.value) == \
        sorted([C3, C4], key=lambda d: d.value)


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
    eg = _Egress(_route([C4], questions=[
        OpenQuestion(id="c1-1", question="what changes?", why_it_matters="w",
                     dimension=CD.FUNCTIONAL_INTENT, materiality=0.9)]),
        [_ok(C4)])
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
    probe = ProbeResult(dimension=C4, questions=[
        OpenQuestion(id=f"C4-{i}", question=f"q{i}?", why_it_matters="w",
                     dimension=C4, materiality=0.9 - i / 100,
                     evidence="a.py") for i in range(4)])
    eg = _Egress(_route([C4]), [probe])
    out = await _fanout(eg, [C4], cap=2)
    assert len(out.open_questions) == 2
    assert len(out.dropped) == 2
