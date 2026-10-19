"""Chaos/edge companions to test_judge_single_retry.py (sbatch-2026-10-19 T1).

The happy-path file pins the fix's two RED axes: the judge site building
string models through ``single_retry_layer`` (SDK retries off) and the
always-429 request bound. This file pins the seam's EDGES around that fix —
every test here names the production change that would break it:

- a non-transient provider error (400) must raise IMMEDIATELY: neither the
  SDK (never retries a 400) nor the judge loop (``_transient`` says no) may
  engage — exactly one HTTP request, the classification visible on the
  raise;
- a single transient failure must cost exactly TWO HTTP requests served by
  exactly ONE retry layer. On main the SDK's own retry serves request 2;
  after the fix the judge loop must serve it instead — the count stays 2
  either way and moves if the fix wrongly kills the judge loop (1 request
  and a raise) or leaves the layers stacked (3+);
- a Model INSTANCE must bypass the string-resolution path entirely — the
  capability fix is for strings only;
- 429 exhaustion must surface the HTTP status in the raise chain, because
  ``_judge_sync``'s fail-safe converts any exception into ``judge="error"``
  and the detail is the only place the run report learns it was a 429.

All four are pins (green on main where the edge is already held) — their
job is to fail the moment the T1 fix changes one of these edges. Direct
sync calls, no Temporal: fast tier. ``_JUDGE_RETRY_DELAYS`` is monkeypatched
to zero-length sleeps (same attempt COUNT, instant backoff) so the loop's
full budget runs without the 5/30/120s wall clock.
"""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel

from sdlc.benchmarks import judge as judge_mod
from sdlc.benchmarks.judge import _run_judge_agent

from ._http_stub import ProviderStub

# The judge's production provider family (anthropic:), resolved through the
# seam and pointed at the counting stub via the SDK's own base-url env. The
# dummy key satisfies client construction and never reaches the wire. (The
# openai: stack is unusable for success-path tests here: this pydantic-ai
# build's chat-completion processing crashes on the stub's 200 body —
# `_tool_search_output_call_ids` iterates a None `output` — so qa-happy's
# always-429 file can use it but a fail-once test cannot.)
_JUDGE_MODEL = "anthropic:claude-sonnet-5"


def _chain_text(exc: BaseException | None) -> str:
    """The full raise chain as text, each member annotated with the HTTP
    status ``judge_mod._status_of`` extracts from it — so a 429 hidden in a
    cause (ModelHTTPError or raw httpx) still prints."""
    parts: list[str] = []
    seen: set[int] = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        parts.append(f"{type(cur).__name__}[http {judge_mod._status_of(cur)}]: {cur}")
        cur = cur.__cause__ or cur.__context__
    return "\n".join(parts)


def test_always_400_raises_immediately_on_exactly_one_request(monkeypatch):
    """PIN (green on main; must stay green through the fix): a 400 is not
    transient, so the judge loop must not retry it and the SDK never does —
    one HTTP request, then the raise. Breaks if the fix makes any layer
    retry non-transient statuses or if 400 gets misclassified transient
    (then count > 1)."""
    monkeypatch.setattr(judge_mod, "_JUDGE_RETRY_DELAYS", (0.0, 0.0, 0.0))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub-key")
    with ProviderStub(mode="always_400") as stub:
        monkeypatch.setenv("ANTHROPIC_BASE_URL", stub.base_url)
        with pytest.raises(Exception) as excinfo:
            _run_judge_agent(_JUDGE_MODEL, "sys", "user prompt")

    assert stub.count == 1, (
        f"always-400 stub saw {stub.count} HTTP requests; a non-transient "
        f"provider error must raise on the first request — no SDK retry, no "
        f"judge-loop retry"
    )
    # The classification must be visible on the raise itself, not merely
    # absent from the retry set: `_transient` is why the loop did not engage.
    assert not judge_mod._transient(excinfo.value), (
        "a 400 classified transient would retry — the immediate raise is "
        "then an accident, not the contract:\n" + _chain_text(excinfo.value)
    )
    assert "400" in _chain_text(excinfo.value)


def test_fail_once_costs_exactly_two_requests_at_one_retry_layer(monkeypatch):
    """PIN of the post-fix invariant (green on main too — the SDK retry
    serves request 2 today; after the fix the judge loop must): one 429 then
    success is exactly 2 HTTP requests with the output returned. The judge
    loop keeps the full budget live (delays zeroed, not removed). Breaks if
    the fix kills the judge loop (1 request, raise) or leaves the layers
    stacked (3+)."""
    monkeypatch.setattr(judge_mod, "_JUDGE_RETRY_DELAYS", (0.0, 0.0, 0.0))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub-key")
    with ProviderStub(mode="fail_once") as stub:
        monkeypatch.setenv("ANTHROPIC_BASE_URL", stub.base_url)
        out = _run_judge_agent(_JUDGE_MODEL, "sys", "user prompt")

    assert out == "ok"
    assert stub.count == 2, (
        f"fail-once stub saw {stub.count} HTTP requests; one transient "
        f"failure then success must cost exactly 2 — exactly one retry layer "
        f"may serve the second request"
    )


def test_model_instance_bypasses_the_string_resolution_path(monkeypatch):
    """PIN: a Model INSTANCE is served as-is — no string resolution, no
    network, no crash. The single-retry capability path is for strings; a
    fix that routes every model through a resolver trips the bomb and fails
    here."""

    def _bomb(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "model instances must not pass through single_retry_layer — "
            "the capability path is for strings only"
        )

    monkeypatch.setattr(judge_mod, "single_retry_layer", _bomb)
    out = _run_judge_agent(TestModel(custom_output_text="edge-ok"), "sys", "user prompt")
    assert out == "edge-ok"


def test_always_429_exhaustion_surfaces_the_status_in_the_raise_chain(monkeypatch):
    """PIN: after the judge loop exhausts its budget, the raise must carry
    the HTTP status (ModelHTTPError / httpx chain containing 429) — that is
    what ``_judge_sync``'s fail-safe turns into ``judge="error"`` with the
    status in the detail, the run report's only trace of the rate limit.
    Also pins that the loop DID retry (count > 1): a fix that swallows the
    status into a statusless wrapper, or stops classifying 429 as transient,
    fails here."""
    monkeypatch.setattr(judge_mod, "_JUDGE_RETRY_DELAYS", (0.0, 0.0, 0.0))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub-key")
    with ProviderStub(mode="always_429") as stub:
        monkeypatch.setenv("ANTHROPIC_BASE_URL", stub.base_url)
        with pytest.raises(Exception) as excinfo:
            _run_judge_agent(_JUDGE_MODEL, "sys", "user prompt")

    assert stub.count >= 2, (
        f"always-429 stub saw only {stub.count} HTTP request(s); the judge "
        f"loop must retry a transient status before raising — a 429 "
        f"classified non-transient turns rate limits into immediate failures"
    )
    chain = _chain_text(excinfo.value)
    assert "429" in chain, (
        f"the exhaustion raise must surface the HTTP status for the "
        f"_judge_sync fail-safe; chain was:\n{chain}"
    )
