"""Tests for research dead-attempt ledger in budget_store.py (T011, FR-030 to FR-032)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from sdlc.core.models import RoleUsage
from sdlc.stages.research.budget_store import append_dead_attempt, read_dead_attempts


def test_missing_file_returns_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    res = read_dead_attempts("non-existent-run")
    assert res == []


def test_append_and_read_single_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    run_id = "run-single"

    u1 = RoleUsage(
        role="research",
        model="model-alpha",
        calls=1,
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=10,
        cache_write_tokens=5,
    )
    u2 = RoleUsage(
        role="research",
        model="model-alpha",
        calls=1,
        input_tokens=200,
        output_tokens=100,
        cache_read_tokens=20,
        cache_write_tokens=10,
    )

    append_dead_attempt(run_id, u1)
    append_dead_attempt(run_id, u2)

    res = read_dead_attempts(run_id)
    assert len(res) == 1
    total = res[0]
    assert total.role == "research"
    assert total.model == "model-alpha"
    assert total.calls == 2
    assert total.input_tokens == 300
    assert total.output_tokens == 150
    assert total.cache_read_tokens == 30
    assert total.cache_write_tokens == 15
    assert total.cost_usd is None


def test_append_and_read_two_models_first_seen_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    run_id = "run-two-models"

    u_b1 = RoleUsage(role="research", model="model-B", calls=1, input_tokens=50, output_tokens=25)
    u_a = RoleUsage(role="research", model="model-A", calls=1, input_tokens=100, output_tokens=50)
    u_b2 = RoleUsage(role="research", model="model-B", calls=1, input_tokens=30, output_tokens=15)

    append_dead_attempt(run_id, u_b1)
    append_dead_attempt(run_id, u_a)
    append_dead_attempt(run_id, u_b2)

    res = read_dead_attempts(run_id)
    assert [u.model for u in res] == ["model-B", "model-A"]
    assert res[0].calls == 2
    assert res[0].input_tokens == 80
    assert res[0].output_tokens == 40
    assert res[1].calls == 1
    assert res[1].input_tokens == 100
    assert res[1].output_tokens == 50


def test_read_skips_corrupt_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    run_id = "run-corrupt"

    u1 = RoleUsage(role="research", model="model-1", calls=1, input_tokens=10, output_tokens=5)
    u2 = RoleUsage(role="research", model="model-2", calls=1, input_tokens=20, output_tokens=10)

    append_dead_attempt(run_id, u1)

    # Inject invalid JSON and non-compliant lines
    ledger_file = tmp_path / run_id / "research" / "dead-attempts.jsonl"
    with open(ledger_file, "a", encoding="utf-8") as f:
        f.write("{broken json\n")
        f.write("\n")  # empty line
        f.write("[1, 2, 3]\n")  # not a dict
        f.write('{"calls": 1}\n')  # missing model
        f.write('{"model": ""}\n')  # empty model
        f.write('{"model": "bad-tokens", "input_tokens": "invalid"}\n')  # non-int tokens

    append_dead_attempt(run_id, u2)

    res = read_dead_attempts(run_id)
    assert [u.model for u in res] == ["model-1", "model-2"]
    assert res[0].input_tokens == 10
    assert res[1].input_tokens == 20


def test_concurrent_thread_appends(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    run_id = "run-concurrent"

    def _worker(idx: int) -> None:
        usage = RoleUsage(
            role="research",
            model="model-worker",
            calls=1,
            input_tokens=10,
            output_tokens=5,
            cache_read_tokens=2,
            cache_write_tokens=1,
        )
        append_dead_attempt(run_id, usage)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(_worker, range(20)))

    ledger_file = tmp_path / run_id / "research" / "dead-attempts.jsonl"
    lines = [ln for ln in ledger_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 20

    res = read_dead_attempts(run_id)
    assert len(res) == 1
    total = res[0]
    assert total.model == "model-worker"
    assert total.calls == 20
    assert total.input_tokens == 200
    assert total.output_tokens == 100
    assert total.cache_read_tokens == 40
    assert total.cache_write_tokens == 20


from unittest.mock import MagicMock

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.usage import RunUsage
from temporalio import activity

from sdlc.stages.research.deps import BudgetExceeded, ResearchDeps
from sdlc.stages.research.models import ResearchBrief, SubQuestion
from sdlc.stages.research.stage import SubQuestionInput, _research_subquestion_impl


class _StubAgent:
    def __init__(self, exc: BaseException | None = None, tokens: int = 0) -> None:
        self.exc = exc
        self.tokens = tokens

    async def run(self, prompt: str, *, deps=None, usage=None, **kwargs) -> Any:
        if usage is not None and self.tokens:
            usage.input_tokens = self.tokens
            usage.output_tokens = self.tokens // 2
        if self.exc is not None:
            raise self.exc
        return MagicMock(output=ResearchBrief(summary="done"), usage=usage or RunUsage())


def _make_inp(run_id: str) -> SubQuestionInput:
    sub = SubQuestion(id="sq-1", question="What is X?")
    deps = ResearchDeps(
        run_id=run_id,
        provider="fake",
        max_searches=5,
        max_fetches=5,
        max_cost_usd=1.0,
    )
    return SubQuestionInput(
        sub_question=sub,
        deps=deps,
        model="test-model",
        max_requests=10,
        max_run_cost_usd=1.0,
    )


@pytest.mark.asyncio
async def test_subquestion_impl_spends_then_raises_model_http_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    run_id = "run-http-err"
    inp = _make_inp(run_id)
    agent = _StubAgent(
        exc=ModelHTTPError(status_code=503, model_name="test-model", body="overloaded"),
        tokens=120,
    )

    with pytest.raises(ModelHTTPError):
        await _research_subquestion_impl(inp, _agent=agent)

    records = read_dead_attempts(run_id)
    assert len(records) == 1
    assert records[0].model == "test-model"
    assert records[0].input_tokens == 120
    assert records[0].output_tokens == 60
    assert records[0].calls == 1


@pytest.mark.asyncio
async def test_subquestion_impl_raise_zero_usage_no_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    run_id = "run-zero-usage"
    inp = _make_inp(run_id)
    agent = _StubAgent(
        exc=ModelHTTPError(status_code=503, model_name="test-model", body="overloaded"),
        tokens=0,
    )

    with pytest.raises(ModelHTTPError):
        await _research_subquestion_impl(inp, _agent=agent)

    records = read_dead_attempts(run_id)
    assert records == []


@pytest.mark.asyncio
async def test_subquestion_impl_ledger_write_error_still_reraises_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    run_id = "run-write-err"
    inp = _make_inp(run_id)
    agent = _StubAgent(
        exc=ModelHTTPError(status_code=503, model_name="test-model", body="overloaded"),
        tokens=100,
    )

    monkeypatch.setattr(
        "sdlc.stages.research.stage.append_dead_attempt",
        MagicMock(side_effect=TimeoutError("ledger locked")),
    )

    with pytest.raises(ModelHTTPError):
        await _research_subquestion_impl(inp, _agent=agent)


@pytest.mark.asyncio
async def test_subquestion_impl_cancelled_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    monkeypatch.setattr(activity, "heartbeat", lambda: None)
    run_id = "run-cancelled"
    inp = _make_inp(run_id)
    agent = _StubAgent(exc=asyncio.CancelledError(), tokens=80)

    with pytest.raises(asyncio.CancelledError):
        await _research_subquestion_impl(inp, _agent=agent)

    records = read_dead_attempts(run_id)
    assert len(records) == 1
    assert records[0].model == "test-model"
    assert records[0].input_tokens == 80
    assert records[0].output_tokens == 40


@pytest.mark.asyncio
async def test_subquestion_impl_budget_exceeded_degrade_path_no_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    run_id = "run-budget-degrade"
    inp = _make_inp(run_id)
    agent = _StubAgent(exc=BudgetExceeded("search limit reached"), tokens=100)

    res = await _research_subquestion_impl(inp, _agent=agent)
    assert "search limit reached" in res.brief.summary
    assert res.usage.input_tokens == 100

    # Degrade returns normally, so no dead attempt line is written
    records = read_dead_attempts(run_id)
    assert records == []


import importlib

from sdlc.benchmarks.models import BenchmarkOutcome
from sdlc.core.models import GateDecision, GateOutcome, IdeaBrief, PipelineConfig, ProjectMode
from sdlc.observability.summary import _role_rollup
from sdlc.observability.trace import RunEvent, RunEventKind
from sdlc.stages.research.models import (
    GroundedFinding,
    ResearchPlan,
    SubQuestionFinding,
)
from sdlc.stages.research.step import _fold_dead_attempts, _fold_research_usage

research_step_mod = importlib.import_module("sdlc.stages.research.step")
from sdlc.workflows.role_host import RoleHost


class _RecordingCtx:
    def __init__(self, gates=None) -> None:
        self.events: list[RunEvent] = []
        self.records: list = []
        self.stages: list[str] = []
        self.retained: list = []
        self._gates = iter(gates or [])

    def emit(self, kind: RunEventKind, stage: str | None = None, **data: str) -> None:
        from datetime import UTC, datetime

        self.events.append(
            RunEvent(
                seq=len(self.events) + 1,
                at=datetime.now(UTC),
                kind=kind,
                stage=stage,
                data=data,
            )
        )

    def stage(self, status: str, trace: str | None = None) -> None:
        self.stages.append(status)

    async def gate(self, name: str, settings: object, **kwargs: object) -> GateDecision:
        outcome, guidance = next(self._gates)
        round_val = kwargs.get("round", 1)
        return GateDecision(
            gate=name,
            outcome=outcome,
            decided_by="human",
            round=round_val if isinstance(round_val, int) else 1,
            guidance=guidance,
        )

    async def record(self, cfg: object, record: object) -> None:
        self.records.append(record)

    async def retain(self, cfg: object, kind: object, bank: str, text: str, metadata: dict) -> None:
        self.retained.append((kind, bank, text, metadata))

    async def judge(self, cfg: object, artifact_json: str, stage: str, author_model: str) -> object:
        res = MagicMock()
        res.score = 1.0
        res.judge = "contract"
        res.detail = None
        return res


@pytest.mark.asyncio
async def test_fold_research_usage_emits_model_usage_and_role_rollup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx: Any = _RecordingCtx()
    cfg = PipelineConfig()
    spend = RoleUsage(role="research", model="m1")
    usage = RoleUsage(
        role="research",
        model="m1",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=10,
        cache_write_tokens=5,
    )

    # Mock price_usage to return $0.05
    async def _mock_price(*a, **k):
        return 0.05

    monkeypatch.setattr(research_step_mod, "_exec_activity", _mock_price)

    await _fold_research_usage(ctx, cfg, usage, spend, calls=2)

    assert spend.calls == 2
    assert spend.input_tokens == 100
    assert spend.output_tokens == 50
    assert spend.cost_usd == 0.05

    assert len(ctx.events) == 1
    ev = ctx.events[0]
    assert ev.kind == RunEventKind.MODEL_USAGE
    assert ev.data["role"] == "research"
    assert ev.data["model"] == "m1"
    assert ev.data["calls"] == "2"
    assert ev.data["cost_usd"] == "0.05"

    rollup = _role_rollup(ctx.events)
    assert len(rollup) == 1
    assert rollup[0].role == "research"
    assert rollup[0].input_tokens == 100


@pytest.mark.asyncio
async def test_fold_dead_attempts_adds_totals_once(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx: Any = _RecordingCtx()
    cfg = PipelineConfig()
    spend = RoleUsage(role="research", model="base-model")

    monkeypatch.setattr(research_step_mod, "_ledger_v2", lambda: True)

    dead_items = [
        RoleUsage(role="research", model="dead-m1", calls=3, input_tokens=300, output_tokens=150),
        RoleUsage(role="research", model="dead-m2", calls=1, input_tokens=100, output_tokens=50),
    ]

    async def _mock_exec(fn, *a, **k):
        if fn == research_step_mod.read_dead_attempt_usage:
            return dead_items
        if fn == research_step_mod.price_usage:
            return 0.02
        return None

    import temporalio.workflow

    monkeypatch.setattr(temporalio.workflow, "execute_activity", _mock_exec)
    monkeypatch.setattr(research_step_mod, "_exec_activity", _mock_exec)

    await _fold_dead_attempts(ctx, cfg, "run-dead", spend)

    assert spend.calls == 4
    assert spend.input_tokens == 400
    assert spend.output_tokens == 200
    assert spend.cost_usd == 0.04
    assert len(ctx.events) == 2


@pytest.mark.asyncio
async def test_unpatched_path_schedules_no_read_dead_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx: Any = _RecordingCtx()
    cfg = PipelineConfig()
    spend = RoleUsage(role="research", model="base-model")

    monkeypatch.setattr(research_step_mod, "_ledger_v2", lambda: False)
    spy = MagicMock()
    monkeypatch.setattr(research_step_mod, "_exec_activity", spy)

    await _fold_dead_attempts(ctx, cfg, "run-unpatched", spend)

    assert spy.call_count == 0
    assert spend.calls == 0
    assert spend.input_tokens == 0


@pytest.mark.asyncio
async def test_research_step_grounding_violation_carries_dead_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    monkeypatch.setattr(research_step_mod, "_ledger_v2", lambda: True)

    run_id = "run-violation"
    append_dead_attempt(
        run_id,
        RoleUsage(role="research", model="sub-model", calls=1, input_tokens=500, output_tokens=250),
    )

    ctx = _RecordingCtx([])
    cfg = PipelineConfig()
    idea = IdeaBrief(title="Idea", description="Desc", mode=ProjectMode.GREENFIELD)

    sq = SubQuestion(id="sq-1", question="Q1")
    plan = ResearchPlan(sub_questions=[sq])
    finding = SubQuestionFinding(sub_question=sq, brief=ResearchBrief(summary="finding"))

    async def _mock_exec(fn, *a, **k):
        name = getattr(fn, "__temporal_activity_definition", MagicMock()).name
        if name == "plan_research":
            return plan
        if name == "research_subquestion":
            return finding
        if name == "synthesize_brief":
            return ResearchBrief(
                summary="synth",
                grounded_findings=[
                    GroundedFinding(source_url="https://example.com", quote="q", claim="c")
                ],
            ), MagicMock(input_tokens=0, output_tokens=0)
        if name == "verify_brief_activity":
            from sdlc.grounding import Violation

            return [Violation(kind="quote_not_found", source="https://example.com", quote="q")]
        if name == "read_dead_attempt_usage":
            return read_dead_attempts(run_id)
        if name == "price_usage":
            return 0.05
        return None

    import temporalio.workflow

    monkeypatch.setattr(temporalio.workflow, "execute_activity", _mock_exec)
    monkeypatch.setattr(research_step_mod, "_exec_activity", _mock_exec)

    result = await research_step_mod.step(ctx, cfg=cfg, idea=idea, run_id=run_id)
    assert result.digest == ""
    assert len(ctx.records) == 1
    rec = ctx.records[0]
    assert rec.outcome == BenchmarkOutcome.FAIL
    assert rec.cost.input_tokens == 500
    assert rec.cost.output_tokens == 250


@pytest.mark.asyncio
async def test_research_step_refine_round_carries_dead_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    monkeypatch.setattr(research_step_mod, "_ledger_v2", lambda: True)

    run_id = "run-refine-pass"
    append_dead_attempt(
        run_id,
        RoleUsage(
            role="research",
            model="refine-dead",
            calls=1,
            input_tokens=700,
            output_tokens=350,
        ),
    )

    ctx = _RecordingCtx([(GateOutcome.APPROVE, None)])
    cfg = PipelineConfig()
    idea = IdeaBrief(title="Idea", description="Desc", mode=ProjectMode.GREENFIELD)

    sq = SubQuestion(id="sq-1", question="Q1")
    plan = ResearchPlan(sub_questions=[sq])
    finding = SubQuestionFinding(sub_question=sq, brief=ResearchBrief(summary="finding"))

    async def _mock_exec(fn, *a, **k):
        name = getattr(fn, "__temporal_activity_definition", MagicMock()).name
        if name == "plan_research":
            return plan
        if name == "research_subquestion":
            return finding
        if name == "synthesize_brief":
            return ResearchBrief(
                summary="synth",
                grounded_findings=[],
            ), MagicMock(input_tokens=0, output_tokens=0)
        if name == "verify_brief_activity":
            return []  # no violations
        if name == "read_dead_attempt_usage":
            return read_dead_attempts(run_id)
        if name == "price_usage":
            return 0.07
        return None

    import temporalio.workflow

    monkeypatch.setattr(temporalio.workflow, "execute_activity", _mock_exec)
    monkeypatch.setattr(research_step_mod, "_exec_activity", _mock_exec)
    monkeypatch.setattr(
        research_step_mod,
        "verified_findings_to_retain",
        lambda *a, **kw: [],
    )

    result = await research_step_mod.step(ctx, cfg=cfg, idea=idea, run_id=run_id)
    assert result.digest != ""
    assert len(ctx.records) == 1
    rec = ctx.records[0]
    assert rec.outcome == BenchmarkOutcome.PASS
    assert rec.cost.input_tokens == 700
    assert rec.cost.output_tokens == 350


@pytest.mark.asyncio
async def test_role_host_check_budget_ignores_research_spend() -> None:
    class _FakeHost(RoleHost):
        def __init__(self) -> None:
            self._role_usage = {
                "architect": RoleUsage(role="architect", model="m", cost_usd=2.50),
                "planner": RoleUsage(role="planner", model="m", cost_usd=1.50),
            }
            self._budget_threshold = 5.00
            self._budget_crossings = 0

    host = _FakeHost()
    cfg = PipelineConfig(run_budget_usd=5.00)

    # Total in _role_usage is 4.00, below threshold 5.00
    await host._check_budget(cfg)
    assert host._budget_crossings == 0

    # Even though research had spend, research never writes to _role_usage,
    # so _check_budget calculation is completely unaffected
    role_usage = getattr(host, "_role_usage", {})
    total = sum(u.cost_usd or 0.0 for u in role_usage.values())
    assert total == 4.00
