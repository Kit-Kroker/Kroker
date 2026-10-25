"""PIN: stored benchmark records validate with BenchmarkRecord and trace is None (017 T007, US1)."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from sdlc.benchmarks.models import (
    AuditEvidence,
    BenchmarkOutcome,
    BenchmarkRecord,
    CriterionAudit,
    TraceBag,
)
from sdlc.benchmarks.record_builder import stage_record
from sdlc.benchmarks.recorder import _root as _resolve_records_root
from sdlc.core.models import PipelineConfig

_RECORDS_ROOT = Path(_resolve_records_root())
_RECORD_FILES = sorted(_RECORDS_ROOT.rglob("*.jsonl")) if _RECORDS_ROOT.is_dir() else []


def _is_removed_herdr_harness(exc: ValidationError) -> bool:
    """Tolerate the known legacy runs that used the removed 'herdr' harness."""
    errors = exc.errors()
    input_value = errors[0].get("input_value")
    return (
        len(errors) == 1
        and errors[0].get("loc") == ("harness",)
        and errors[0].get("type") == "enum"
        and (input_value is None or input_value == "herdr")
    )


def test_stored_benchmark_records_compat_and_trace_none():
    if not _RECORD_FILES:
        pytest.skip(
            f"no stored benchmark records under {_RECORDS_ROOT}; skipping stored compat PIN",
        )

    validated = 0
    for path in _RECORD_FILES:
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    record = BenchmarkRecord.model_validate_json(line)
                except ValidationError as exc:
                    if _is_removed_herdr_harness(exc):
                        continue
                    raise
                assert record.trace is None
                assert record.tasks_total is None
                assert record.blocking_checks is None
                validated += 1

    assert validated > 0


def test_stage_record_with_trace_round_trips():
    cfg = PipelineConfig()
    now = datetime.now(UTC)
    trace = TraceBag(
        traced_by_test=2,
        traced_by_file=1,
        traced_by_command=1,
        untraced=1,
        criteria_trace=[
            CriterionAudit(
                key="T1#1",
                bucket="test",
                evidence=[AuditEvidence(kind="test", ref="test_x", valid=True)],
            )
        ],
        truncated=False,
    )
    record = stage_record(
        cfg=cfg,
        stage="analyze",
        role="analyst",
        started=now,
        ended=now,
        quality_score=1.0,
        judge="contract",
        outcome=BenchmarkOutcome.PASS,
        model="test-model",
        trace=trace,
    )
    assert record.trace is not None
    assert record.trace.traced_by_test == 2
    assert record.trace.traced_by_file == 1
    assert record.trace.traced_by_command == 1
    assert record.trace.untraced == 1
    assert len(record.trace.criteria_trace) == 1
    assert record.trace.criteria_trace[0].key == "T1#1"

    # JSON round-trip validation
    dumped = record.model_dump_json()
    loaded = BenchmarkRecord.model_validate_json(dumped)
    assert loaded.trace == trace


def test_stage_record_with_tasks_total_and_blocking_checks_round_trips():
    cfg = PipelineConfig()
    now = datetime.now(UTC)
    record = stage_record(
        cfg=cfg,
        stage="plan",
        role="planner",
        started=now,
        ended=now,
        quality_score=1.0,
        judge="contract",
        outcome=BenchmarkOutcome.PASS,
        model="test-model",
        tasks_total=3,
        blocking_checks=["lint", "coverage"],
    )
    assert record.tasks_total == 3
    assert record.blocking_checks == ["lint", "coverage"]

    dumped = record.model_dump_json()
    loaded = BenchmarkRecord.model_validate_json(dumped)
    assert loaded.tasks_total == 3
    assert loaded.blocking_checks == ["lint", "coverage"]


@pytest.mark.parametrize(
    "module_name",
    [
        "sdlc.benchmarks.models",
        "sdlc.stages.analyze",
        "sdlc.stages.analyze.models",
        "sdlc.stages.code",
    ],
)
def test_fresh_interpreter_import_has_no_circular_dependency(module_name: str):
    """Pin that each module imports cleanly in a fresh interpreter without circular import."""
    cmd = [
        sys.executable,
        "-c",
        f"import {module_name}",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"Importing {module_name} failed: {res.stderr}"
