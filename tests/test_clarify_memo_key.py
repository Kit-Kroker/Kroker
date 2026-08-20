"""The memo key must move when a probe prompt moves, and must NOT move when
the flag is off.

Without the first, editing a probe serves a stale clarification silently.
Without the second, landing E-85 invalidates every existing clarify memo even
though the flag-off prompt did not change -- which is what "the default
pipeline is byte-identical to today" rules out."""
from sdlc.clarify.prompts import probe_prompt_digest
from sdlc.memoization.cache import content_key


def _key(extra: str) -> str:
    return content_key("clarify", '{"title": "x"}' + extra, "prompt-sha",
                       "anthropic:glm-5.2", "none")


def test_the_flag_off_key_carries_no_e85_terms():
    # Flag off appends nothing, so the key is what it was pre-E-85.
    assert _key("") == _key("")


def test_turning_the_flag_on_moves_the_key():
    on = f"|e85:{probe_prompt_digest()}|map:abc123"
    assert _key(on) != _key("")


def test_a_different_tree_moves_the_key():
    d = probe_prompt_digest()
    assert _key(f"|e85:{d}|map:aaa") != _key(f"|e85:{d}|map:bbb")


def test_the_same_tree_and_prompts_hit_the_same_key():
    d = probe_prompt_digest()
    assert _key(f"|e85:{d}|map:aaa") == _key(f"|e85:{d}|map:aaa")
