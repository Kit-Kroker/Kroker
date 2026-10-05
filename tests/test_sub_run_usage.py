"""The sub-run usage payload and its reader (plan D7 test_sub_run_usage.py;
tasks.md T005): the report a tool hands back beside its return value, and the
total, duck-typed harvest the model-egress point will use (plan D1 / R2 / R5).

Import discipline (T005): ``sdlc.observability.sub_run_usage`` is absent on
the base commit, so EVERY test imports it inside its own body -- module-top
imports stay base-only -- and every test here is RED on base with
ModuleNotFoundError. The end-to-end case additionally imports
``tool_return`` from ``sdlc.stages.research.toolset``, which lands with T008:
it stays red after T007 and is the case T007 commits as
``xfail(strict=True, reason="needs tool_return, T008")``."""

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from sdlc.stages.research.models import ResearchBrief

# The key, spelled as the literal the wire carries (the module under test
# owns the constant; this file never imports it at module top).
_KEY = "sdlc_sub_run_usage"


def _payload(model="m", input_tokens=1, output_tokens=2, cache_read=3, cache_write=4):
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
    }


def _metadata(**kw):
    return {_KEY: _payload(**kw)}


@dataclass
class _Part:
    part_kind: str
    metadata: object = None


@dataclass
class _Message:
    parts: list


class _MessagesResult:
    def __init__(self, messages):
        self._messages = messages

    def new_messages(self):
        return self._messages


class _RaisingMessagesResult:
    def new_messages(self):
        raise RuntimeError("boom")


def _tool_part(metadata):
    return _Part(part_kind="tool-return", metadata=metadata)


def test_from_run_usage_returns_the_counts():
    from sdlc.observability.sub_run_usage import SubRunUsage, from_run_usage

    usage = SimpleNamespace(
        input_tokens=11, output_tokens=2, cache_read_tokens=3, cache_write_tokens=4
    )
    assert from_run_usage(usage, "m") == SubRunUsage(
        model="m", input_tokens=11, output_tokens=2, cache_read_tokens=3, cache_write_tokens=4
    )


def test_from_run_usage_coerces_none_counts_to_zero():
    from sdlc.observability.sub_run_usage import SubRunUsage, from_run_usage

    usage = SimpleNamespace(
        input_tokens=None, output_tokens=2, cache_read_tokens=None, cache_write_tokens=4
    )
    assert from_run_usage(usage, "m") == SubRunUsage(
        model="m", input_tokens=0, output_tokens=2, cache_read_tokens=0, cache_write_tokens=4
    )


def test_from_run_usage_gives_none_for_zero_usage():
    from sdlc.observability.sub_run_usage import from_run_usage

    zero = SimpleNamespace(
        input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0
    )
    assert from_run_usage(zero, "m") is None
    all_none = SimpleNamespace(
        input_tokens=None, output_tokens=None, cache_read_tokens=None, cache_write_tokens=None
    )
    assert from_run_usage(all_none, "m") is None


def test_from_run_usage_accepts_a_real_run_usage():
    from sdlc.observability.sub_run_usage import SubRunUsage, from_run_usage

    assert from_run_usage(RunUsage(input_tokens=5, output_tokens=6), "m") == SubRunUsage(
        model="m", input_tokens=5, output_tokens=6, cache_read_tokens=0, cache_write_tokens=0
    )


def test_metadata_for_holds_the_key_and_the_dump():
    from sdlc.observability.sub_run_usage import SUB_RUN_USAGE_KEY, SubRunUsage, metadata_for

    assert SUB_RUN_USAGE_KEY == "sdlc_sub_run_usage"
    report = SubRunUsage(
        model="m", input_tokens=1, output_tokens=2, cache_read_tokens=3, cache_write_tokens=4
    )
    out = metadata_for(report)
    assert isinstance(out, dict)
    assert list(out) == [SUB_RUN_USAGE_KEY]
    assert out[SUB_RUN_USAGE_KEY] == _payload()


def test_harvest_reads_one_report():
    from sdlc.observability.sub_run_usage import SubRunUsage, harvest_reports

    result = _MessagesResult([_Message(parts=[_tool_part(_metadata())])])
    assert harvest_reports(result) == [
        SubRunUsage(
            model="m", input_tokens=1, output_tokens=2, cache_read_tokens=3, cache_write_tokens=4
        )
    ]


