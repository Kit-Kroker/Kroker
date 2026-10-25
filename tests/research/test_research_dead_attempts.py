"""Tests for research dead-attempt ledger in budget_store.py (T011, FR-030 to FR-032)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
