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

from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..agents.loader import HARNESS_ROLES, validate_run_roles
    from ..agents.roles import STAGE_MODELS
    from ..models import (BenchmarkConfig, GateConfig, GatePolicy, HarnessKind,
                          IdeaBrief, PipelineConfig, ProjectMode, RoleConfig)
    from ..workflows.feature import FeatureWorkflow
    from .judge import load_case_assets
    from .matrix import expand_matrix
    from .models import (BenchmarkCell, BenchmarkOutcome, BenchmarkRecord,
                         BenchmarkScope, CaseSpec, QualityScore, SpeedBag)
    from .oracle import OracleGrade, OracleInput, grade_oracle
    from .recorder import record_benchmark
    from .report import finalize_benchmark_report

CHILD_ACT = dict(start_to_close_timeout=timedelta(hours=4),
                 retry_policy=RetryPolicy(maximum_attempts=1))
RECORD_ACT = dict(start_to_close_timeout=timedelta(seconds=30),
                  retry_policy=RetryPolicy(maximum_attempts=5))
ORACLE_ACT = dict(start_to_close_timeout=timedelta(minutes=20),
                  retry_policy=RetryPolicy(maximum_attempts=1))


def _cell_config(base: PipelineConfig, idea: IdeaBrief, spec: CaseSpec,
                 cell: BenchmarkCell, bench_run_id: str,
                 rubrics: dict[str, str] | None = None) -> PipelineConfig:
    """Build a per-cell PipelineConfig from the cell's arm: each role in
    role_models is overridden to its model (harness roles carry the cell's
    harness + the base role's context budget / extra args; proposer roles are
    kind='proposer'). ADR-6 is validated for the resolved review roles before
    the cell runs — a violation raises, recording a failed cell rather than a
    silent bad run."""
    cfg = base.model_copy(deep=True)
    resolved = cell.role_models
    roles: dict[str, RoleConfig] = {}
    for role, model in resolved.items():
        if role in HARNESS_ROLES:
            rc = base.roles.get(role)
            roles[role] = RoleConfig(
                harness=cell.harness, model=model,
                context_budget_tokens=(rc.context_budget_tokens
                                       if rc else 30_000),
                extra_args=[*(rc.extra_args if rc else []),
                            *spec.extra_args_by_model.get(model, [])])
        else:
            roles[role] = RoleConfig(kind="proposer", model=model)
    cfg.roles = roles

    # Per-run ADR-6 (Task 3): resolve the review roles, defaulting any the arm
    # did not override to the registry model (STAGE_MODELS).
    adr6 = {
        "dev": resolved.get("dev", base.roles["dev"].model),
        "reviewer": resolved.get("reviewer", STAGE_MODELS["review"]),
    }
    if "deep_review" in STAGE_MODELS:
        adr6["deep_review"] = resolved.get("deep_review",
                                           STAGE_MODELS["deep_review"])
    validate_run_roles(adr6)

    # research provider is a property of the RUN, not the repo (registry keeps
    # provider: fake so CI needs no key); inject the real provider only when a
    # case asked for research.
    cfg.research_enabled = spec.research_enabled
    if spec.research_enabled:
        cfg.roles["research"] = RoleConfig(kind="research", provider="tavily")
    cfg.benchmark = BenchmarkConfig(
        case_id=spec.case_id, bench_run_id=bench_run_id,
        rubrics=dict(rubrics or {}), judge_model=spec.judge_model)
    # A benchmark matrix run is unattended — no human is present to click
    # approve for every cell. Auto-approve every gate rather than let
    # FeatureWorkflow block for gate_timeout_hours and auto-reject the cell.
    # default_gate_policy covers dynamic gates not named in `gates`.
    cfg.gates = {name: GateConfig(policy=GatePolicy.OFF) for name in cfg.gates}
    cfg.default_gate_policy = GatePolicy.OFF
    return cfg


def _oracle_record(base_cell: BenchmarkCell, grade: OracleGrade,
                   bench_run_id: str, run_id: str,
                   started: datetime, ended: datetime) -> BenchmarkRecord:
    """Build the stage='oracle' record from a grade. An integrity breach
    (held-out or language mismatch) sets .error so it surfaces in the report's
    failure section -- loud, never silent."""
    err = None
    if not grade.held_out_ok:
        err = "held-out breach: oracle path in produced diff"
    elif not grade.language_match:
        err = (f"language mismatch: manifest={grade.language_manifest} "
               f"detected={grade.language_detected}")
    outcome = (BenchmarkOutcome.PASS if (grade.score or 0.0) >= 1.0
               else BenchmarkOutcome.FAIL)
    return BenchmarkRecord(
        run_id=run_id, bench_run_id=bench_run_id, case_id=base_cell.case_id,
        scope=BenchmarkScope.ORACLE, stage="oracle", role="oracle",
        harness=base_cell.harness, model=base_cell.arm_name,
        quality=QualityScore(
            score=grade.score, judge="oracle",
            components={"passed": float(grade.passed),
                        "total": float(grade.total),
                        "held_out_ok": float(grade.held_out_ok),
                        "language_match": float(grade.language_match)}),
        speed=SpeedBag(wall_clock_s=(ended - started).total_seconds(),
                       started_at=started, ended_at=ended),
        outcome=outcome, error=err)


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
        # Load rubric text once (file I/O in the activity, not the workflow);
        # the same {stage: text} map is reused across every cell.
        rubrics = await workflow.execute_activity(
            load_case_assets, args=[spec.case_id, dict(spec.rubrics)],
            **RECORD_ACT)
        for cell in cells:
            child_id = f"{bench_run_id}/{cell.cell_id}"
            try:
                cfg = _cell_config(base, idea, spec, cell,
                                   bench_run_id=bench_run_id, rubrics=rubrics)
            except Exception as e:
                # an ADR-6-violating arm is rejected at the boundary — the cell
                # never runs, so there is nothing to grade; log and skip it
                workflow.logger.warning("cell %s rejected: %s", child_id, e)
                continue
            try:
                await workflow.execute_child_workflow(
                    FeatureWorkflow.run, args=[idea, cfg],
                    id=child_id, task_queue=workflow.info().task_queue,
                )
            except Exception as e:
                # a failed/escalated cell is a data point, not a crash
                workflow.logger.warning("cell %s failed: %s", child_id, e)

            if spec.language:
                started = workflow.now()
                grade = await workflow.execute_activity(
                    grade_oracle,
                    OracleInput(case_id=spec.case_id,
                                repo_url=spec.repo_url or "",
                                run_id=child_id, language=spec.language,
                                base_branch=idea.base_branch),
                    **ORACLE_ACT)
                await workflow.execute_activity(
                    record_benchmark,
                    _oracle_record(cell, grade, bench_run_id, child_id,
                                   started, workflow.now()),
                    **RECORD_ACT)

        # All file I/O (aggregate + write_report) is isolated in this
        # activity — workflow code stays deterministic and replay-safe.
        report_path = await workflow.execute_activity(
            finalize_benchmark_report, bench_run_id, **RECORD_ACT)
        return report_path
