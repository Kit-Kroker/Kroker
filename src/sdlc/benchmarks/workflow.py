"""BenchmarkWorkflow — the matrix runner.

For each (case × harness × model) cell, start a FeatureWorkflow child with
the cell's roles overridden and benchmark config set. Collect nothing in-
workflow — the record_benchmark activity writes each record to the file
store; after all cells complete, the finalize_benchmark_report activity
aggregates and writes the report.

Determinism rule: workflow code never touches the filesystem. All I/O
(reading records.jsonl, writing report.md) lives in the
finalize_benchmark_report activity, invoked via execute_activity.
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..models import (BenchmarkConfig, HarnessKind, IdeaBrief,
                          PipelineConfig, ProjectMode, RoleConfig)
    from ..workflows.feature import FeatureWorkflow
    from .matrix import expand_matrix
    from .models import CaseSpec
    from .report import finalize_benchmark_report

CHILD_ACT = dict(start_to_close_timeout=timedelta(hours=4),
                 retry_policy=RetryPolicy(maximum_attempts=1))
RECORD_ACT = dict(start_to_close_timeout=timedelta(seconds=30),
                  retry_policy=RetryPolicy(maximum_attempts=5))


def _cell_config(base: PipelineConfig, idea: IdeaBrief, spec: CaseSpec,
                 harness: HarnessKind, model: str,
                 bench_run_id: str) -> PipelineConfig:
    """Build a per-cell PipelineConfig: every role overridden to
    (harness, model), benchmark fields set so FeatureWorkflow records."""
    cfg = base.model_copy(deep=True)
    cfg.roles = {
        role: RoleConfig(harness=harness, model=model,
                         context_budget_tokens=rc.context_budget_tokens,
                         extra_args=rc.extra_args)
        for role, rc in base.roles.items()
    }
    cfg.benchmark = BenchmarkConfig(case_id=spec.case_id,
                                    bench_run_id=bench_run_id)
    return cfg


@workflow.defn
class BenchmarkWorkflow:
    @workflow.run
    async def run(self, spec_json: str) -> str:
        spec = CaseSpec.model_validate_json(spec_json)
        bench_run_id = workflow.info().workflow_id
        cells = expand_matrix(spec)
        idea = IdeaBrief(title=spec.case_id, description=spec.description,
                         mode=ProjectMode(spec.mode), repo_url=spec.repo_url)
        base = PipelineConfig()
        for cell in cells:
            cfg = _cell_config(base, idea, spec, cell.harness, cell.model,
                               bench_run_id=bench_run_id)
            child_id = f"{bench_run_id}/{cell.cell_id}"
            try:
                await workflow.execute_child_workflow(
                    FeatureWorkflow.run, idea, cfg,
                    id=child_id, task_queue=workflow.info().task_queue,
                )
            except Exception as e:
                # a failed/escalated cell is a data point, not a crash
                workflow.logger.warning("cell %s failed: %s", child_id, e)

        # All file I/O (aggregate + write_report) is isolated in this
        # activity — workflow code stays deterministic and replay-safe.
        report_path = await workflow.execute_activity(
            finalize_benchmark_report, bench_run_id, **RECORD_ACT)
        return report_path
