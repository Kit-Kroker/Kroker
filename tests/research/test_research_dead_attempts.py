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
