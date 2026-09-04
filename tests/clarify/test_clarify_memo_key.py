"""The clarify memo key must move when the fan-out's inputs move, and must
NOT move when the flag is off.

Without the first, editing a probe -- or retuning the cap -- serves a stale
clarification silently. Without the second, landing E-85 invalidates every
existing clarify memo even though the flag-off prompt did not change, which is
what "the default pipeline is byte-identical to today" rules out.

The unit under test is `_clarify_memo_extra`, the workflow's own helper, NOT
`content_key`. Asserting on hand-built key strings would pass unchanged if the
stage stopped appending the extra altogether; asserting on the helper the
stage actually calls is what makes the constraint executable. The content_key
tests at the bottom pin the one remaining thing the helper cannot: that a
non-empty extra really does move a key, i.e. that the term is load-bearing.
"""

from __future__ import annotations

from typing import Any

import pytest

from sdlc.assessment.scan.models import Confidence
from sdlc.benchmarks.models import QualityScore
from sdlc.context.models import CodebaseMap, MapModule
from sdlc.core.models import (
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
)
from sdlc.measurement import Measurement
from sdlc.memoization.cache import content_key
from sdlc.models import ClarifiedRequirements
from sdlc.stages import clarify
from sdlc.stages.clarify.prompts import (
    _clarify_memo_extra,
    probe_prompt_digest,
    prompt_digest,
)


def _map(name: str = "cap001", tree: str = "t1") -> CodebaseMap:
    ok = Measurement.measured(1.0)
    return CodebaseMap(
        tree_hash=tree,
        commit_sha="c" * 40,
        modules=(MapModule(name=name, member_paths=("src/a.py",), confidence=Confidence.LOW),),
        modules_collected=ok,
        contracts_collected=ok,
        hot_spots_collected=ok,
        collected=ok,
    )


def _cfg(**kw) -> PipelineConfig:
    return PipelineConfig(clarify_probes_enabled=True, **kw)


# ---- flag off: nothing is appended, at all ----------------------------


@pytest.mark.parametrize("cmap", [None, _map()])
def test_the_flag_off_extra_is_empty_with_or_without_a_tree(cmap):
    """The binding guarantee. An empty string concatenates to the identity,
    so a flag-off run keys exactly as it did pre-E-85 and every memo written
    before E-85 landed still hits."""
    assert _clarify_memo_extra(PipelineConfig(), cmap) == ""


def test_the_default_config_is_flag_off():
    # If this ever flips, the assertion above stops meaning anything.
    assert PipelineConfig().clarify_probes_enabled is False


# ---- flag on: every input that changes the answer moves the key -------


def test_turning_the_flag_on_appends_the_probe_digest():
    extra = _clarify_memo_extra(_cfg(), _map())
    assert extra != ""
    assert probe_prompt_digest() in extra


def test_a_different_tree_moves_the_extra():
    assert _clarify_memo_extra(_cfg(), _map(name="cap001")) != _clarify_memo_extra(
        _cfg(), _map(name="cap999")
    )


def test_the_same_tree_and_prompts_hit_the_same_extra():
    assert _clarify_memo_extra(_cfg(), _map()) == _clarify_memo_extra(_cfg(), _map())


def test_a_different_cap_moves_the_extra():
    """Spec section 10 names the cap as the first knob the benchmark tunes.
    The cap decides which questions reach a human and which land on
    `dropped`, so a memo made under cap=3 is not the cap=8 artifact."""
    assert _clarify_memo_extra(_cfg(clarify_question_cap=3), _map()) != _clarify_memo_extra(
        _cfg(clarify_question_cap=8), _map()
    )


def test_greenfield_has_no_tree_but_still_keys_stably():
    """codebase_map is None for a greenfield run. The term must be a stable
    sentinel, not a crash and not an empty string that would collide with
    the flag-off key."""
    greenfield = _clarify_memo_extra(_cfg(), None)
    assert greenfield == _clarify_memo_extra(_cfg(), None)
    assert greenfield != ""
    assert greenfield != _clarify_memo_extra(_cfg(), _map())


# ---- the extra is load-bearing in the key it feeds --------------------


