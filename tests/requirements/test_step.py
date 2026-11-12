"""FR-113 plan Task 8: the requirements step -- flag off (zero commands),
flag on with partial freeze (warning event), degraded (FAIL event), and the
cap warning.

The step runs workflow-side; its only model call crosses the
draft_requirements activity boundary, so these tests script
temporalio.workflow.execute_activity by activity-definition name (the
constitution retention suite's pattern) and never touch a model or disk.
freeze() runs for real: the frozen ids/digest are asserted against the
verify module's own outputs, not re-implemented here.
"""

from __future__ import annotations

import importlib
import pathlib
import re

import pytest
import temporalio.workflow

from sdlc.core.models import (
    IdeaBrief,
    PipelineConfig,
    ProjectMode,
    RoleConfig,
    RoleUsage,
)
from sdlc.stages.requirements.models import (
    DraftOutput,
    DraftStory,
    FunctionalRequirement,
    Requirements,
    Story,
    SuccessCriterion,
    requirements_digest,
)
from sdlc.stages.requirements.stage import DraftInput, _DraftResult
from sdlc.stages.requirements.verify import freeze

# The package __init__ re-exports the step FUNCTION as
# `requirements.step`'s submodule shadow rule; bind the module itself (the
# constitution suite's reason).
step_module = importlib.import_module("sdlc.stages.requirements.step")
step = step_module.step

BROWN = IdeaBrief(title="t", description="d", mode=ProjectMode.BROWNFIELD)

_GROUNDED = DraftStory(
    narrative="As a user I want X so that Y.",
    functional=["The system does X."],
    success_criteria=["X visibly happens."],
    source_ref="src/app.py",
)
_UNGROUNDED = DraftStory(
    narrative="As a user I want Z so that W.",
    functional=["The system does Z."],
    success_criteria=["Z visibly happens."],
    source_ref=None,  # brownfield freeze drops the whole story
)


def _story(n: str, ref: str) -> DraftStory:
    return DraftStory(
        narrative=f"As a user I want {n} so that Y.",
        functional=[f"The system does {n}."],
        success_criteria=[f"{n} visibly happens."],
        source_ref=ref,
    )


class _Ctx:
    """The StageContext surface the step uses: stage/emit/retain (no gate --
    touching one is the assertion)."""

    def __init__(self) -> None:
        self.statuses: list[tuple[str, str | None]] = []
        self.events: list[tuple[str, str | None, dict[str, str]]] = []
        self.retained: list[tuple[object, str, str, dict[str, str]]] = []
        self.gate_calls = 0

    def emit(self, kind, stage: str | None = None, **data: str) -> None:
        self.events.append((str(kind), stage, data))

    def stage(self, status: str, trace: str | None = None) -> None:
        self.statuses.append((status, trace))

    async def gate(self, *args, **kwargs):
        self.gate_calls += 1
        raise AssertionError("requirements holds no gate")

    async def retain(self, cfg, kind, bank, text, metadata):
        self.retained.append((kind, bank, text, metadata))


def _script(monkeypatch, results: dict[str, object], scheduled: list | None = None) -> None:
    """Mock temporalio.workflow.execute_activity, dispatched by activity
    definition name; every scheduled activity must be scripted or the test
    fails (that IS the zero-commands assertion)."""

    async def _execute(activity_fn, *args, **kwargs):
        defn = getattr(activity_fn, "__temporal_activity_definition", None)
        name = defn.name if defn is not None else getattr(activity_fn, "__name__", "")
        if scheduled is not None:
            scheduled.append((name, args[0] if args else None))
        if name in results:
            item = results[name]
            if isinstance(item, BaseException):
                raise item
            return item
        raise AssertionError(f"unexpected activity scheduled: {name}")

    monkeypatch.setattr(temporalio.workflow, "execute_activity", _execute)


def _ended(ctx: _Ctx) -> dict[str, str]:
    events = [data for kind, _, data in ctx.events if kind == "stage_ended"]
    assert len(events) == 1, f"exactly one STAGE_ENDED, got {ctx.events}"
    return events[0]


def test_slice_exports_step_and_activities():
    from sdlc import stages as all_stages
    from sdlc.stages.requirements import ACTIVITIES

    # `step` stays on its submodule (the architecture/plan rule); the
    # handler imports it from there.
    from sdlc.stages.requirements.step import step as step_fn

    assert callable(step_fn)
    assert [a.__temporal_activity_definition.name for a in ACTIVITIES] == ["draft_requirements"]
    # the ACTIVITIES list joins the worker's registration via STAGE_MODULES
    assert any(m.__name__ == "sdlc.stages.requirements" for m in all_stages.STAGE_MODULES)


def test_pipeline_config_carries_the_requirements_bounds():
    cfg = PipelineConfig()
    assert (cfg.requirements.max_stories, cfg.requirements.max_requests) == (8, 6)


