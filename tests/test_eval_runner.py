"""run_variant builds the proposer agent from SUPPLIED instructions text and
runs it. The critical assertion: the supplied text reaches the system prompt.
A run_variant that ignored its argument and read the shipped file would score
both variants identically and silently defeat the whole tool."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from sdlc.agents.model_ids import ZAI_CODING_BASE_URL
from sdlc.eval import runner as eval_runner
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
    return EvalFixture(
        role=role,
        case="c",
        prompt="the frozen input",
        model="anthropic:glm-5.2",
        source_run_id="r",
        captured_at=datetime(2026, 7, 18, tzinfo=UTC),
    )


def test_run_variant_puts_supplied_text_in_system_prompt(tmp_path):
    seen_system.clear()
    root = write_registry_dir(tmp_path / "agents")
    out = run_variant(
        "reviewer", "VARIANT-B INSTRUCTIONS", _fixture(), root, model_override=FunctionModel(_fn)
    )
    assert out == '"canned output"' or "canned output" in out
    assert seen_system == ["VARIANT-B INSTRUCTIONS"]


def _url(base_url: object) -> str:
    """A client base URL without the trailing slash the OpenAI-style client
    normalises onto every URL."""
    return str(base_url).rstrip("/")


def test_run_variant_resolves_string_models_and_passes_model_overrides_through(
    tmp_path, monkeypatch
):
    """005 T011 (FR-016, plan D2 site 5): a string fixture.model must go
    through ``resolve_model`` BEFORE ``build(...)`` — a ``zai:`` string
    reaches the role's build function as a pydantic-ai Model whose client
    sits on the coding endpoint, not as the raw string — while an injected
    ``model_override`` instance (FunctionModel/TestModel) passes through
    unchanged. The recorder build replaces ``_load_build`` in the runner's
    namespace, so nothing touches the registry or the network."""
    seen_models: list[Any] = []

    def _recorder_load_build(role, role_dir):
        def _build(model, instructions_text, settings):
            seen_models.append(model)
            result = SimpleNamespace(output="stub output", usage=None)
            return SimpleNamespace(run_sync=lambda prompt: result)

        return _build

    monkeypatch.setattr(eval_runner, "_load_build", _recorder_load_build)
    fixture = EvalFixture(
        role="reviewer",
        case="c",
        prompt="the frozen input",
        model="zai:glm-5.3",
        source_run_id="r",
        captured_at=datetime(2026, 7, 18, tzinfo=UTC),
    )

    run_variant("reviewer", "VARIANT-B INSTRUCTIONS", fixture, tmp_path / "agents")

    (model,) = seen_models
    assert isinstance(model, Model), (
        f"build received {model!r}; a string fixture.model must be resolved "
        f"through resolve_model before build (005 T011, plan D2 site 5)"
    )
    assert _url(model.client.base_url) == ZAI_CODING_BASE_URL, (
        f"the resolved zai model points its client at "
        f"{_url(model.client.base_url)!r}; the URL policy must apply at the "
        f"eval site too (005 contract C1)"
    )

    override = FunctionModel(_fn)
    run_variant(
        "reviewer",
        "VARIANT-B INSTRUCTIONS",
        fixture,
        tmp_path / "agents",
        model_override=override,
    )
    assert seen_models[1] is override, (
        "an injected model_override instance must reach build unchanged — "
        "only string models resolve (005 T011)"
    )
