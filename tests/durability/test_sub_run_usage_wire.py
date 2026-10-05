"""Wire neutrality of the sub-run usage report, layer 2 (plan D5, FR-001 /
SC-002 as amended; research R8): the provider request mappings serialize a
tool-return part's content, never its metadata -- a report riding
ToolReturnPart.metadata must not change one byte of the request body.

Fast tier, no temporalio: the concrete models are pointed at the local
counting stub (always_ok) and ONE [user prompt, tool call, tool return]
history is sent twice per provider mapping -- metadata None and metadata
carrying a report dict (a literal until T007, ``metadata_for`` since). PIN
from the start: it needs no source change to pass, and a byte difference
here is stop-guard SG-5."""

from datetime import UTC, datetime

import pytest
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
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider

from sdlc.observability.sub_run_usage import SubRunUsage, metadata_for

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