def _key(extra: str) -> str:
    return content_key(
        "clarify", '{"title": "x"}' + extra, "prompt-sha", "anthropic:glm-5.2", "none"
    )


def test_the_flag_off_key_equals_the_pre_e85_key():
    assert _key(_clarify_memo_extra(PipelineConfig(), _map())) == _key("")


def test_the_flag_on_key_differs_from_the_pre_e85_key():
    assert _key(_clarify_memo_extra(_cfg(), _map())) != _key("")


# ---- the stage actually USES the helper and prompt_digest ------------------
# Tests that clarify.step passes both the extra memo key terms and prompt_digest
# into ctx.cached_stage, ensuring cache invalidation on probe edits, tree changes,
# or cap changes, while preserving byte-identity when the flag is off.


class _StubContext:
    def __init__(self) -> None:
        self.stage_calls: list[tuple[str, str | None]] = []
        self.cached_stage_calls: list[dict[str, Any]] = []
        self.judged: list[tuple[str, str]] = []
        self.recorded: list[Any] = []

    def stage(self, status: str, trace: str | None = None) -> None:
        self.stage_calls.append((status, trace))

    async def recall(self, cfg: Any, bank: str, *, query: str, filters: dict[str, str]) -> Any:
        from sdlc.models import RecallSnapshot

        return RecallSnapshot(query_hash="qh", bank=bank, watermark="wm", items=[])

    async def cached_stage(
        self,
        cfg: Any,
        stage: str,
        key: str,
        artifact_type: Any,
        run_fn: Any,
        *,
        prompt_digest: str = "",
    ) -> tuple[ClarifiedRequirements, bool]:
        self.cached_stage_calls.append(
            {
                "cfg": cfg,
                "stage": stage,
                "key": key,
                "artifact_type": artifact_type,
                "prompt_digest": prompt_digest,
            }
        )
        return (
            ClarifiedRequirements(
                summary="stub summary",
                functional_requirements=[],
                non_functional_requirements=[],
                out_of_scope=[],
                open_questions=[],
            ),
            False,
        )

    async def judge(
        self, cfg: Any, artifact_json: str, stage: str, *, author_model: str = ""
    ) -> QualityScore:
        self.judged.append((stage, author_model))
        return QualityScore(score=1.0, judge="contract", rationale="")

    async def record(self, cfg: Any, record: Any) -> None:
        self.recorded.append(record)


@pytest.mark.clause("CLARIFY-1.5")
@pytest.mark.asyncio
async def test_step_appends_extra_and_passes_prompt_digest():
    ctx = _StubContext()
    cfg = _cfg()
    idea = IdeaBrief(title="test idea", description="some desc", mode=ProjectMode.GREENFIELD)
    cmap = _map()
    reqs = await clarify.step(
        ctx,
        cfg=cfg,
        idea=idea,
        codebase_map=cmap,
        brief_digest="bd123",
        clarify_agent=None,
        route_agent=None,
        probe_agent=None,
    )
    assert reqs.summary == "stub summary"
    assert len(ctx.cached_stage_calls) == 1
    call = ctx.cached_stage_calls[0]
    assert call["stage"] == "clarify"
    assert call["prompt_digest"] == prompt_digest(cfg)
    assert ":e85:" in call["prompt_digest"]
    assert idea.model_dump_json() in call["key"]
    assert "bd123" in call["key"]
    assert _clarify_memo_extra(cfg, cmap) in call["key"]


@pytest.mark.asyncio
async def test_step_flag_off_passes_empty_prompt_digest_and_no_memo_extra():
    ctx = _StubContext()
    cfg = PipelineConfig()
    idea = IdeaBrief(title="test idea", description="some desc", mode=ProjectMode.GREENFIELD)
    reqs = await clarify.step(
        ctx,
        cfg=cfg,
        idea=idea,
        codebase_map=None,
        brief_digest="",
        clarify_agent=None,
        route_agent=None,
        probe_agent=None,
    )
    assert reqs.summary == "stub summary"
    assert len(ctx.cached_stage_calls) == 1
    call = ctx.cached_stage_calls[0]
    assert call["prompt_digest"] == ""
    assert call["key"] == idea.model_dump_json()
