"""Wire neutrality of the sub-run usage report (plan D5, FR-001/SC-002 as
amended; research R8).

Layer 2 (fast, PIN from the start): the provider request mappings serialize a
tool-return part's content, never its metadata -- a report riding
ToolReturnPart.metadata must not change one byte of the request body. The
concrete models are pointed at the local counting stub (always_ok) and ONE
[user prompt, tool call, tool return] history is sent twice per provider
mapping -- metadata None and metadata carrying a report dict (a literal until
T007, ``metadata_for`` since). A byte difference here is stop-guard SG-5.

Layer 1 (temporal): the durable stand-in pair -- one tool returning the bare
brief, one returning ``tool_return(brief, REPORT)`` -- run through a real
worker, and the recordings the concrete model receives are equal after
removing exactly the tool-return ``metadata`` key; the set of differing JSON
paths is exactly that key; the two agents' research tool definitions are
equal. On the branch before T008 the reported side fails by ImportError
(``tool_return`` does not exist yet): the expected RED."""

import copy
import json
from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter
from pydantic_ai import Agent, RunContext
from pydantic_ai import messages as _messages
from pydantic_ai.capabilities import ResolveModelId
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from temporalio import workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG
from sdlc.agents.runner import SdlcPydanticAIPlugin
from sdlc.observability.sub_run_usage import SubRunUsage, metadata_for
from sdlc.stages.architecture.models import ArchitectureSpec
from sdlc.stages.research.deps import ResearchDeps
from sdlc.stages.research.models import ResearchBrief
from tests.fakes.canned import ARCH

from ._http_stub import ProviderStub

# The report as the tool hands it over (T007: built with the pure module's
# own writer, so the wire side pins the key and the five fields exactly as
# metadata_for spells them).
_REPORT = metadata_for(
    SubRunUsage(
        model="m-test",
        input_tokens=7,
        output_tokens=2,
        cache_read_tokens=1,
        cache_write_tokens=0,
    )
)

_NOW = datetime(2026, 10, 5, tzinfo=UTC)


def _history(*, metadata: dict | None) -> list:
    """[user prompt, tool call, tool return] with the tool-return part's
    metadata set to `metadata`."""
    return [
        ModelRequest(parts=[UserPromptPart(content="look it up", timestamp=_NOW)]),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="lookup", args={"question": "collars?"}, tool_call_id="call_1"
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="lookup",
                    content="the answer",
                    tool_call_id="call_1",
                    metadata=metadata,
                    timestamp=_NOW,
                )
            ]
        ),
    ]


async def _send_twice(build_model) -> list[bytes]:
    """Send the metadata-None history and the report-metadata history through
    one always_ok stub; return the two recorded bodies in order."""
    with ProviderStub(mode="always_ok") as stub:
        await build_model(stub.base_url).request(
            _history(metadata=None), None, ModelRequestParameters()
        )
        await build_model(stub.base_url).request(
            _history(metadata=_REPORT), None, ModelRequestParameters()
        )
        bodies = list(stub.bodies)
    assert len(bodies) == 2, f"exactly two requests must land, saw {len(bodies)}"
    return bodies


@pytest.mark.asyncio
async def test_openai_chat_mapping_serializes_no_metadata():
    """The openai-chat mapping (the route `zai:glm-5.3` uses): the request
    body is byte-identical with and without tool-return metadata."""
    bodies = await _send_twice(
        lambda base_url: OpenAIChatModel(
            "gpt-5.2", provider=OpenAIProvider(base_url=base_url, api_key="dummy")
        )
    )

    assert all(isinstance(b, bytes) and b for b in bodies), (
        "the stub must record one non-empty body per request"
    )
    assert bodies[0] == bodies[1], (
        "the openai-chat request body must be byte-identical with and without "
        "tool-return metadata -- the mapping serializes part.content only "
        "(FR-001/SC-002 layer 2)"
    )


