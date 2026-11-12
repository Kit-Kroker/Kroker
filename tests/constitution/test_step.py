"""FR-112 plan Task 7: the constitution step -- flag off (zero commands),
flag on with partial freeze (warning event), degraded (FAIL event).

The step runs workflow-side; its only model call crosses the
draft_constitution activity boundary, so these tests script
temporalio.workflow.execute_activity by activity-definition name (the
research retention suite's pattern) and never touch a model or disk.
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
from sdlc.stages.constitution.models import (
    Constitution,
    DraftOutput,
    DraftPrinciple,
    Principle,
    constitution_digest,
)
from sdlc.stages.constitution.stage import DraftInput, _DraftResult
from sdlc.stages.constitution.verify import freeze

# The package __init__ re-exports the step FUNCTION as `constitution.step`,
# so bind the module itself (the research suite's reason).
step_module = importlib.import_module("sdlc.stages.constitution.step")
step = step_module.step

BROWN = IdeaBrief(title="t", description="d", mode=ProjectMode.BROWNFIELD)

_GROUNDED = DraftPrinciple(
    statement="Flag-off runs stay byte-identical to today.",
    normative="MUST",
    rationale="FR-010",
    source_ref="AGENTS.md",
)
_UNGROUNDED = DraftPrinciple(
    statement="Cite the repo.",
    normative="SHOULD",
    rationale="grounding",
    source_ref=None,
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
        raise AssertionError("constitution holds no gate")

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
    from sdlc.stages.constitution import ACTIVITIES

    # `step` stays on its submodule (the architecture/plan rule); the
    # handler imports it from there.
    from sdlc.stages.constitution.step import step as step_fn

    assert callable(step_fn)
    assert [a.__temporal_activity_definition.name for a in ACTIVITIES] == ["draft_constitution"]
    # the ACTIVITIES list joins the worker's registration via STAGE_MODULES
    assert any(m.__name__ == "sdlc.stages.constitution" for m in all_stages.STAGE_MODULES)


def test_pipeline_config_carries_the_constitution_bounds():
    cfg = PipelineConfig()
    assert (cfg.constitution.max_principles, cfg.constitution.max_requests) == (12, 6)


@pytest.mark.asyncio
async def test_flag_off_zero_commands(monkeypatch):
    """Flag off (the state every non-constitution graph projects): the empty
    artifact, zero activities scheduled, no event, no gate, no retain --
    byte-identical to a graph without the node."""

    async def _no_activity(*args, **kwargs):
        raise AssertionError("flag off must schedule zero activities")

    monkeypatch.setattr(temporalio.workflow, "execute_activity", _no_activity)
    ctx = _Ctx()

    out = await step(ctx, cfg=PipelineConfig(), idea=BROWN, repo_path=None)

    assert out == Constitution(drafted_by="empty", principles=[], digest="")
    assert ctx.statuses == []
    assert ctx.events == []
    assert ctx.retained == []
    assert ctx.gate_calls == 0


@pytest.mark.asyncio
async def test_flag_on_partial_freeze_path(monkeypatch):
    """One grounded + one ungrounded brownfield principle -> 1 frozen with a
    code-assigned id, a warning naming the drop, priced usage, and a retain
    of the frozen artifact."""
    draft = DraftOutput(principles=[_GROUNDED, _UNGROUNDED])
    scheduled: list = []
    _script(
        monkeypatch,
        {
            "draft_constitution": _DraftResult(
                draft=draft,
                usage=RoleUsage(
                    role="constitution",
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
    cfg = PipelineConfig(constitution_enabled=True)
    cfg.roles["constitution"] = RoleConfig(kind="proposer", model="run-model")

    out = await step(ctx, cfg=cfg, idea=BROWN, repo_path="/repo")

    # the one model call crossed the boundary with the run's particulars
    assert [name for name, _ in scheduled] == ["draft_constitution", "price_usage"]
    inp = scheduled[0][1]
    assert isinstance(inp, DraftInput)
    assert inp.idea_json == BROWN.model_dump_json()
    assert inp.repo_path == "/repo"
    assert inp.model == "run-model"  # resolve_role_model: the run override wins
    assert inp.deps.mode == "brownfield"  # the freeze contract (ruling e)
    assert (inp.deps.max_principles, inp.deps.max_requests) == (12, 6)

    # freeze assigned ids/digests in workflow code; the offender is dropped
    assert out.drafted_by == "agent"
    assert out.principles == [
        Principle(
            id="CP-1",
            statement=_GROUNDED.statement,
            normative="MUST",
            rationale="FR-010",
            source_ref="AGENTS.md",
        )
    ]
    assert out.digest == constitution_digest(out.principles)

    assert ctx.statuses == [("drafting", "constitution")]
    usage_events = [(st, d) for k, st, d in ctx.events if k == "model_usage"]
    assert usage_events == [
        (
            "constitution",
            {
                "role": "constitution",
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
        "role": "constitution",
        "outcome": "pass",
        "cost_usd": "0.5",
        "warning": "dropped 1 of 2 drafted principles at freeze",
    }
    assert len(ctx.retained) == 1
    kind, bank, text, metadata = ctx.retained[0]
    assert str(kind) == "stage_summary"
    assert bank == cfg.memory.project_bank
    assert _GROUNDED.statement in text and _UNGROUNDED.statement not in text
    assert metadata["stage"] == "constitution"
    assert metadata["digest"] == out.digest


@pytest.mark.asyncio
async def test_degraded_emits_fail(monkeypatch):
    """Nothing survives freeze -> the empty constitution, a FAIL-path
    STAGE_ENDED, and nothing retained (the research fail-soft floor: the
    opt-in flag can never kill a run, so it fails soft, not loud)."""
    draft = DraftOutput(principles=[_UNGROUNDED])  # brownfield: no source_ref
    scheduled: list = []
    _script(
        monkeypatch,
        {
            "draft_constitution": _DraftResult(
                draft=draft,
                usage=RoleUsage(
                    role="constitution",
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
        cfg=PipelineConfig(constitution_enabled=True),
        idea=BROWN,
        repo_path="/repo",
    )

    assert out == Constitution(drafted_by="empty", principles=[], digest="")
    # even a degraded draft is priced (T6: the spend survives the abort)
    assert [name for name, _ in scheduled] == ["draft_constitution", "price_usage"]
    assert _ended(ctx)["outcome"] == "fail"
    assert _ended(ctx)["warning"] == "no principle survived freeze"
    assert ctx.retained == []
    assert ctx.gate_calls == 0


def _clause_text(clause_id: str) -> str:
    """The named clause's text from the slice contract, constitution.md —
    from its `### <id>` heading to the next heading. The contract is a
    shipped doc, so citing it is part of the assertion: a clause that was
    deleted or renumbered fails here, not silently in review."""
    contract = pathlib.Path("src/sdlc/stages/constitution/constitution.md").read_text(
        encoding="utf-8"
    )
    match = re.search(
        rf"^### {re.escape(clause_id)}\n(.*?)(?=^### |^## |\Z)",
        contract,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert match is not None, f"{clause_id} not found in constitution.md"
    return match.group(1)


@pytest.mark.clause("CONSTITUTION-1.4")
def test_freeze_rules_are_the_contract_clause():
    """CONSTITUTION-1.4 states the shipped partial-freeze rules, and
    freeze() enforces each one. Ruling (g) is pinned on both sides: the
    empty/whitespace-statement drop is IN the clause list and IN the
    behavior."""
    clause = _clause_text("CONSTITUTION-1.4")
    # the clause names every rule the code applies
    assert "CP-1" in clause and "surviving order" in clause  # code-assigned ids
    assert "source_ref" in clause  # brownfield grounding drop
    assert "duplicate" in clause  # exact-duplicate collapse
    assert "whitespace-only" in clause  # ruling (g): noise drop is listed
    assert "degrade" in clause  # zero survivors

    draft = DraftOutput(
        principles=[
            DraftPrinciple(statement="   ", normative="MUST", rationale="noise"),
            DraftPrinciple(statement="", normative="SHOULD", rationale="noise"),
            DraftPrinciple(
                statement="Cite the repo.", normative="MUST", rationale="ground"
            ),  # brownfield: no source_ref
            DraftPrinciple(
                statement="One source of truth.",
                normative="MUST",
                rationale="dup",
                source_ref="AGENTS.md",
            ),
            DraftPrinciple(
                statement="One source of truth.",
                normative="SHOULD",
                rationale="dup",
                source_ref="pyproject.toml",
            ),  # exact-duplicate statement: collapsed
            DraftPrinciple(
                statement="Survivor.",
                normative="MUST",
                rationale="kept",
                source_ref="README.md",
            ),
        ]
    )
    res = freeze(draft, mode="brownfield")

    # survivors renumber densely from CP-1 in surviving order
    assert [(p.id, p.statement) for p in res.frozen.principles] == [
        ("CP-1", "One source of truth."),
        ("CP-2", "Survivor."),
    ]
    assert res.frozen.digest == constitution_digest(res.frozen.principles)
    # every offender is listed as dropped, in draft order
    assert res.dropped == ["   ", "", "Cite the repo.", "One source of truth."]
    assert res.degraded is False

    # zero survivors degrade — verify never raises (the flag can't kill a run)
    empty = freeze(DraftOutput(principles=[]), mode="brownfield")
    assert empty.frozen == Constitution(drafted_by="empty", principles=[], digest="")
    assert empty.degraded is True
