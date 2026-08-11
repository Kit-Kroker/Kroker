"""Replay: build a proposer agent from supplied instructions text and run it
on a fixture prompt. No Temporal — a plain synchronous model call."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..agents.loader import _load_build
from ..agents.settings import MODEL_SETTINGS
from .fixtures import EvalFixture


def _to_json(output: Any) -> str:
    """Proposer outputs are pydantic models; a bare-string test agent is not.
    Serialize either to a JSON string."""
    dump = getattr(output, "model_dump_json", None)
    if callable(dump):
        return dump()
    return json.dumps(output)


def run_variant_detailed(role: str, instructions_text: str,
                         fixture: EvalFixture, agents_dir: Path, *,
                         model_override: Any | None = None) -> tuple[str, Any]:
    """As run_variant, but also returns the run's Usage.

    The promptfoo provider needs it to report tokenUsage/cost -- the native
    `cost` assertion is an ABSOLUTE gating check and would be vacuous
    without real numbers (E-82).
    """
    build = _load_build(role, agents_dir / role)
    model = model_override if model_override is not None else fixture.model
    agent = build(model, instructions_text, MODEL_SETTINGS)
    result = agent.run_sync(fixture.prompt)
    # `usage` is a PROPERTY on RunResult (RunUsage), not a method.
    return _to_json(result.output), result.usage


def run_variant(role: str, instructions_text: str, fixture: EvalFixture,
                agents_dir: Path, *, model_override: Any | None = None) -> str:
    """Build agents/<role>/agent.py's Agent with instructions_text as its
    system prompt, run it on the fixture prompt, return serialized output.

    model_override lets tests inject a FunctionModel/TestModel; production
    passes nothing and the captured author model (fixture.model) is used, so
    both variants run under the same model and only the prompt differs.
    """
    return run_variant_detailed(role, instructions_text, fixture, agents_dir,
                                model_override=model_override)[0]
