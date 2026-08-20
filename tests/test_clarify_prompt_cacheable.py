"""The probe prefix must be byte-identical across a burst and long enough to
cache. Under ~512 tokens a prefix is silently NOT cached -- no error, the
counter just stays at zero -- so this is a test, not a comment. Modelled on
tests/test_research_prompt_cacheable.py."""
from sdlc.clarify.prompts import (PROBE_PREFIX, PROBE_SYSTEM, ROUTE_SCOPE,
                                  SCOPES, probe_prompt, probe_prompt_digest)
from sdlc.models import ClarificationDimension

# ~4 chars per token; 512 tokens is the documented cache floor. 2400 chars
# gives headroom without being precious. Same constant as research's guard.
MIN_CACHEABLE_CHARS = 2400

C3 = ClarificationDimension.TECHNICAL_CONTEXT
C4 = ClarificationDimension.INTERFACE_SPEC
C6 = ClarificationDimension.DATA_SEMANTICS


def _prompt(dim):
    return probe_prompt(dim, idea_json='{"title": "x"}',
                        requirements_json='{"summary": "s"}',
                        grounding="src/api/routes.py")


def test_prefix_is_long_enough_to_be_cacheable():
    assert len(PROBE_PREFIX) >= MIN_CACHEABLE_CHARS, (
        "prefix is below the cache floor -- it will silently not be cached "
        "and every parallel probe pays full input price")


def test_prefix_is_byte_identical_across_different_dimensions():
    for dim in (C3, C4, C6):
        assert _prompt(dim).startswith(PROBE_PREFIX)


def test_the_scope_lands_after_the_prefix_never_inside_it():
    # Interpolating the dimension into the prefix would break the shared
    # cache entry for every probe in the burst.
    for dim, scope in SCOPES.items():
        assert scope not in PROBE_PREFIX, f"{dim} scope leaked into the prefix"
        assert scope in _prompt(dim)


def test_every_dimension_has_a_scope_block():
    assert set(SCOPES) == set(ClarificationDimension)


def test_the_prefix_licenses_abstention():
    # A probe that cannot abstain manufactures questions (spec §13).
    assert "abstain" in PROBE_PREFIX.lower()


def test_route_scope_and_probe_system_are_non_empty():
    assert len(ROUTE_SCOPE) > 200
    assert len(PROBE_SYSTEM) > 200


def test_the_digest_is_stable_across_calls():
    assert probe_prompt_digest() == probe_prompt_digest()


def test_the_digest_is_a_sha256_hex():
    d = probe_prompt_digest()
    assert len(d) == 64 and all(c in "0123456789abcdef" for c in d)


def test_editing_a_scope_block_moves_the_digest(monkeypatch):
    """The whole point of the digest: edit a probe prompt, invalidate the
    memo. Without this, a probe edit serves a stale clarification silently."""
    before = probe_prompt_digest()
    patched = dict(SCOPES)
    patched[C4] = patched[C4] + "\nAlso consider idempotency.\n"
    monkeypatch.setattr("sdlc.clarify.prompts.SCOPES", patched)
    assert probe_prompt_digest() != before


def test_editing_the_prefix_moves_the_digest(monkeypatch):
    before = probe_prompt_digest()
    monkeypatch.setattr("sdlc.clarify.prompts.PROBE_PREFIX",
                        PROBE_PREFIX + "\nOne more rule.\n")
    assert probe_prompt_digest() != before


def test_swapping_two_scopes_moves_the_digest(monkeypatch):
    """The digest binds each scope to ITS dimension. A digest that hashed
    only the concatenated text would miss this and serve a stale memo after
    a re-attribution."""
    before = probe_prompt_digest()
    patched = dict(SCOPES)
    patched[C3], patched[C6] = patched[C6], patched[C3]
    monkeypatch.setattr("sdlc.clarify.prompts.SCOPES", patched)
    assert probe_prompt_digest() != before
