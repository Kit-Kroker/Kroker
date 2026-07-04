"""Worker entrypoint.

Registers the FeatureWorkflow, plain activities, and the activities that
TemporalAgent generates for each Pydantic AI agent (model requests, tool
calls). Uses the Pydantic data converter so pipeline models serialize
cleanly through Temporal.
"""
from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from .activities import (
    create_worktree, deploy, evaluate_gate, merge_into_integration,
    open_pull_request, run_coding_task, run_test_suite,
    setup_integration_branch,
)
from .agents.roles import ALL_TEMPORAL_AGENTS
from .benchmarks.judge import judge_artifact, load_case_assets
from .benchmarks.recorder import record_benchmark
from .benchmarks.report import finalize_benchmark_report
from .benchmarks.workflow import BenchmarkWorkflow
from .workflows.feature import FeatureWorkflow

TASK_QUEUE = "ai-sdlc"


async def main() -> None:
    client = await Client.connect(
        "localhost:7233", data_converter=pydantic_data_converter)

    agent_activities = [
        act for ta in ALL_TEMPORAL_AGENTS for act in ta.temporal_activities
    ]
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[FeatureWorkflow, BenchmarkWorkflow],
        activities=[
            create_worktree, setup_integration_branch, merge_into_integration,
            run_coding_task, run_test_suite, open_pull_request, deploy,
            evaluate_gate, record_benchmark, judge_artifact,
            load_case_assets, finalize_benchmark_report,
            *agent_activities,
        ],
    )
    print(f"worker running on task queue {TASK_QUEUE!r}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
