"""Worker entrypoint.

Registers the FeatureWorkflow, plain activities, and the activities that
TemporalAgent generates for each Pydantic AI agent (model requests, tool
calls). Uses the Pydantic data converter so pipeline models serialize
cleanly through Temporal.
"""
from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()  # read .env in CWD — shell-neutral, works on any OS

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from .activities import (
    create_worktree, deploy, evaluate_gate, get_task_diff,
    measure_coverage, merge_into_integration, open_pull_request,
    run_coding_task, run_integration_checks, run_lint, run_test_suite,
    security_scan, setup_integration_branch,
)
from .agents.loader import load_registry, validate_registry
from .agents.roles import ALL_TEMPORAL_AGENTS
from .artifacts.read import load_session
from .artifacts.retention import apply_session_retention
from .benchmarks.judge import judge_artifact, load_case_assets
from .benchmarks.oracle import grade_oracle
from .benchmarks.recorder import record_benchmark
from .benchmarks.report import finalize_benchmark_report
from .benchmarks.workflow import BenchmarkWorkflow
from .harness.adapters import check_harness_versions
from .memoization.activities import cache_get, cache_put
from .memory.activities import (
    capture_watermark, recall_snapshot, reflect, retain,
)
from .observability.activities import export_run_artifacts
from .notify.activities import notify
from .pricing import price_usage
from .research.stage import plan_research
from .research.verify import verify_brief_activity
from .workflows.feature import FeatureWorkflow
from .workflows.reflect import ReflectWorkflow

TASK_QUEUE = "ai-sdlc"


async def main() -> None:
    # Fail closed: a registry that violates the ADR-6 family-inequality
    # invariant must never boot a worker (FR-204/US-5).
    validate_registry(load_registry())
    # E-24 (via E-35): warn — not fail — on harness CLI version drift.
    check_harness_versions()

    from .observability.logfire_setup import configure as configure_logfire
    if configure_logfire():
        logging.getLogger(__name__).info("logfire instrumentation enabled")

    client = await Client.connect(
        os.environ.get("TEMPORAL_HOST", "localhost:7233"),
        data_converter=pydantic_data_converter,
        plugins=[PydanticAIPlugin()])

    agent_activities = [
        act for ta in ALL_TEMPORAL_AGENTS for act in ta.temporal_activities
    ]
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[FeatureWorkflow, BenchmarkWorkflow, ReflectWorkflow],
        activities=[
            create_worktree, setup_integration_branch, merge_into_integration,
            run_coding_task, run_integration_checks, run_lint, run_test_suite,
            security_scan,
            measure_coverage,
            open_pull_request, deploy,
            evaluate_gate, get_task_diff, record_benchmark, judge_artifact,
            load_case_assets, finalize_benchmark_report,
            grade_oracle,
            recall_snapshot, retain, capture_watermark, reflect,
            cache_get, cache_put,
            export_run_artifacts,
            notify,
            price_usage,
            apply_session_retention,
            load_session,
            verify_brief_activity,
            plan_research,
            *agent_activities,
        ],
    )
    print(f"worker running on task queue {TASK_QUEUE!r}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