def test_harvest_preserves_message_then_part_order():
    from sdlc.observability.sub_run_usage import harvest_reports

    first = _Message(parts=[_tool_part(_metadata(model="a")), _tool_part(_metadata(model="b"))])
    second = _Message(parts=[_tool_part(_metadata(model="c"))])
    assert [r.model for r in harvest_reports(_MessagesResult([first, second]))] == ["a", "b", "c"]


def test_harvest_without_new_messages_yields_nothing():
    from sdlc.observability.sub_run_usage import harvest_reports

    assert harvest_reports(SimpleNamespace()) == []


def test_harvest_of_a_magic_mock_yields_nothing():
    from sdlc.observability.sub_run_usage import harvest_reports

    assert harvest_reports(MagicMock()) == []


def test_harvest_skips_parts_that_are_not_tool_returns():
    from sdlc.observability.sub_run_usage import harvest_reports

    message = _Message(
        parts=[_Part(part_kind="text", metadata=_metadata()), _tool_part(_metadata(model="keep"))]
    )
    assert [r.model for r in harvest_reports(_MessagesResult([message]))] == ["keep"]


def test_harvest_skips_non_dict_metadata():
    from sdlc.observability.sub_run_usage import harvest_reports

    message = _Message(parts=[_tool_part("nope"), _tool_part(_metadata(model="keep"))])
    assert [r.model for r in harvest_reports(_MessagesResult([message]))] == ["keep"]


def test_harvest_skips_metadata_without_the_key():
    from sdlc.observability.sub_run_usage import harvest_reports

    message = _Message(parts=[_tool_part({}), _tool_part(_metadata(model="keep"))])
    assert [r.model for r in harvest_reports(_MessagesResult([message]))] == ["keep"]


def test_harvest_skips_a_payload_missing_a_field():
    from sdlc.observability.sub_run_usage import harvest_reports

    message = _Message(parts=[_tool_part({_KEY: {"model": "m"}})])
    assert harvest_reports(_MessagesResult([message])) == []


def test_harvest_skips_a_non_integer_count():
    from sdlc.observability.sub_run_usage import harvest_reports

    message = _Message(parts=[_tool_part({_KEY: _payload(input_tokens="lots")})])
    assert harvest_reports(_MessagesResult([message])) == []


def test_harvest_skips_a_negative_count():
    from sdlc.observability.sub_run_usage import harvest_reports

    message = _Message(parts=[_tool_part({_KEY: _payload(input_tokens=-1)})])
    assert harvest_reports(_MessagesResult([message])) == []


def test_harvest_drops_an_empty_token_report():
    from sdlc.observability.sub_run_usage import harvest_reports

    zero = _payload(input_tokens=0, output_tokens=0, cache_read=0, cache_write=0)
    message = _Message(parts=[_tool_part({_KEY: zero}), _tool_part(_metadata(model="keep"))])
    assert [r.model for r in harvest_reports(_MessagesResult([message]))] == ["keep"]


def test_harvest_survives_a_raising_new_messages():
    from sdlc.observability.sub_run_usage import harvest_reports

    assert harvest_reports(_RaisingMessagesResult()) == []


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason="needs tool_return, T008")
async def test_end_to_end_report_round_trips_through_a_real_agent():
    """A real pydantic_ai agent whose tool returns tool_return(brief, report):
    harvest_reports(result) reads back exactly that report -- pinning the
    ``tool-return`` part kind and the key on BOTH sides (writer and reader).
    xfail(strict) until T008 lands tool_return; T008 removes this mark."""
    from sdlc.observability.sub_run_usage import SubRunUsage, harvest_reports
    from sdlc.stages.research.toolset import tool_return

    report = SubRunUsage(
        model="m-test", input_tokens=7, output_tokens=2, cache_read_tokens=1, cache_write_tokens=0
    )
    agent = Agent(TestModel(call_tools=["lookup"]), output_type=str)

    @agent.tool_plain
    def lookup() -> ResearchBrief:
        return tool_return(ResearchBrief(summary="canned"), report)

    result = await agent.run("look it up")

    assert harvest_reports(result) == [report]