@pytest.mark.asyncio
async def test_anthropic_mapping_serializes_no_metadata():
    """The anthropic mapping: the request body is byte-identical with and
    without tool-return metadata."""
    bodies = await _send_twice(
        lambda base_url: AnthropicModel(
            "glm-5.2", provider=AnthropicProvider(base_url=base_url, api_key="dummy")
        )
    )

    assert all(isinstance(b, bytes) and b for b in bodies), (
        "the stub must record one non-empty body per request"
    )
    assert bodies[0] == bodies[1], (
        "the anthropic request body must be byte-identical with and without "
        "tool-return metadata -- the mapping serializes part.content only "
        "(FR-001/SC-002 layer 2)"
    )


# --- Layer 1: the durable pair (temporal) -----------------------------------
#
# The T029 parity-test shape: module-level durability-bound stand-in agents,
# a recording concrete model, a real worker. The production agent name
# architect_agent is NOT reused (unique activity names).

_message_adapter: TypeAdapter[list[_messages.ModelMessage]] = TypeAdapter(
    list[_messages.ModelMessage]
)

# Non-zero counts: the report must be worth harvesting, and its five fields
# must be distinguishable from a default.
REPORT = SubRunUsage(
    model="m-test",
    input_tokens=7,
    output_tokens=2,
    cache_read_tokens=1,
    cache_write_tokens=0,
)

REPORTED_BRIEF = ResearchBrief(summary="wire layer 1 canned brief")

_VOLATILE = ("run_id", "conversation_id", "timestamp")


class _RecordingTestModel(TestModel):
    """Parity shape: record exactly what the durable layer hands a concrete
    model -- the message turns and the research tool's definition."""

    def __init__(self, *args, recorded: list, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.recorded = recorded

    async def request(  # type: ignore[override]
        self, messages, model_settings, model_request_parameters
    ):
        self.recorded.append(
            {
                "messages": json.loads(_message_adapter.dump_json(list(messages))),
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters_json_schema": t.parameters_json_schema,
                    }
                    for t in (model_request_parameters.function_tools or ())
                ],
            }
        )
        return await super().request(messages, model_settings, model_request_parameters)


def _wire_agent(*, name: str, reported: bool, recorded: list) -> Agent:
    """The parity recipe, twice: same everything except the agent name and
    whether the research tool returns the bare brief or the reported pair.
    ``tool_return`` does not exist before T008, so it is imported lazily
    inside the tool body -- module import stays base-only and the reported
    run fails by ImportError there (the RED)."""
    recording_model = _RecordingTestModel(
        custom_output_args=ARCH.model_dump(mode="json"),
        call_tools=["research"],
        recorded=recorded,
    )
    agent = Agent(
        recording_model,
        name=name,
        deps_type=ResearchDeps,
        output_type=ArchitectureSpec,
        capabilities=[
            TemporalDurability(
                activity_config=AGENT_ACTIVITY_CONFIG,
                model_activity_config={"heartbeat_timeout": None},
            ),
            ResolveModelId(lambda ctx, model_id: recording_model),
        ],
    )

    @agent.tool
    async def research(ctx: RunContext[ResearchDeps], question: str) -> ResearchBrief:
        """Consult grounded research on a sub-question."""
        if reported:
            from sdlc.stages.research.toolset import tool_return  # lands with T008

            return tool_return(REPORTED_BRIEF, REPORT)
        return REPORTED_BRIEF

    return agent


_BARE_RECORDED: list = []
_REPORTED_RECORDED: list = []

_AGENT_BARE = _wire_agent(name="architect_agent_wire_bare", reported=False, recorded=_BARE_RECORDED)
_AGENT_REPORTED = _wire_agent(
    name="architect_agent_wire_reported", reported=True, recorded=_REPORTED_RECORDED
)


def _wire_deps() -> ResearchDeps:
    return ResearchDeps(
        run_id="wire-layer-1",
        provider="fake",
        max_searches=1,
        max_fetches=1,
        max_cost_usd=1.0,
    )


@workflow.defn
class _WireBareWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        result = await _AGENT_BARE.run(prompt, deps=_wire_deps())
        return result.output.model_dump_json()