@pytest.mark.asyncio
async def test_flag_off_zero_commands(monkeypatch):
    """Flag off (the state every non-requirements graph projects, including
    the shipped default): the empty artifact, zero activities scheduled, no
    event, no gate, no retain -- byte-identical to a graph without the
    node, so default-graph replays stay byte-identical."""

    async def _no_activity(*args, **kwargs):
        raise AssertionError("flag off must schedule zero activities")

    monkeypatch.setattr(temporalio.workflow, "execute_activity", _no_activity)
    ctx = _Ctx()

    out = await step(ctx, cfg=PipelineConfig(), idea=BROWN, repo_path=None)

    assert out == Requirements(drafted_by="empty", stories=[], digest="")
    assert ctx.statuses == []
    assert ctx.events == []
    assert ctx.retained == []
    assert ctx.gate_calls == 0


@pytest.mark.asyncio
async def test_flag_on_partial_freeze(monkeypatch):
    """One grounded + one ungrounded brownfield story -> 1 frozen with
    code-assigned ids, a warning naming the drop, priced usage, and a retain
    of the frozen artifact."""
    draft = DraftOutput(stories=[_GROUNDED, _UNGROUNDED])
    scheduled: list = []
    _script(
        monkeypatch,
        {
            "draft_requirements": _DraftResult(
                draft=draft,
                usage=RoleUsage(
                    role="product",
                    model="m1",
                    calls=1,
                    input_tokens=11,
                    output_tokens=7,
                ),
            ),
            "price_usage": 0.5,
        },
        scheduled=scheduled,
    )
    ctx = _Ctx()
    cfg = PipelineConfig(requirements_enabled=True)
    cfg.roles["product"] = RoleConfig(kind="proposer", model="run-model")

    out = await step(ctx, cfg=cfg, idea=BROWN, repo_path="/repo")

    # the one model call crossed the boundary with the run's particulars
    assert [name for name, _ in scheduled] == ["draft_requirements", "price_usage"]
    inp = scheduled[0][1]
    assert isinstance(inp, DraftInput)
    assert inp.idea_json == BROWN.model_dump_json()
    assert inp.repo_path == "/repo"
    assert inp.model == "run-model"  # resolve_role_model: the run override wins
    assert inp.deps.mode == "brownfield"  # the freeze contract
    assert inp.deps.run_id == ""  # no workflow context in a unit test
    assert (inp.deps.max_stories, inp.deps.max_requests) == (8, 6)

    # freeze assigned ids/digest in workflow code; the offender is dropped
    assert out.drafted_by == "agent"
    assert out.stories == [
        Story(
            id="US-1",
            narrative=_GROUNDED.narrative,
            functional=[FunctionalRequirement(id="FR-1", text="The system does X.")],
            success_criteria=[SuccessCriterion(id="SC-1", text="X visibly happens.")],
            source_ref="src/app.py",
        )
    ]
    assert out.digest == requirements_digest(out.stories)

    assert ctx.statuses == [("drafting", "requirements")]
    usage_events = [(st, d) for k, st, d in ctx.events if k == "model_usage"]
    assert usage_events == [
        (
            "requirements",
            {
                "role": "product",
                "model": "m1",
                "calls": "1",
                "input_tokens": "11",
                "output_tokens": "7",
                "cache_read_tokens": "0",
                "cache_write_tokens": "0",
                "cost_usd": "0.5",
            },
        )
    ]
    assert _ended(ctx) == {
        "role": "product",
        "outcome": "pass",
        "cost_usd": "0.5",
        "warning": "dropped 1 of 2 drafted items at freeze",
    }
    assert len(ctx.retained) == 1
    kind, bank, text, metadata = ctx.retained[0]
    assert str(kind) == "stage_summary"
    assert bank == cfg.memory.project_bank
    assert _GROUNDED.narrative in text and _UNGROUNDED.narrative not in text
    assert metadata["stage"] == "requirements"
    assert metadata["digest"] == out.digest
    assert ctx.gate_calls == 0


@pytest.mark.asyncio
async def test_degraded_emits_fail(monkeypatch):
    """Nothing survives freeze -> the empty requirements, a FAIL-path
    STAGE_ENDED, and nothing retained (the constitution fail-soft floor: the
    opt-in flag can never kill a run, so it fails soft, not loud)."""
    draft = DraftOutput(stories=[_UNGROUNDED])  # brownfield: no source_ref
    scheduled: list = []
    _script(
        monkeypatch,
        {
            "draft_requirements": _DraftResult(
                draft=draft,
                usage=RoleUsage(
                    role="product",
                    model="m1",
                    calls=1,
                    input_tokens=3,
                    output_tokens=2,
                ),
            ),
            "price_usage": 0.1,
        },
        scheduled=scheduled,
    )
    ctx = _Ctx()

    out = await step(
        ctx,
        cfg=PipelineConfig(requirements_enabled=True),
        idea=BROWN,
        repo_path="/repo",
    )

    assert out == Requirements(drafted_by="empty", stories=[], digest="")
    # even a degraded draft is priced (the spend survives the abort)
    assert [name for name, _ in scheduled] == ["draft_requirements", "price_usage"]
    assert _ended(ctx)["outcome"] == "fail"
    assert _ended(ctx)["warning"] == "no story survived freeze"
    assert ctx.retained == []
    assert ctx.gate_calls == 0


