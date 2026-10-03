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

import sdlc.workflows.assessment as assessment_module
from sdlc.agents import payload_guard, roles
from sdlc.agents.payload_guard import has_payload_guard
from sdlc.assessment.activities import discover_context
from sdlc.assessment.discover.map import CapabilityMap, DiscoverContext, GraphSummary
from sdlc.assessment.models import PhaseId, PhaseResult
from sdlc.assessment.risk.models import UnifiedRiskMap
from sdlc.core.models import PipelineConfig
from sdlc.measurement import CollectionState, Measurement
from sdlc.stages.review.lenses import LensPresence, classify_lens
from sdlc.stages.review.step import run_adversary
from sdlc.workflows import graph_dispatch
from sdlc.workflows.assessment import AssessmentInput, AssessmentWorkflow
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.role_host import RoleHost
from sdlc.workflows.scanning import ScanOutcome
from tests.test_assessment_workflow import _risk_map, _scan_result, _triage

_LIMIT = payload_guard.PROPOSER_PAYLOAD_LIMIT_BYTES
_AGENT_NAME = "callsite_guard_agent"
_OVERSIZE_PROMPT = "E" * (_LIMIT + 2_048)
# The measure the guard embedded in the message below: deterministic (pure
# function over the same fixture), so the reason-name assertions can pin it.
_EXPECTED_SIZE = payload_guard.payload_size(
    [ModelRequest(parts=[UserPromptPart(content=_OVERSIZE_PROMPT)])],
    ModelRequestParameters(),
    None,
)


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


def _real_error(monkeypatch: pytest.MonkeyPatch, name: str = _AGENT_NAME) -> ApplicationError:
    """Drive the real guard over the limit once and return the caught
    exception object. Identity of THIS object is what the call-site tests
    assert on; ``name`` is the agent name baked into the message rule."""
    _seam_workflow(monkeypatch, in_workflow=True, patched=True)
    handler = _NeverCalled()
    with pytest.raises(ApplicationError) as excinfo:
        asyncio.run(
            payload_guard.payload_guard().wrap_model_request(
                _Ctx(name),
                request_context=SimpleNamespace(
                    messages=_messages(_OVERSIZE_PROMPT),
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


# -- T008 (b): the assessment phases' fail-closed / degraded paths -----------
#
# The same real error, handed to the proposer binding the phase bodies
# actually read: assessment.py imports t_discover/t_risk at MODULE level
# (under workflow.unsafe.imports_passed_through), so the stub is patched on
# the assessment module's own name, not on roles' -- patching roles would
# leave the real durable agent running. No server: the only activities
# faked are the phase lead-ins (discover_context succeeds with a measured
# empty context; every run_or_degrade call degrades to its fallback), which
# is exactly the scaffolding's no-workflow test posture.


def _measured_context() -> DiscoverContext:
    return DiscoverContext(
        graph=GraphSummary(
            parsed=1,
            unparsed=0,
            edges=0,
            unresolved_relative_rate=Measurement.measured(0.0),
        ),
        collected=Measurement.measured(1.0),
    )


def _scan_outcome() -> ScanOutcome:
    """A measured scan over the scaffolding's ScanResult, so the S5 row
    _discover requires is MEASURED."""
    return ScanOutcome(
        result=PhaseResult(phase=PhaseId.SCAN, collected=Measurement.measured(1.0)),
        scan=_scan_result(),
        tree_hash="t" * 40,
    )


def _fake_lead_in_activities(monkeypatch: pytest.MonkeyPatch) -> None:
    """discover_context succeeds; anything run_or_degrade-wrapped raises and
    takes its fallback (memo MISS, verification skip)."""

    async def _fake_activity(activity: object, arg: object, **_opts: object) -> object:
        if activity is discover_context:
            return _measured_context()
        raise RuntimeError("no activity runtime in-process")

    monkeypatch.setattr(assessment_module.workflow, "execute_activity", _fake_activity)


def test_discover_phase_fails_closed_naming_agent_size_and_limit(monkeypatch):
    """R6 row 'assessment discover': the guard's error through t_discover.run
    lands in the existing catch and becomes no_discover -- map-less, phase
    NOT_COLLECTED, and the reason carries the agent name, the measured size
    and the limit (no cut at this site)."""
    agent_name = roles.t_discover.name
    err = _real_error(monkeypatch, name=agent_name)
    monkeypatch.setattr(assessment_module, "t_discover", _RaisingAgent(err))
    _fake_lead_in_activities(monkeypatch)

    out = asyncio.run(
        AssessmentWorkflow()._discover(AssessmentInput(repo_dir="/r"), _triage(), _scan_outcome())
    )

    reason = out.result.collected.reason
    assert out.map is None, "fail closed: a tripped proposer yields no map"
    assert out.result.phase is PhaseId.DISCOVER
    assert out.result.collected.state is CollectionState.NOT_COLLECTED
    assert reason.startswith("discover proposer failed:")
    assert agent_name in reason
    assert str(_EXPECTED_SIZE) in reason
    assert str(_LIMIT) in reason


def test_risk_phase_degrades_and_the_facts_survive_the_300_char_cut(monkeypatch):
    """R6 row 'assessment risk': the guard's error through t_risk.run lands
    in _judge's catch and returns the baseline DEGRADED -- composites
    survive, judgment NOT_COLLECTED -- and the agent name, size and limit
    all sit inside the 300-character cut (assessment.py's [:300])."""
    agent_name = roles.t_risk.name
    err = _real_error(monkeypatch, name=agent_name)
    monkeypatch.setattr(assessment_module, "t_risk", _RaisingAgent(err))
    baseline = _risk_map()

    out = asyncio.run(
        AssessmentWorkflow()._judge(
            AssessmentInput(repo_dir="/r"),
            _triage(),
            CapabilityMap(collected=Measurement.measured(1.0)),
            baseline,
            proposing=True,
        )
    )

    reason = out.judgment.reason
    assert isinstance(out, UnifiedRiskMap)
    assert out.collected.state is CollectionState.MEASURED, "the composites survive"
    assert out.capabilities == baseline.capabilities
    assert out.judgment.state is CollectionState.NOT_COLLECTED
    assert len(reason) <= 300, "the degraded reason is cut at 300 characters"
    assert reason.startswith("the risk proposer ran and failed:")
    assert agent_name in reason, "the agent name must survive the cut"
    assert str(_EXPECTED_SIZE) in reason, "the measured size must survive the cut"
    assert str(_LIMIT) in reason, "the limit must survive the cut"


# -- T008 (c): the two assessment agents are durable and guarded --------------


def test_discover_and_risk_agents_are_durable_and_guarded():
    """The attachment claim behind (b): both assessment proposers are in
    ALL_TEMPORAL_AGENTS (so the boot check covers them) and carry the guard
    (so the errors (b) drives are the ones a real run would raise)."""
    assert roles.discover_agent in roles.ALL_TEMPORAL_AGENTS
    assert roles.risk_agent in roles.ALL_TEMPORAL_AGENTS
    assert has_payload_guard(roles.discover_agent)
    assert has_payload_guard(roles.risk_agent)
