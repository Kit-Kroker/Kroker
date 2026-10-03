"""007 T002/T004 (qa-chaos, RED): the proposer payload guard's edge cases.

Plan D1/D5 cases 1-7 (T002) against a module that did not exist yet: on the
base tree every case failed on the missing ``sdlc.agents.payload_guard`` --
the stated RED reason. T003 created the module (26a32a2) and cases 1-7 went
green. D5 case 8 (T004, qa-chaos again): coverage and attachment, RED while
the loader, roles.py and the worker do not attach the guard yet.

The guard measures every workflow-scheduled model request in workflow code
and raises the repo's non-retryable failure above the limit BEFORE the
request is sent. Workflow context is simulated on the seam T003's import
style provides (``from temporalio import workflow`` plus attribute calls):
these tests monkeypatch ``in_workflow``/``patched`` on the temporalio.workflow
module object the guard reads them from, which a ``from temporalio.workflow
import in_workflow`` form would bypass. Cases 1-7 attach no durability, so
nothing can schedule an activity -- an over-limit failure can only come from
the guard itself. Case 8(iv) is the one place TemporalDurability appears: a
stub built in the production shape MINUS the guard, appended to the worker
module's own ``ALL_TEMPORAL_AGENTS`` so it passes the boot check's
durability gate and can only fail the guard one.

Edges pinned (spec E1/E2/E4/E7/E9, FR-001/FR-002/FR-003/FR-006/FR-007):
- size measures UTF-8 bytes, not characters, and includes the request
  parameters and the model settings (E2);
- the boundary is inclusive: a payload measuring exactly the limit passes
  (E1), and an under-limit request never consults the patch marker at all
  (E4/R5: under-limit runs stay command-identical);
- replaying a pre-007 history (patched False) steps aside, after consulting
  the marker under its wire id (FR-006);
- outside a workflow the guard is inert even over the limit (E9);
- the failure message carries numbers only and stays under 300 characters --
  a sentinel planted in the payload must not leak into it (E7);
- a history that grows past the limit during a call fails on the request
  that crosses it, and that request is never sent (FR-001);
- each model request of an output-retry loop enters the hook exactly once.

The three module constants are pinned as literals in the first test: the
patch id and the error type are wire names never renamed once shipped
(plan D1) and the 1 MiB limit is the GATE 2 ruling (FR-005) -- every
other test reads them from the module, which alone would not catch a
typo in the constant itself.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import FunctionModel
from temporalio.exceptions import ApplicationError

from sdlc.agents import payload_guard
from sdlc.core.models import RoleConfig

# One constant (FR-005): every assertion that names the limit reads it from
# the module under test, the way the failure message does.
_LIMIT = payload_guard.PROPOSER_PAYLOAD_LIMIT_BYTES
_AGENT_NAME = "chaos_guard_agent"
_SENTINEL = "SENTINEL-LEAK-CANARY-4277"


def _messages(prompt: str) -> list[ModelRequest]:
    return [ModelRequest(parts=[UserPromptPart(content=prompt)])]


def _params(**overrides: object) -> ModelRequestParameters:
    return ModelRequestParameters(**overrides)


class _Ctx:
    """The D1-shaped context stand-in: the message rule reads ctx.agent.name."""

    def __init__(self, name: str) -> None:
        self.agent = SimpleNamespace(name=name)


class _Recorder:
    """Handler double: counts calls, returns one canned response."""

    def __init__(self) -> None:
        self.calls = 0
        self.response = ModelResponse(parts=[TextPart("handler ran")])

    async def __call__(self, request_context: object) -> ModelResponse:
        self.calls += 1
        return self.response


def _run_hook(messages: list[ModelRequest], handler: _Recorder) -> object:
    """Drive one wrap_model_request call with default parameters/settings."""
    guard = payload_guard.payload_guard()
    return asyncio.run(
        guard.wrap_model_request(
            _Ctx(_AGENT_NAME),
            request_context=SimpleNamespace(
                messages=messages,
                model_request_parameters=_params(),
                model_settings=None,
            ),
            handler=handler,
        )
    )


def _seam_workflow(
    monkeypatch: pytest.MonkeyPatch,
    *,
    in_workflow: bool | None = True,
    patched: bool | None = None,
) -> list[str]:
    """Fake the guard's temporalio.workflow seam and record every patched()
    call. ``in_workflow=None`` / ``patched=None`` leave the real function in
    place: the real in_workflow() answers False under pytest, and the real
    patched() RAISES outside a workflow, so a guard that consults the marker
    before the size test, or outside a workflow, fails loudly here instead of
    silently passing. Returns the recording list of patched ids."""
    calls: list[str] = []
    if in_workflow is not None:
        monkeypatch.setattr(payload_guard.workflow, "in_workflow", lambda: in_workflow)
    if patched is not None:

        def _patched(patch_id: str) -> bool:
            calls.append(patch_id)
            return patched

        monkeypatch.setattr(payload_guard.workflow, "patched", _patched)
    return calls


# --- The wire surface: constants as literals (plan D1, FR-005, SC-002) --------


def test_wire_names_and_limit_are_pinned():
    """The wire names ship and are never renamed; the limit is the ruled
    value. Everything else in this module reads the constants -- this is
    the one test that would catch a typo in a constant itself."""
    assert payload_guard.PROPOSER_PAYLOAD_LIMIT_BYTES == 1_048_576
    assert payload_guard.GUARD_PATCH_ID == "007-proposer-payload-guard"
    assert payload_guard.OVERSIZE_ERROR_TYPE == "ProposerPayloadTooLarge"


# --- D5 case 1: payload_size --------------------------------------------------


def test_payload_size_counts_bytes_parameters_and_settings():
    """E2: the measure is UTF-8 bytes (a CJK character is at least three of
    them), the request parameters and the model settings are part of the
    payload, and equal inputs measure equally."""
    cjk = "漢" * 1_000
    assert payload_guard.payload_size(_messages(cjk), _params(), None) >= 3 * len(cjk)

    same = _messages("same payload")
    bare = payload_guard.payload_size(same, _params(), None)
    with_parameters = payload_guard.payload_size(
        same, _params(tool_visibility={"grow": "visible"}), None
    )
    with_settings = payload_guard.payload_size(same, _params(), {"max_tokens": 12345})
    assert with_parameters > bare, "request parameters must be measured"
    assert with_settings > bare, "model settings must be measured"
    assert payload_guard.payload_size(same, _params(), None) == bare


# --- D5 case 2: over the limit, in a workflow, marker present -----------------


def test_over_limit_in_workflow_raises_before_the_handler(monkeypatch):
    """FR-001/FR-003/E7: over the limit and patched, the guard raises a
    non-retryable ApplicationError of its own type instead of calling the
    handler, with a message of numbers only -- the sentinel planted in the
    payload must not leak into it."""
    _seam_workflow(monkeypatch, in_workflow=True, patched=True)
    messages = _messages(_SENTINEL + "x" * (_LIMIT + 2_048))
    expected_size = payload_guard.payload_size(messages, _params(), None)
    assert expected_size > _LIMIT, "fixture: the payload must qualify as over-limit"
    handler = _Recorder()

    with pytest.raises(ApplicationError) as excinfo:
        _run_hook(messages, handler)

    error = excinfo.value
    assert error.non_retryable is True
    assert error.type == payload_guard.OVERSIZE_ERROR_TYPE
    message = error.message
    assert message.startswith(f"agent '{_AGENT_NAME}': proposer payload ")
    assert str(expected_size) in message
    assert str(_LIMIT) in message
    assert len(message) < 300
    assert _SENTINEL not in message
    assert handler.calls == 0, "an over-limit request must never reach the model"


# --- D5 case 3: the boundary is inclusive (E1) --------------------------------


def test_exactly_at_and_under_the_limit_reach_the_handler(monkeypatch):
    """E1/FR-007: the limit is inclusive -- a payload measuring exactly the
    limit passes, as does a small one; the handler is called once and its
    result is returned untouched."""
    _seam_workflow(monkeypatch, in_workflow=True, patched=True)

    # Pad an ASCII prompt so the measured size lands on the limit exactly:
    # every extra ASCII character is exactly one serialized byte.
    base = payload_guard.payload_size(_messages("x"), _params(), None)
    exact_messages = _messages("x" * (1 + _LIMIT - base))
    measured = payload_guard.payload_size(exact_messages, _params(), None)
    assert measured == _LIMIT, f"fixture: padding landed on {measured}, not the limit"

    at_limit = _Recorder()
    result = _run_hook(exact_messages, at_limit)
    assert at_limit.calls == 1
    assert result is at_limit.response

    under = _Recorder()
    result_under = _run_hook(_messages("small"), under)
    assert under.calls == 1
    assert result_under is under.response


# --- D5 case 4: inert outside a workflow (E9) ----------------------------------


def test_outside_a_workflow_the_guard_is_inert_even_over_the_limit(monkeypatch):
    """E9: the real workflow.in_workflow() answers False under pytest. Only
    patched is faked here: a guard that consults the marker before asking
    whether it is even in a workflow fails this test by the recording list
    staying non-empty -- or by the real patched() raising."""
    patch_ids = _seam_workflow(monkeypatch, in_workflow=None, patched=True)
    handler = _Recorder()

    result = _run_hook(_messages("x" * (_LIMIT + 2_048)), handler)

    assert handler.calls == 1
    assert result is handler.response
    assert patch_ids == []


# --- D5 case 5: replay without the marker; under-limit never asks (E4/R5) ------


def test_replay_without_marker_passes_and_under_limit_never_consults_it(monkeypatch):
    """FR-006/E4/R5: over the limit but patched False (replaying a pre-007
    history) the guard steps aside, after consulting the marker under its
    wire id; under the limit the marker is never consulted at all, so an
    under-limit run schedules exactly the commands it always did."""
    marker_ids = _seam_workflow(monkeypatch, in_workflow=True, patched=False)
    replay_handler = _Recorder()

    result = _run_hook(_messages("x" * (_LIMIT + 2_048)), replay_handler)

    assert replay_handler.calls == 1
    assert result is replay_handler.response
    assert marker_ids == [payload_guard.GUARD_PATCH_ID]

    # Under the limit patched is faked to RECORD; its value is irrelevant
    # because it must simply never be asked.
    under_ids = _seam_workflow(monkeypatch, in_workflow=True, patched=True)
    handler = _Recorder()
    _run_hook(_messages("small"), handler)
    assert handler.calls == 1
    assert under_ids == []


# --- D5 case 6: a history that grows past the limit mid-call (US2) -------------


def test_growth_during_a_call_fails_the_crossing_request_unsent(monkeypatch):
    """FR-001/FR-002: a tool return that pushes the history past the limit
    fails the NEXT request -- the ApplicationError surfaces from agent.run,
    and the model-function count proves the over-limit request was never
    made."""
    _seam_workflow(monkeypatch, in_workflow=True, patched=True)
    model_calls = 0

    async def _model(messages: object, info: object) -> ModelResponse:
        nonlocal model_calls
        model_calls += 1
        return ModelResponse(parts=[ToolCallPart(tool_name="grow", args={})])

    def grow() -> str:
        return "P" * (_LIMIT + 2_048)

    agent = Agent(
        FunctionModel(_model),
        name=_AGENT_NAME,
        tools=[grow],
        capabilities=[payload_guard.payload_guard()],
    )

    with pytest.raises(ApplicationError) as excinfo:
        asyncio.run(agent.run("start"))

    assert excinfo.value.type == payload_guard.OVERSIZE_ERROR_TYPE
    assert excinfo.value.non_retryable is True
    assert model_calls == 1, "the over-limit request must never reach the model"


# --- D5 case 7: one hook entry per model request across output retries ---------


def test_output_retry_enters_the_hook_once_per_request(monkeypatch):
    """FR-002: an output whose first answer is invalid drives a second model
    request, and the hook is entered exactly once for each -- counted through
    a subclass, so the entry count is the request count. The first answer is
    bare text (no output tool call -- invalid for a typed output); the retry
    answers through the final_result output tool (its single argument is
    named 'response' for a plain output type)."""
    _seam_workflow(monkeypatch, in_workflow=True, patched=True)
    answers = iter(
        [
            [TextPart("not an integer")],
            [ToolCallPart(tool_name="final_result", args={"response": 7})],
        ]
    )

    async def _model(messages: object, info: object) -> ModelResponse:
        return ModelResponse(parts=next(answers))

    entries: list[int] = []

    class _CountingGuard(payload_guard.ProposerPayloadGuard):
        async def wrap_model_request(self, ctx, *, request_context, handler):
            entries.append(len(request_context.messages))
            return await super().wrap_model_request(
                ctx, request_context=request_context, handler=handler
            )

    agent = Agent(
        FunctionModel(_model),
        name=_AGENT_NAME,
        output_type=int,
        capabilities=[_CountingGuard()],
    )

    result = asyncio.run(agent.run("give a number"))

    assert result.output == 7
    assert len(entries) == 2, "one hook entry per model request, retries included"
    assert entries[1] > entries[0], "the second entry is the retry, a later request"


# --- D5 case 8: coverage and attachment (T004 RED) ------------------------------
#
# The module existing is not the feature: the guard must reach every durable
# agent through the loader (D2) and the worker must refuse to boot without it
# (D3). These four are RED on the tree that has the module attached to
# nothing; the fixture-agents registry and the received_capabilities pattern
# are the same seam tests/durability/test_loader_contract_edges.py uses.

_FIXTURES = Path(__file__).parent / "fixture_agents"
_TOOL = _FIXTURES / "research" / "tools" / "web_search.py"
_UNGUARDED_AGENT_NAME = "unguarded_chaos_agent"


def _fixture_roles() -> dict[str, RoleConfig]:
    """planner (3-arg build shape) + research (5-arg shape), per the loader
    contract tests -- both build shapes must hand the guard over."""
    return {
        "planner": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
        "research": RoleConfig(
            kind="research",
            model="anthropic:glm-5.2",
            provider="fake",
            tool_files=[str(_TOOL)],
        ),
    }


def _unguarded_durable_agent() -> Agent:
    """A durable agent in the production capability shape MINUS the guard:
    exactly the object a build path that forgets payload_guard() would
    produce. It MUST carry TemporalDurability -- an agent missing durability
    would fail the boot check for the wrong reason and make the assertion
    below vacuous once the guard check exists."""
    from datetime import timedelta

    from pydantic_ai.durable_exec.temporal import TemporalDurability
    from pydantic_ai.models.test import TestModel
    from temporalio.common import RetryPolicy
    from temporalio.workflow import ActivityConfig

    return Agent(
        TestModel(call_tools=[]),
        name=_UNGUARDED_AGENT_NAME,
        capabilities=[
            TemporalDurability(
                activity_config=ActivityConfig(
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                ),
                model_activity_config={"heartbeat_timeout": None},
            )
        ],
    )


def test_every_temporal_agent_carries_the_guard():
    """D2/D3, coverage half: every agent the worker will serve satisfies
    has_payload_guard. The failure names the unguarded agents so the fix
    task knows exactly which build path forgot it."""
    from sdlc.agents.roles import ALL_TEMPORAL_AGENTS

    unguarded = [
        agent.name for agent in ALL_TEMPORAL_AGENTS if not payload_guard.has_payload_guard(agent)
    ]
    assert unguarded == [], (
        f"{len(unguarded)} of {len(ALL_TEMPORAL_AGENTS)} temporal agents carry "
        f"no ProposerPayloadGuard: {unguarded}"
    )


def test_loader_durable_path_hands_a_distinct_guard_per_role():
    """D2, durable path: with a durability factory supplied, build_agents
    hands EVERY role exactly one ProposerPayloadGuard (on both build shapes
    the fixture registry covers), and no guard instance is shared between
    two roles -- a shared capability would bind one instance to two agents,
    the same hazard the durability factory's fresh-per-role rule exists
    for."""
    from sdlc.agents.loader import build_agents

    sentinels: list[object] = []

    def factory() -> object:
        dur = object()  # a fresh durability identity per call
        sentinels.append(dur)
        return dur

    agents = build_agents(_fixture_roles(), {}, durability_factory=factory, agents_dir=_FIXTURES)
    guards: dict[str, payload_guard.ProposerPayloadGuard] = {}
    for role in ("planner", "research"):
        caps = agents[role].received_capabilities
        found = [c for c in caps if isinstance(c, payload_guard.ProposerPayloadGuard)]
        assert len(found) == 1, (
            f"{role}: expected exactly one ProposerPayloadGuard handed over, "
            f"got {len(found)} "
            f"(capabilities: {[type(c).__name__ for c in caps]})"
        )
        guards[role] = found[0]
    assert guards["planner"] is not guards["research"], (
        "one guard instance is shared between two roles"
    )
    assert len(sentinels) == 2, "fixture sanity: the factory ran once per role"


def test_loader_eval_path_hands_no_guard():
    """D2, eval path: with durability_factory=None (the loader-only/eval
    path, which never runs in a workflow and so has nothing for the guard
    to check) no ProposerPayloadGuard is handed to either role. A pin
    against T005 over-reaching, not a red: nothing anywhere attaches the
    guard yet, so this cannot fail until someone attaches it in the wrong
    place."""
    from sdlc.agents.loader import build_agents

    agents = build_agents(_fixture_roles(), {}, durability_factory=None, agents_dir=_FIXTURES)
    for role in ("planner", "research"):
        guards = [
            c
            for c in agents[role].received_capabilities
            if isinstance(c, payload_guard.ProposerPayloadGuard)
        ]
        assert guards == [], (
            f"{role}: the eval path must carry no guard "
            f"(capabilities: {[type(c).__name__ for c in agents[role].received_capabilities]})"
        )


def test_worker_boot_refuses_an_unguarded_durable_agent(monkeypatch):
    """D3: get_worker_activities raises RuntimeError naming the agent when
    the worker module's own ALL_TEMPORAL_AGENTS binding -- the name the
    loop actually reads; patching sdlc.agents.roles has no effect -- grows
    a durable agent built without the guard. The appended agent carries
    TemporalDurability, so the ONLY boot check it can fail is the guard
    one."""
    import sdlc.worker

    unguarded = _unguarded_durable_agent()
    monkeypatch.setattr(
        sdlc.worker,
        "ALL_TEMPORAL_AGENTS",
        [*sdlc.worker.ALL_TEMPORAL_AGENTS, unguarded],
    )

    with pytest.raises(RuntimeError) as excinfo:
        sdlc.worker.get_worker_activities()

    assert _UNGUARDED_AGENT_NAME in str(excinfo.value), (
        f"the boot refusal must name the unguarded agent, got: {excinfo.value}"
    )
