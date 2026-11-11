"""FR-112, Task 8: the constitution digest joins the architect memo key, and
the bounded constitution block renders into the prompt ABOVE recall (spec
hierarchy: idea -> constitution -> codebase map -> recall).

Byte-identity discipline (FR-010, the ResearchDeps.research_model
omit-while-default rule expressed on the memo-key seam): a run that never
saw a constitution and one handed the flag-off digest "" must key
byte-identically; only a non-empty digest may move the key.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sdlc.core.models import PipelineConfig
from sdlc.stages.architecture.step import prepare, produce
from tests.fakes.canned import ARCH, CLARIFIED, CONSTITUTION, greenfield_idea


class Ctx:
    """The architecture services produce touches: recall (via prepare),
    run_role, cached_stage. Keys and prompts are captured for assertions."""

    def __init__(self):
        self.keys: list[str] = []
        self.prompts: list[str] = []

    def stage(self, status, trace=None):
        pass

    async def recall(self, cfg, bank, query, filters):
        return SimpleNamespace(items=["prior decision"])

    async def run_role(self, cfg, role, model, agent, prompt, **kw):
        self.prompts.append(prompt)
        return SimpleNamespace(output=ARCH)

    async def cached_stage(self, cfg, stage, input_json, output_type, run_fn, *, prompt_digest=""):
        self.keys.append(input_json)
        return await run_fn(), False


def _run(**kw) -> Ctx:
    ctx = Ctx()

    async def go():
        cfg = PipelineConfig()
        prep = await prepare(ctx, cfg=cfg, idea=greenfield_idea(), architect_model="m-arch")
        await produce(
            ctx,
            prep,
            cfg=cfg,
            requirements=CLARIFIED,
            architect_agent=object(),
            guidance=None,
            **kw,
        )

    asyncio.run(go())
    return ctx


def test_memo_key_constitution_digest_empty_equals_flag_off():
    assert _run(constitution_digest="").keys[0] == _run().keys[0]


def test_memo_key_changed_constitution_digest_flips_the_key():
    base = _run().keys[0]
    a = _run(constitution_digest="a" * 64).keys[0]
    b = _run(constitution_digest="b" * 64).keys[0]
    assert a != b
    assert a != base
    assert b != base


def test_prompt_without_constitution_is_byte_identical():
    plain = _run().prompts[0]
    explicit_none = _run(constitution=None).prompts[0]
    assert explicit_none == plain
    assert "CP-1" not in plain


def test_constitution_block_renders_between_requirements_and_recall():
    ctx = _run(constitution=CONSTITUTION)
    prompt = ctx.prompts[0]
    reqs_json = CLARIFIED.model_dump_json(exclude={"dropped", "dimensions_probed"})
    assert "CP-1" in prompt
    assert prompt.index(reqs_json) < prompt.index("CP-1")
    assert prompt.index("CP-1") < prompt.index("Relevant memory")
