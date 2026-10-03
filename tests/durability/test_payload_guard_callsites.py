"""007 T006 (PIN): the guard's error takes each call site's existing path.

Plan D4 / tasks T006. Every test hands the call site the REAL error object
-- obtained by driving ``ProposerPayloadGuard.wrap_model_request`` over the
limit with the workflow seam faked exactly the way
``test_payload_guard.py`` does -- never a hand-written ``ApplicationError``
with a made-up message, so a drift in the guard's failure shape fails here
instead of being papered over.

This module is a PIN: with T005 landed it is expected GREEN on the first
run. A red run here is SG-2 -- a call site does not behave as plan D4
claims (research R6); stop and report, do not edit ``src/``.

Pinned paths:
- ``RoleHost._run_role`` (the object wired into StageServices as
  ``run_role``, ``workflows/feature.py``) propagates the SAME exception
  object -- type, ``non_retryable`` flag and wire ``type`` field intact --
  and no usage is tracked: the guard fires before the model call, so
  neither ``price_usage`` nor ``_track_usage`` is reached;
- ``stages.review.step.run_adversary`` fails OPEN: the same error through
  the same ``_run_role`` returns None (the caller reads that as agreement),
  and ``classify_lens`` turns "adversary ran and produced no report" into
  the UNDECLARED_ABSENT tombstone -- an absence that cannot claim approval
  (``LensOutcome``'s validator);
- the error is an instance of a type in ``graph_dispatch.FAILURE_TYPES``
  (temporalio ``ApplicationError`` is a ``FailureError``), so a graph node
  routes it to the node's fail port.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from temporalio.exceptions import ApplicationError

from sdlc.agents import payload_guard
from sdlc.core.models import PipelineConfig
from sdlc.stages.review.lenses import LensPresence, classify_lens
from sdlc.stages.review.step import run_adversary
from sdlc.workflows import graph_dispatch
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.role_host import RoleHost

_LIMIT = payload_guard.PROPOSER_PAYLOAD_LIMIT_BYTES
_AGENT_NAME = "callsite_guard_agent"


# -- the real error, driven through the guard (not hand-written) --------------


def _messages(prompt: str) -> list[ModelRequest]:
    return [ModelRequest(parts=[UserPromptPart(content=prompt)])]


def _params() -> ModelRequestParameters:
    return ModelRequestParameters()


class _Ctx:
    """The D1-shaped context stand-in: the message rule reads ctx.agent.name."""

    def __init__(self, name: str) -> None:
        self.agent = SimpleNamespace(name=name)


class _NeverCalled:
    """Handler double: the guard must raise before the handler runs."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, request_context: object) -> ModelResponse:
        self.calls += 1
        return ModelResponse(parts=[TextPart("handler ran")])


def _seam_workflow(
    monkeypatch: pytest.MonkeyPatch,
    *,
    in_workflow: bool,
    patched: bool,
) -> None:
    """Fake the guard's temporalio.workflow seam -- the same seam T003's
    import style provides and ``test_payload_guard.py`` fakes."""
    monkeypatch.setattr(payload_guard.workflow, "in_workflow", lambda: in_workflow)
    monkeypatch.setattr(payload_guard.workflow, "patched", lambda _patch_id: patched)


def _real_error(monkeypatch: pytest.MonkeyPatch) -> ApplicationError:
    """Drive the real guard over the limit once and return the caught
    exception object. Identity of THIS object is what the call-site tests
    assert on."""
    _seam_workflow(monkeypatch, in_workflow=True, patched=True)
    handler = _NeverCalled()
    with pytest.raises(ApplicationError) as excinfo:
        asyncio.run(
            payload_guard.payload_guard().wrap_model_request(
                _Ctx(_AGENT_NAME),
                request_context=SimpleNamespace(
                    messages=_messages("E" * (_LIMIT + 2_048)),
                    model_request_parameters=_params(),
                    model_settings=None,
                ),
                handler=handler,
            )
        )
    assert handler.calls == 0, "fixture: the guard must raise before the handler"
    return excinfo.value


class _RaisingAgent:
    """A proposer stand-in whose run raises the given error, as the real
    agent.run surface does when the guard fires on any of its requests."""

    def __init__(self, error: ApplicationError) -> None:
        self._error = error

    async def run(self, *args: object, **kwargs: object) -> object:
        raise self._error


# -- D4 (1): _run_role propagates the same object, tracking nothing -----------


def test_run_role_propagates_the_guard_error_without_tracking_usage(monkeypatch):
    """FR-004, R6 row 1: no catch at the egress point -- the failure the
    stage fails with IS the guard's error, and it fires before the model
    call, so neither pricing nor the per-role usage bag is touched."""
    err = _real_error(monkeypatch)
    # FeatureWorkflow, not bare RoleHost: _run_role lives on the RoleHost
    # mixin but _track_usage/_role_usage on ReportHost -- the full workflow
    # is the object that carries both, and the mixins test constructs it
    # bare.
    host = FeatureWorkflow()
    tracked: list[dict[str, object]] = []
    monkeypatch.setattr(FeatureWorkflow, "_track_usage", lambda self, **kw: tracked.append(kw))

    with pytest.raises(ApplicationError) as excinfo:
        asyncio.run(
            host._run_role(
                PipelineConfig(), "planner", "anthropic:glm-5.2", _RaisingAgent(err), "the prompt"
            )
        )

    assert excinfo.value is err, "the SAME exception object must propagate"
    assert excinfo.value.non_retryable is True
    assert excinfo.value.type == payload_guard.OVERSIZE_ERROR_TYPE
    assert tracked == [], "a guard failure must never reach _track_usage"
    assert host._role_usage == {}, "and must leave the per-role usage bag empty"


# -- D4 (2): run_adversary fails open; classify_lens tombstones the absence ---


def test_run_adversary_fails_open_on_the_guard_error(monkeypatch):
    """R6 row 'adversary lens': the lens is caught, warned, and read as
    agreement (None) -- it must never fail a task (REVIEW-1.3). The ctx is
    a bare RoleHost because that is the production wiring: StageServices
    hands stages ``run_role=self._run_role``."""
    err = _real_error(monkeypatch)
    cfg = PipelineConfig(adversarial_review_enabled=True)

    result = asyncio.run(
        run_adversary(
            RoleHost(),
            cfg=cfg,
            contract=None,
            assertions=["A1"],
            diff={"patch": "diff --git a/x b/x"},
            qa_raw=None,
            task=SimpleNamespace(id="t1"),
            adversary_agent=_RaisingAgent(err),
        )
    )

    assert result is None, "the adversary lens must fail open on the guard's error"


def test_adversary_none_classifies_as_undeclared_absent():
    """The caller-side pairing: an adversary that was enabled, configured,
    and reached but produced no report (run_adversary returned None on the
    guard's error) classifies as UNDECLARED_ABSENT -- a tombstone that
    cannot carry an approval verdict."""
    outcome = classify_lens(
        "adversary", enabled=True, agent_present=True, reached=True, report=None
    )

    assert outcome.presence is LensPresence.UNDECLARED_ABSENT
    assert outcome.approved is None
    assert "ran but produced no report" in outcome.reason


# -- D4 (3): the error routes to a graph node's fail port --------------------


def test_the_guard_error_routes_to_a_graph_failure_type(monkeypatch):
    """R6 row 'graph node': temporalio's ApplicationError is a FailureError,
    so the guard's failure is an instance of a type in FAILURE_TYPES and the
    dispatcher sends the node to its fail edge instead of failing the task."""
    err = _real_error(monkeypatch)

    assert isinstance(err, graph_dispatch.FAILURE_TYPES)
