"""A capped sub-question run reports what it spent (feature 008, plan D5).

This module pins the WIRE side of the refusal record: the record the
exhaustion handler will own lives in memory on `ResearchDeps` and must
never change what crosses the activity boundary. An input carrying a
noted refusal serializes to the same bytes as one without it, the
serialized deps keep exactly today's twelve keys, and a fresh round-trip
starts with an empty record -- so no replay, history or wire payload a
run has ever produced sees the record (FR-010, EC9).
"""

import json

import pytest

from sdlc.stages.research.deps import ResearchDeps
from sdlc.stages.research.models import SubQuestion
from sdlc.stages.research.stage import SubQuestionInput


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def _deps() -> ResearchDeps:
    return ResearchDeps(
        run_id="r1", provider="fake", max_searches=5, max_fetches=10, max_cost_usd=1.0
    )


def _inp() -> SubQuestionInput:
    """The plan-D5 input shape: `_inp()` from test_research_subquestion_activity."""
    return SubQuestionInput(
        sub_question=SubQuestion(id="sq-0", question="what is the timeline?"),
        deps=_deps(),
        model="test-model",
        max_requests=40,
        max_run_cost_usd=4.0,
    )


def test_input_json_is_byte_identical_before_and_after_a_refusal():
    inp = _inp()
    before = inp.model_dump_json()
    inp.deps.note_refusal("x")
    assert inp.model_dump_json() == before


def test_deps_json_is_byte_identical_before_and_after_a_refusal():
    d = _deps()
    before = d.model_dump_json()
    d.note_refusal("x")
    assert d.model_dump_json() == before


def test_serialized_deps_keys_stay_exactly_today_twelve_with_a_refusal_noted():
    d = _deps()
    d.note_refusal("sq-0 allowance: search budget exhausted (1 searches)")
    assert sorted(json.loads(d.model_dump_json()).keys()) == [
        "budget",
        "max_cost_usd",
        "max_fetches",
        "max_run_cost_usd",
        "max_searches",
        "memory_backend",
        "memory_bank",
        "memory_base_url",
        "memory_watermark",
        "provider",
        "run_id",
        "scope",
    ]


def test_a_round_trip_starts_with_an_empty_refusal_record():
    d = _deps()
    d.note_refusal("sq-0 allowance: search budget exhausted (1 searches)")
    round_tripped = ResearchDeps.model_validate_json(d.model_dump_json())
    assert round_tripped.refusals == []


def test_a_fresh_deps_has_an_empty_refusal_record():
    assert _deps().refusals == []


def test_note_refusal_appends_in_order():
    d = _deps()
    d.note_refusal("first")
    d.note_refusal("second")
    assert d.refusals == ["first", "second"]


def test_reset_refusals_on_a_copy_leaves_the_source_record_intact():
    # model_copy shares the private list (measured, E4 A4): reset must hand the
    # copy a fresh list, never mutate the source's.
    d = _deps()
    d.note_refusal("first")
    d.note_refusal("second")
    c = d.model_copy(update={"scope": "sq-9"})
    c.reset_refusals()
    assert d.refusals == ["first", "second"]
    assert c.refusals == []
