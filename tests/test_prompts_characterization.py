"""Characterization: prompts.py must reproduce feature.py's inline
expressions byte-for-byte. Expected values are transcribed from the
current source, NOT re-derived. See feature.py:1893, :2040, :1403,
:1414, :2192, :2360."""

from __future__ import annotations

from sdlc.prompts import (
    analyst_prompt,
    clarify_prompt,
    merge_verdict_prompt,
    planner_prompt,
    qa_prompt,
    reviewer_prompt,
)

IDEA = '{"title":"T","description":"D"}'
ARCH = '{"stack":"python"}'


def test_clarify_no_memory():
    # feature.py:1893 -- idea.model_dump_json() + ("" when no items)
    assert clarify_prompt(IDEA, []) == IDEA


def test_clarify_with_memory():
    assert clarify_prompt(IDEA, ["a", "b"]) == (IDEA + "\nRelevant memory:\n- a\n- b")


def test_planner_no_memory_no_guidance():
    assert planner_prompt(ARCH, [], None) == ARCH


def test_planner_memory_and_guidance():
    assert planner_prompt(ARCH, ["m1"], "fix it") == (
        ARCH + "\nRelevant memory:\n- m1" + "\nRevision guidance from reviewer:\nfix it"
    )


def test_planner_guidance_empty_string_is_omitted():
    # feature.py uses `if guidance else ""` -- "" is falsy, so no block.
    assert planner_prompt(ARCH, [], "") == ARCH


def test_qa_includes_diff_stat():
    assert qa_prompt(["a1", "a2"], '{"passed":true}', "STAT", "PATCH") == (
        "Frozen contract assertions:\n- a1\n- a2"
        + '\nTest results: {"passed":true}'
        + "\nDiff stat:\nSTAT"
        + "\nDiff:\nPATCH"
    )


def test_reviewer_omits_diff_stat():
    # feature.py:1417 -- reviewer gets Diff: but NOT Diff stat:. Asymmetry
    # is preserved deliberately; see design doc section 4.1.
    assert reviewer_prompt(["a1"], '{"passed":true}', "PATCH") == (
        "Frozen contract assertions:\n- a1" + '\nTest results: {"passed":true}' + "\nDiff:\nPATCH"
    )


def test_analyst():
    assert analyst_prompt("CRIT", "QA", "STAT", "PATCH") == (
        "Acceptance criteria (task_id in brackets):\nCRIT"
        + "\nAggregate test output:\nQA"
        + "\nIntegration diff stat:\nSTAT"
        + "\nIntegration diff:\nPATCH"
    )


def test_merge_verdict_preserves_em_dash_and_repr():
    # feature.py:2361-2362 -- f-string interpolates the LIST, so Python's
    # repr of list-of-dicts is what reaches the model. Preserve exactly.
    assert merge_verdict_prompt([{"id": 1}]) == (
        "Advisory only — the deterministic gate already passed. Task results: [{'id': 1}]"
    )


def test_empty_assertions_still_emits_header():
    # "\n- ".join([]) == "" -- the header survives with a trailing "- ".
    assert qa_prompt([], "{}", "S", "P").startswith("Frozen contract assertions:\n- \n")