@pytest.mark.asyncio
async def test_cap_warns(monkeypatch):
    """More survivors than max_stories -> the first max_stories kept, a cap
    warning on STAGE_ENDED, dense ids (nothing dropped: cap is not drop)."""
    draft = DraftOutput(stories=[_story("A", "a.py"), _story("B", "b.py"), _story("C", "c.py")])
    scheduled: list = []
    _script(
        monkeypatch,
        {
            "draft_requirements": _DraftResult(
                draft=draft,
                usage=RoleUsage(role="product", model="m1", calls=1, input_tokens=9),
            ),
            "price_usage": 0.2,
        },
        scheduled=scheduled,
    )
    ctx = _Ctx()
    cfg = PipelineConfig(requirements_enabled=True, requirements={"max_stories": 2})

    out = await step(ctx, cfg=cfg, idea=BROWN, repo_path="/repo")

    assert [s.id for s in out.stories] == ["US-1", "US-2"]
    assert [s.narrative for s in out.stories] == [
        _story("A", "a.py").narrative,
        _story("B", "b.py").narrative,
    ]
    assert _ended(ctx)["outcome"] == "pass"
    assert _ended(ctx)["warning"] == "capped to 2 stories at freeze"
    assert len(ctx.retained) == 1


def _clause_text(clause_id: str) -> str:
    """The named clause's text from the slice contract, requirements.md —
    from its `### <id>` heading to the next heading. The contract is a
    shipped doc, so citing it is part of the assertion: a clause that was
    deleted or renumbered fails here, not silently in review."""
    contract = pathlib.Path("src/sdlc/stages/requirements/requirements.md").read_text(
        encoding="utf-8"
    )
    match = re.search(
        rf"^### {re.escape(clause_id)}\n(.*?)(?=^### |^## |\Z)",
        contract,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert match is not None, f"{clause_id} not found in requirements.md"
    return match.group(1)


@pytest.mark.clause("REQUIREMENTS-1.4")
def test_freeze_rules_are_the_contract_clause():
    """REQUIREMENTS-1.4 states the shipped partial-freeze rules in their
    OPERATIONAL order, and freeze() enforces each one. The order is pinned
    on both sides: the brownfield source_ref drop runs BEFORE the text
    rules (the rescue case below) — a rejected story's texts never
    enter the keyspace."""
    clause = _clause_text("REQUIREMENTS-1.4")
    # the clause names every rule the code applies
    assert "US-1" in clause and "surviving order" in clause  # code-assigned ids
    assert "source_ref" in clause  # brownfield grounding drop (strip semantics)
    assert "duplicate" in clause  # exact-duplicate collapse, global keyspaces
    assert "whitespace-only" in clause  # narrative + text noise drops
    assert "max_stories" in clause  # the cap keeps the first max_stories
    assert "degrade" in clause  # zero survivors
    # ...and states the order as operational: brownfield drop before texts
    assert "before" in clause and "keyspace" in clause

    # behavior: three ungrounded brownfield stories drop as units — exactly
    # one dropped entry each (their narratives), for missing refs. The
    # keyspace ordering itself is pinned by the rescue case below.
    ungrounded = [
        DraftStory(
            narrative=f"As a user I want {name} so that Y.",
            functional=[f"The system does {name}."],
            success_criteria=[f"{name} visibly happens."],
            source_ref=None,
        )
        for name in ("X", "Z", "W")
    ]
    res = freeze(DraftOutput(stories=ungrounded), mode="brownfield")
    assert res.degraded is True
    assert res.dropped == [s.narrative for s in ungrounded]

    # a rejected story's text must not block the same text in a survivor
    rescue = freeze(
        DraftOutput(
            stories=[
                DraftStory(
                    narrative="As a user I want U so that Y.",
                    functional=["The system does X."],
                    success_criteria=[],
                    source_ref="   ",  # whitespace ref counts as missing
                ),
                DraftStory(
                    narrative="As a user I want V so that Y.",
                    functional=["The system does X."],
                    success_criteria=[],
                    source_ref="docs/prd.md",
                ),
            ]
        ),
        mode="brownfield",
    )
    assert [fr.text for fr in rescue.frozen.stories[0].functional] == ["The system does X."]
    assert rescue.frozen.digest != ""
    assert rescue.degraded is False
