"""The benchmark judge's model must run with SDK retries off
(sbatch-2026-10-19 T1; task .workspace/tasks/2026-10-02-benchmark-judge-sdk-retry-stacking.md).

``_run_judge_agent`` resolves a string model through ``resolve_model``,
whose contract keeps SDK retries at the provider default (``model_ids.py``
C4) — so an openai-style client retries each judge-loop attempt itself and
the two retry layers stack: today one judge call against an always-429
provider costs ``len(_JUDGE_RETRY_DELAYS)+1`` loop attempts x 3 SDK
requests = 12 HTTP requests. Same defect 004 removed for every proposer
(FR-007..FR-009); the judge was ruled out of 004's scope (Q1: not a
proposer role) and lands here.

Two axes, both RED on main:

1. coverage — the judge site must construct its string model through the
   shared ``single_retry_layer`` factory it imports (the
   ``_require_stage_factory`` pattern of test_single_retry_coverage.py,
   004 T013), with eager resolution before Agent construction preserved:
   tests/test_benchmark_judge.py:480-534 pin the Agent receiving a
   resolved model, and tests/test_model_construction_sites.py requires
   the ``resolve_model`` token in judge.py source — neither is weakened
   by this file;
2. bound — one judge call against the always-429 counting stub
   (``_http_stub.py``) must cost at most ``len(_JUDGE_RETRY_DELAYS)+1``
   HTTP requests: the judge loop is the retry layer, the provider SDK
   must add none beneath it. No Temporal needed — ``_run_judge_agent``
   is sync and in-process, so this rides the fast tier.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from sdlc.benchmarks import judge as judge_mod

from ._http_stub import ProviderStub

# --- axis 1: the judge site builds through the single-retry factory ---------

# The Agent-recording shape of tests/test_benchmark_judge.py: capture the
# model the site hands Agent, serve a canned output, touch no network.
_BUILT_MODELS: list[object] = []


class _RecordingAgent:
    def __init__(self, model, **kwargs):
        self.model = model
        _BUILT_MODELS.append(model)

    def run_sync(self, prompt):
        return SimpleNamespace(output="ok")


def _require_judge_factory(monkeypatch):
    """The judge module must build its string models through the shared
    single_retry_layer factory (T1). Returns (wrapped_factory, calls)."""
    factory = getattr(judge_mod, "single_retry_layer", None)
    assert factory is not None, (
        "benchmarks/judge.py does not import single_retry_layer — its string "
        "models resolve through resolve_model, which leaves the provider "
        "SDK's own retry layer stacked under the judge loop's backoff "
        "(task 2026-10-02, FR-007)"
    )
    calls: list[int] = []

    def _recording() -> object:
        calls.append(1)
        return factory()

    monkeypatch.setattr(judge_mod, "single_retry_layer", _recording)
    return _recording, calls


def test_run_judge_agent_builds_a_string_model_through_single_retry(monkeypatch):
    """A string judge model must resolve through the single-retry capability
    factory — SDK retries off — and the Agent must still receive a resolved
    model instance, never the bare string (eager resolution survives the
    fix)."""
    _, calls = _require_judge_factory(monkeypatch)
    _BUILT_MODELS.clear()
    monkeypatch.setattr(judge_mod, "Agent", _RecordingAgent)
    # The recording wrapper delegates to the real factory, which builds the
    # openai provider for real: it wants a key at construction, never on the
    # wire (the conftest dummy pattern).
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    raw = judge_mod._run_judge_agent("openai:gpt-5.2", "sys", "user prompt")

    assert raw == "ok", "the judge site must still return the agent output"
    assert calls, (
        "the judge site constructed its model without the single-retry "
        "factory — the provider SDK keeps its own retry layer stacked under "
        "the judge loop (T1, FR-007)"
    )
    built = _BUILT_MODELS[-1]
    assert built is not None and not isinstance(built, str), (
        f"the judge site built Agent from the bare string {built!r} — eager "
        "resolution before Agent construction must survive the fix "
        "(tests/test_benchmark_judge.py:480-534 pin it)"
    )


# --- axis 2: one judge call is bounded by its own attempt budget ------------


def test_judge_call_always_429_is_bounded_by_the_judge_loop_budget(monkeypatch):
    """One judge call against an always-429 provider must exhaust the judge
    loop at <= len(_JUDGE_RETRY_DELAYS)+1 HTTP requests: the loop's backoff
    is the only retry layer here (the Temporal activity's attempt budget
    multiplies on top of it), so the provider SDK must add none beneath it.
    RED on main: resolve_model keeps the openai SDK default max_retries=2,
    so the stub sees 4 loop attempts x 3 SDK requests = 12."""
    delays = (0.0, 0.0, 0.0)  # instant backoff: every loop attempt still runs
    import sdlc.agents.retry_policy as retry_policy_mod

    monkeypatch.setattr(retry_policy_mod, "DEFAULT_LADDER", delays)
    monkeypatch.setattr(judge_mod, "_JUDGE_RETRY_DELAYS", delays)
    # The openai client is built inside the call and reads both at
    # construction; a dummy key never reaches the stub's wire.
    monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

    with ProviderStub(mode="always_429") as stub:
        monkeypatch.setenv("OPENAI_BASE_URL", stub.base_url)
        with pytest.raises(ModelHTTPError) as excinfo:
            judge_mod._run_judge_agent("openai:gpt-5.2", "sys", "user prompt")

    # 429 exhaustion, not an incidental failure (e.g. auth or config errors
    # would never reach the wire): the raised exception carries the status
    # the loop spent its budget on.
    assert judge_mod._status_of(excinfo.value) == 429, (
        f"expected the 429 exhaustion to propagate out of the judge loop, "
        f"got {type(excinfo.value).__name__}: {excinfo.value}"
    )
    budget = len(delays) + 1
    assert stub.count <= budget, (
        f"always-429 stub saw {stub.count} HTTP requests for one judge call; "
        f"the judge loop's own budget is {budget} attempts and the provider "
        f"SDK must add none beneath it (T1, FR-008)"
    )
