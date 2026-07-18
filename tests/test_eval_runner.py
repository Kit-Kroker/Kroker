"""run_variant builds the proposer agent from SUPPLIED instructions text and
runs it. The critical assertion: the supplied text reaches the system prompt.
A run_variant that ignored its argument and read the shipped file would score
both variants identically and silently defeat the whole tool."""
from datetime import datetime, timezone

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from sdlc.eval.fixtures import EvalFixture
from sdlc.eval.runner import run_variant
from tests.conftest import write_registry_dir

seen_system: list[str] = []


def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    # first message is the ModelRequest carrying the system prompt
    for part in messages[0].parts:
        if part.part_kind == "system-prompt":
            seen_system.append(part.content)
    return ModelResponse(parts=[TextPart("canned output")])


def _fixture(role="reviewer"):
    return EvalFixture(role=role, case="c", prompt="the frozen input",
                       model="anthropic:glm-5.2", source_run_id="r",
                       captured_at=datetime(2026, 7, 18, tzinfo=timezone.utc))


def test_run_variant_puts_supplied_text_in_system_prompt(tmp_path):
    seen_system.clear()
    root = write_registry_dir(tmp_path / "agents")
    out = run_variant("reviewer", "VARIANT-B INSTRUCTIONS", _fixture(),
                      root, model_override=FunctionModel(_fn))
    assert out == '"canned output"' or "canned output" in out
    assert seen_system == ["VARIANT-B INSTRUCTIONS"]
