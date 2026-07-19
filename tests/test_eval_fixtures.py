"""Capture: a completed run's history -> agents/<role>/fixtures/<case>.json.

Pure core only (no live Temporal), mirroring tests/test_drift_harvester.py.
The message-shape assertion uses REAL pydantic-ai message objects serialized
to dicts, so extract_user_prompt is pinned to the shape the runtime actually
produces rather than a guessed one.
"""
import json
from datetime import datetime

from pydantic_ai.messages import (
    ModelMessagesTypeAdapter, ModelRequest, SystemPromptPart, UserPromptPart,
)

from sdlc.eval.fixtures import (
    AGENT_TO_ROLE, DEPS_ROLES, SUPPORTED_ROLES, EvalFixture,
    extract_user_prompt, fixtures_from_events, write_fixtures,
)


def _serialized_messages(system: str, user: str) -> list[dict]:
    """One ModelRequest with a system part and a user part, dumped the way the
    Temporal activity payload carries it.

    NOTE: in the installed pydantic-ai-slim (2.5.0), ModelRequest is a plain
    stdlib dataclass, not a pydantic BaseModel -- it has no .model_dump().
    The Temporal integration itself serializes `_RequestParams.messages:
    list[ModelMessage]` via ModelMessagesTypeAdapter (pydantic_ai/durable_exec
    /temporal/_model.py's _RequestParams field, converted through Temporal's
    pydantic data converter), so that adapter is the real, working
    equivalent of "dump this message list the way the runtime does" and is
    used here in place of the brief's `req.model_dump(mode="json")`."""
    req = ModelRequest(parts=[SystemPromptPart(content=system),
                              UserPromptPart(content=user)])
    return ModelMessagesTypeAdapter.dump_python([req], mode="json")


def test_supported_and_deps_role_sets():
    assert SUPPORTED_ROLES == frozenset(
        {"clarify", "planner", "qa", "reviewer", "analyst", "merge_verdict"})
    assert DEPS_ROLES == frozenset({"architect", "research"})
    # the two roles whose agent name is not their role name
    assert AGENT_TO_ROLE["qa_analyst_agent"] == "qa"
    assert AGENT_TO_ROLE["merge_verdict_agent"] == "merge_verdict"


def test_extract_user_prompt_from_real_messages():
    msgs = _serialized_messages("SYS", "the user prompt")
    assert extract_user_prompt(msgs) == "the user prompt"


def test_extract_user_prompt_none_when_absent():
    req = ModelRequest(parts=[SystemPromptPart(content="only system")])
    assert extract_user_prompt(
        ModelMessagesTypeAdapter.dump_python([req], mode="json")) is None


def test_fixtures_from_events_builds_one_per_supported_proposer():
    events = [
        {"activity": "clarify_agent__model_request",
         "input": {"messages": _serialized_messages("s", "clarify input")}},
        {"activity": "reviewer_agent__model_request",
         "input": {"messages": _serialized_messages("s", "review input")}},
        {"activity": "architect_agent__model_request",       # deps role: skip
         "input": {"messages": _serialized_messages("s", "arch input")}},
        {"activity": "run_coding_task", "input": {}},         # not a proposer
    ]
    registry = {"clarify": type("R", (), {"model": "anthropic:glm-5.2"})(),
                "reviewer": type("R", (), {"model": "anthropic:glm-5.2"})()}
    fx = fixtures_from_events("feature-1", "add-login-greenfield", events, registry)
    got = {f.role: f for f in fx}
    assert set(got) == {"clarify", "reviewer"}
    assert got["clarify"].prompt == "clarify input"
    assert got["reviewer"].model == "anthropic:glm-5.2"
    assert got["clarify"].source_run_id == "feature-1"


def test_write_fixtures_lands_beside_the_asset(tmp_path):
    agents = tmp_path / "agents"
    (agents / "clarify").mkdir(parents=True)
    fx = EvalFixture(role="clarify", case="add-login-greenfield",
                     prompt="p", model="anthropic:glm-5.2",
                     source_run_id="feature-1", captured_at=datetime(2026, 7, 18))
    paths = write_fixtures([fx], agents)
    assert paths == [agents / "clarify" / "fixtures" / "add-login-greenfield.json"]
    loaded = json.loads(paths[0].read_text(encoding="utf-8"))
    assert loaded["prompt"] == "p" and loaded["role"] == "clarify"
