"""The sub-question prefix must be byte-identical across a burst and long
enough to cache. Under ~512 tokens a prefix is silently NOT cached -- no
error, the counter just stays at zero -- so this is guarded by a test rather
than a comment."""

from sdlc.stages.research.prompts import (
    PLAN_SYSTEM,
    SUB_QUESTION_PREFIX,
    SYNTHESIS_SYSTEM,
    sub_question_prompt,
)

# ~4 chars per token is the standard rough conversion. 512 tokens is the
# documented cache floor; 2400 chars gives headroom without being precious.
MIN_CACHEABLE_CHARS = 2400


def test_prefix_is_long_enough_to_be_cacheable():
    assert len(SUB_QUESTION_PREFIX) >= MIN_CACHEABLE_CHARS, (
        "prefix is below the cache floor -- it will silently not be cached "
        "and every parallel sub-question pays full input price"
    )


def test_prefix_is_byte_identical_across_different_questions():
    a = sub_question_prompt("What is the current EU AI Act timeline?")
    b = sub_question_prompt("How many US states have privacy statutes?")
    assert a.startswith(SUB_QUESTION_PREFIX)
    assert b.startswith(SUB_QUESTION_PREFIX)


def test_the_question_lands_after_the_prefix_never_inside_it():
    q = "UNIQUE-MARKER-9f3a"
    assert q not in SUB_QUESTION_PREFIX
    assert q in sub_question_prompt(q)


def test_plan_and_synthesis_prompts_are_non_empty():
    assert len(PLAN_SYSTEM) > 200
    assert len(SYNTHESIS_SYSTEM) > 200
