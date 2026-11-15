"""FR-205/FR-113: the requirements artifact reaches the planner prompt and
the plan memo key.

``produce`` gains ``requirements_doc``: a doc with stories renders into the
prompt as ``render_requirements(doc)`` plus the covers instruction (the
planner's ``covers`` field is what plan_check's coverage halt reads), and
its ``digest`` joins the memo key between ``constitution_digest`` and
``guidance`` — clarify's same-payload rule re-applied (object and digest
from the artifact itself).

Byte-identity discipline (FR-010): ``requirements_doc=None`` keys and
prompts exactly like today; the flag-off empty artifact (``stories=[]``,
``digest=""``) renders to no block and concatenates to the identity, so it
too is byte-identical.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sdlc.core.models import PipelineConfig
from sdlc.stages.plan.step import prepare, produce
from sdlc.stages.requirements.models import (
    FunctionalRequirement,
    Requirements,
    Story,
    requirements_digest,
)
from sdlc.stages.requirements.prompts import render_requirements
from tests.fakes.canned import ARCH, CONSTITUTION, greenfield_idea

COVERS_INSTRUCTION = "Each task must list the FR ids it implements in its covers field."


def _doc(fr_text: str = "GET /hello returns 200") -> Requirements:
    stories = [
        Story(
            id="US-1",
            narrative="As a user, I want a greeting, so that the service greets me.",
            functional=[FunctionalRequirement(id="FR-1", text=fr_text)],
            success_criteria=[],
        )
    ]
    return Requirements(stories=stories, digest=requirements_digest(stories), drafted_by="agent")


class Ctx:
    """The plan services produce touches: recall (via prepare), run_role,
    cached_stage. Keys and prompts are captured for assertions."""

    def __init__(self):
        self.keys: list[str] = []
        self.prompts: list[str] = []

    def stage(self, status, trace=None):
        pass

    async def recall(self, cfg, bank, query, filters):
        return SimpleNamespace(items=["prior decision"], snapshot_hash="")

    async def run_role(self, cfg, role, model, agent, prompt, **kw):
        self.prompts.append(prompt)
        return SimpleNamespace(output=SimpleNamespace())

    async def cached_stage(
        self, cfg, stage, input_json, output_type, run_fn, *, prompt_digest="", recall_ref=""
    ):
        self.keys.append(input_json)
        return await run_fn(), False


def _run(**kw) -> Ctx:
    ctx = Ctx()

    async def go():
        cfg = PipelineConfig()
        prep = await prepare(ctx, cfg=cfg, idea=greenfield_idea(), planner_model="m-plan")
        await produce(
            ctx,
            prep,
            cfg=cfg,
            architecture=ARCH,
            planner_agent=object(),
            **kw,
        )

    asyncio.run(go())
    return ctx


# ---- memo key ----------------------------------------------------------------


def test_memo_key_without_requirements_doc_is_exactly_todays():
    """Pin the whole concatenation: arch JSON + "" + "" — a flag-off run
    must build the byte-for-byte key of today."""
    assert _run(requirements_doc=None).keys[0] == ARCH.model_dump_json()


def test_memo_key_requirements_digest_sits_between_constitution_and_guidance():
    doc = _doc()
    key = _run(
        constitution_digest="c" * 64,
        requirements_doc=doc,
        guidance="tighten",
    ).keys[0]
    assert key == ARCH.model_dump_json() + "c" * 64 + doc.digest + "tighten"


def test_memo_key_changed_requirements_digest_flips_the_key():
    a = _run(requirements_doc=_doc("GET /hello returns 200")).keys[0]
    b = _run(requirements_doc=_doc("GET /hello is rate limited")).keys[0]
    base = _run(requirements_doc=None).keys[0]
    assert a != b
    assert a != base and b != base


def test_memo_key_empty_doc_digests_to_the_identity():
    """The flag-off empty artifact (no stories, digest "") keys exactly like
    requirements_doc=None (FR-010)."""
    empty = Requirements(stories=[], digest="", drafted_by="empty")
    assert _run(requirements_doc=empty).keys[0] == _run(requirements_doc=None).keys[0]


# ---- prompt ------------------------------------------------------------------


def test_prompt_carries_rendered_requirements_plus_covers_instruction():
    doc = _doc()
    prompt = _run(requirements_doc=doc).prompts[0]
    assert render_requirements(doc) + "\n" + COVERS_INSTRUCTION in prompt


def test_prompt_without_requirements_doc_is_byte_identical():
    plain = _run(requirements_doc=None).prompts[0]
    assert plain == ARCH.model_dump_json() + "\nRelevant memory:\n- prior decision"


def test_prompt_empty_doc_renders_no_block():
    """A doc without stories gets no block and no instruction line (FR-010):
    the prompt is byte-identical to the no-doc run."""
    empty = Requirements(stories=[], digest="", drafted_by="empty")
    assert _run(requirements_doc=empty).prompts[0] == _run(requirements_doc=None).prompts[0]


def test_prompt_requirements_block_follows_constitution_block():
    doc = _doc()
    prompt = _run(constitution=CONSTITUTION, requirements_doc=doc).prompts[0]
    assert prompt.index("CP-1") < prompt.index(render_requirements(doc))
    assert prompt.index(render_requirements(doc)) < prompt.index("Relevant memory")