@workflow.defn
class _WireReportedWorkflow:
    @workflow.run
    async def run(self, prompt: str) -> str:
        result = await _AGENT_REPORTED.run(prompt, deps=_wire_deps())
        return result.output.model_dump_json()


def _strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k not in _VOLATILE}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def _turns(recording: dict) -> list:
    return _strip_volatile(recording["messages"])


def _strip_tool_return_metadata(messages: list) -> list:
    """A metadata-stripped COPY: removes exactly the tool-return parts'
    ``metadata`` key on every message, leaving the input untouched (the raw
    diff in assertion (b) reads the unstripped lists)."""
    stripped = copy.deepcopy(messages)
    for message in stripped:
        if not isinstance(message, dict):
            continue
        for part in message.get("parts", []):
            if isinstance(part, dict) and part.get("part_kind") == "tool-return":
                part.pop("metadata", None)
    return stripped


def _differing_paths(bare, reported) -> list[str]:
    """The JSON paths where two turn structures differ."""
    paths: list[str] = []

    def walk(a, b, prefix: str) -> None:
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a or key not in b:
                    paths.append(f"{prefix}.{key}")
                else:
                    walk(a[key], b[key], f"{prefix}.{key}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                paths.append(f"{prefix} (len {len(a)} != {len(b)})")
                return
            for i, (x, y) in enumerate(zip(a, b, strict=False)):
                walk(x, y, f"{prefix}[{i}]")
        elif a != b:
            paths.append(prefix)

    walk(bare, reported, "$")
    return paths


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_durable_report_differs_only_by_the_metadata_key():
    """Wire layer 1 (FR-001/SC-002): through the durable path, (a) the two
    agents' model-visible recordings are equal after removing exactly the
    tool-return metadata key from both, (b) the raw difference is exactly
    that key, and (c) the two agents' research tool definitions are equal --
    the model that answers the architect never learns a new surface. Before
    T008 the reported run fails by ImportError (tool_return missing)."""
    queue = "c12-wire-layer-1"
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[_WireBareWorkflow, _WireReportedWorkflow],
            activities=(
                list(TemporalDurability.from_agent(_AGENT_BARE).temporal_activities)
                + list(TemporalDurability.from_agent(_AGENT_REPORTED).temporal_activities)
            ),
            plugins=[SdlcPydanticAIPlugin()],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            bare = await env.client.start_workflow(
                _WireBareWorkflow.run,
                "Design a greeting endpoint.",
                id="c12-wire-layer-1-bare",
                task_queue=queue,
            )
            await bare.result()
            reported = await env.client.start_workflow(
                _WireReportedWorkflow.run,
                "Design a greeting endpoint.",
                id="c12-wire-layer-1-reported",
                task_queue=queue,
            )
            await reported.result()

    assert len(_BARE_RECORDED) == len(_REPORTED_RECORDED) == 2, (
        f"expected a two-turn model run on both sides, got "
        f"{len(_BARE_RECORDED)}/{len(_REPORTED_RECORDED)}"
    )

    # (a) equal after removing exactly the tool-return metadata key.
    bare_turns = [t for r in _BARE_RECORDED for t in _turns(r)]
    reported_turns = [t for r in _REPORTED_RECORDED for t in _turns(r)]
    assert _strip_tool_return_metadata(bare_turns) == _strip_tool_return_metadata(reported_turns)

    # (b) the raw difference is exactly the tool-return metadata key.
    diff = _differing_paths(bare_turns, reported_turns)
    assert len(diff) == 1 and diff[0].endswith(".metadata") and ".parts[" in diff[0], (
        f"the only permitted difference is the tool-return metadata key, got {diff}"
    )

    # (c) the research tool definition the agent exposes is unchanged.
    for recording in (_BARE_RECORDED[0], _REPORTED_RECORDED[0]):
        assert recording["tools"] == _BARE_RECORDED[0]["tools"], (
            "the research tool definition must be identical on both agents "
            "(name, description, parameters_json_schema)"
        )
    assert [t["name"] for t in _BARE_RECORDED[0]["tools"]] == ["research"]
