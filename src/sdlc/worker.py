"""Worker entrypoint.

Registers the GraphWorkflow (020 deleted the legacy pipeline workflow), plain
activities, and the durable activities the TemporalDurability capability
generates for each Pydantic AI agent (model requests, tool calls). Uses
the Pydantic data converter so pipeline models serialize cleanly through
Temporal.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dotenv import load_dotenv

load_dotenv()  # read .env in CWD — shell-neutral, works on any OS

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from pydantic_ai.durable_exec.temporal import TemporalDurability
from temporalio.client import Client
from temporalio.worker import Worker

from .agents.loader import load_registry, validate_registry
from .agents.payload_guard import has_payload_guard
from .agents.roles import ALL_TEMPORAL_AGENTS
from .agents.runner import SdlcPydanticAIPlugin
from .artifacts.read import load_diff, load_session
from .artifacts.retention import apply_session_retention
from .assessment.activities import (
    assess_risk,
    assessment_resolve_tree,
    discover_context,
    discover_finalize,
    discover_lock,
    discover_memo_load,
    discover_memo_store,
    load_blueprint,
    load_dispositions,
    risk_memo_load,
    risk_memo_store,
    scan_ci,
    scan_config_infra,
    scan_coverage,
    scan_entrypoints,
    scan_frontend,
    scan_packages,
    scan_schema,
    scan_security_static,
    scan_sensitivity,
    scan_testability,
    scan_tests_inventory,
    verify_discover_refs,
    verify_risk_refs,
)
from .benchmarks.axis import measure_code_axis
from .benchmarks.cell import summarize_cell
from .benchmarks.judge import judge_artifact, load_case_assets
from .benchmarks.oracle import grade_oracle
from .benchmarks.provenance import resolve_provenance
from .benchmarks.recorder import record_benchmark
from .benchmarks.report import finalize_benchmark_report
from .benchmarks.workflow import BenchmarkWorkflow
from .board.activities import (
    attach_task_evidence,
    publish_artifact_version,
    set_task_authoritative,
    sync_plan_tasks,
)
from .calibration.activities import calibration_verdict, record_calibration_samples
from .converter import sdlc_data_converter
from .crew.activities import (
    checkpoint_round,
    load_crew,
    prepare_crew,
    read_round,
    run_crew_turn,
)
from .crew.loader import validate_crew_clis
from .harness.registry import check_harness_versions
from .maintenance.activities import probe_repair_child
from .memoization.activities import cache_get, cache_put
from .memory.activities import (
    capture_watermark,
    recall_snapshot,
    reflect,
    retain,
)
from .notify.activities import notify
from .observability.activities import export_run_artifacts
from .pools import (
    HARNESS_ACTIVITIES,
    PoolBootPlan,
    boot_plan_from_env,
    pool_identity,
)
from .pricing import price_usage
from .stages import STAGE_MODULES
from .task_queue import TASK_QUEUE  # noqa: F401 -- re-export
from .triage.activities import (
    triage_baseline,
    triage_build_probe,
    triage_dependencies,
    triage_misconfig,
    triage_outliers,
    triage_resolve_commit,
    triage_scaffold,
    triage_secrets,
)
from .validators.activities import paths_exist
from .vcs import (
    build_verification_branch,
    check_test_drift,
    cleanup_run_worktrees,
    create_worktree,
    get_task_diff,
    is_ancestor,
    merge_into_integration,
    prepare_base_worktree,
    read_committed_bytes,
    remove_verification_tree,
    setup_integration_branch,
)
from .vcs.janitor import worktree_janitor
from .workflows.assessment import AssessmentWorkflow
from .workflows.crew import CrewTaskWorkflow
from .workflows.deployment import DeploymentWorkflow
from .workflows.graph import GraphWorkflow
from .workflows.maintenance import MaintenanceKickWorkflow, MaintenanceWorkflow
from .workflows.reflect import ReflectWorkflow
from .workflows.tidyup import TidyUpWorkflow
from .workflows.triage import TriageWorkflow


def get_worker_activities() -> Sequence[Callable[..., Any]]:
    """Compose all activities registered on the Temporal worker.

    Combines vertical slice activities from STAGE_MODULES, horizontal domain
    activities, and the durable activities each agent's TemporalDurability
    capability registers (003: via the agent's own registration surface —
    `from_agent(a)` is the bound handle whose activities these are; no
    hand-maintained name list, FR-007).
    """
    stage_activities = [act for mod in STAGE_MODULES for act in mod.ACTIVITIES]
    agent_activities: list[Callable[..., Any]] = []
    for agent in ALL_TEMPORAL_AGENTS:
        durability = TemporalDurability.from_agent(agent)
        if durability is None:
            # Unreachable while roles.py builds every agent through the
            # loader's durability factory (whose fail-closed checks would
            # have rejected a capability-free agent first); kept explicit so
            # a future agent that skips the factory still fails HERE, at
            # boot, naming the agent — not mid-run as an unregistered
            # activity type.
            raise RuntimeError(
                f"agent '{agent.name}' has no TemporalDurability capability; "
                f"build it through build_agents(durability_factory=...)"
            )
        # 007 T005 (D3): a durable agent without the proposer payload guard
        # is a partial guard described as complete (FR-002) — same boot-time
        # refusal as the durability check above, so a future agent that
        # skips the loader's list fails HERE, naming the agent, not mid-run
        # as an oversized payload left to the workflow engine.
        if not has_payload_guard(agent):
            raise RuntimeError(
                f"agent '{agent.name}' has no ProposerPayloadGuard capability; "
                f"build it through build_agents(durability_factory=...)"
            )
        agent_activities.extend(durability.temporal_activities)
    return [
        *stage_activities,
        create_worktree,
        cleanup_run_worktrees,
        setup_integration_branch,
        merge_into_integration,
        build_verification_branch,
        prepare_base_worktree,
        # 023b (T014): the maintenance loop's client-side probe and the two
        # read-only/tidy-up verification activities (R2/R4/R8).
        probe_repair_child,
        is_ancestor,
        remove_verification_tree,
        prepare_crew,
        run_crew_turn,
        read_round,
        checkpoint_round,
        load_crew,
        read_committed_bytes,
        get_task_diff,
        # 024 T005 (R2 latent defect): vcs.ACTIVITIES has always listed
        # check_test_drift and code/step.py schedules it, but it was never
        # registered here — a containment-on repair attempt would schedule
        # an activity no worker serves. Registered, in the harness class.
        check_test_drift,
        paths_exist,
        record_benchmark,
        judge_artifact,
        load_case_assets,
        finalize_benchmark_report,
        grade_oracle,
        measure_code_axis,
        summarize_cell,
        resolve_provenance,
        recall_snapshot,
        retain,
        capture_watermark,
        reflect,
        cache_get,
        cache_put,
        record_calibration_samples,
        calibration_verdict,
        export_run_artifacts,
        notify,
        price_usage,
        apply_session_retention,
        load_session,
        load_diff,
        publish_artifact_version,
        sync_plan_tasks,
        set_task_authoritative,
        attach_task_evidence,
        triage_baseline,
        triage_secrets,
        triage_build_probe,
        triage_dependencies,
        triage_scaffold,
        triage_misconfig,
        triage_outliers,
        triage_resolve_commit,
        assessment_resolve_tree,
        discover_context,
        discover_finalize,
        discover_lock,
        discover_memo_load,
        discover_memo_store,
        load_blueprint,
        scan_packages,
        scan_schema,
        scan_entrypoints,
        scan_frontend,
        scan_security_static,
        scan_config_infra,
        scan_sensitivity,
        scan_tests_inventory,
        scan_coverage,
        scan_testability,
        scan_ci,
        verify_discover_refs,
        assess_risk,
        load_dispositions,
        risk_memo_load,
        risk_memo_store,
        verify_risk_refs,
        *agent_activities,
    ]


def core_activities() -> list[Callable[..., Any]]:
    """The registered activities in the core class (024 T007).

    Everything ``get_worker_activities()`` registers whose defn name is not
    in ``pools.HARNESS_ACTIVITIES`` — order preserved.
    """
    return [
        act
        for act in get_worker_activities()
        if getattr(act, "__temporal_activity_definition").name not in HARNESS_ACTIVITIES
    ]


def harness_activities() -> list[Callable[..., Any]]:
    """The registered activities in the harness class (024 T007).

    The ``HARNESS_ACTIVITIES`` subset of ``get_worker_activities()``,
    order preserved — the classification test pins that every harness
    name is registered, so this never silently drops one.
    """
    return [
        act
        for act in get_worker_activities()
        if getattr(act, "__temporal_activity_definition").name in HARNESS_ACTIVITIES
    ]


def graph_boot_problems() -> list[str]:
    """E-72 D2 / E-74 D14: the registry self-check plus handler coverage, at boot."""
    from .graph.node_types import NODE_TYPES, check_node_types
    from .workflows.graph_catalog import NOT_EXECUTABLE
    from .workflows.graph_nodes import HANDLERS

    problems = list(check_node_types())
    expected = sorted(NODE_TYPES)
    covered = sorted({*HANDLERS, *NOT_EXECUTABLE})
    if expected != covered:
        problems.append(f"handler coverage mismatch: registry {expected} vs handled {covered}")
    return problems


_ALL_WORKFLOWS = [
    GraphWorkflow,
    BenchmarkWorkflow,
    ReflectWorkflow,
    DeploymentWorkflow,
    TriageWorkflow,
    TidyUpWorkflow,
    AssessmentWorkflow,
    CrewTaskWorkflow,
    MaintenanceWorkflow,
    MaintenanceKickWorkflow,
]


def _build_workers(client: Client, plan: PoolBootPlan) -> list[Worker]:
    """Construct the plan's Worker(s); main runs them, the boot tests
    construct through here.

    025 Part B repair (T020 STOP): a sync ``@activity.defn`` —
    paths_exist, 023 FR-205 — cannot construct without an
    activity_executor. Executor over making the activity async:
    paths_exist does blocking filesystem stats, which belong on a thread
    pool, not the worker's event loop (Temporal's guidance for blocking
    sync activities)."""
    executor = ThreadPoolExecutor()
    workers: list[Worker] = []
    if plan.harness_worker:
        # G-4: the harness worker is built (and starts) first.
        cap_kwargs: dict[str, Any] = (
            {} if plan.cap is None else {"max_concurrent_activities": plan.cap}
        )
        assert plan.queue is not None  # the plan's refusals guarantee it
        workers.append(
            Worker(
                client,
                task_queue=plan.queue,
                workflows=[],
                activities=harness_activities(),
                identity=pool_identity("harness"),
                activity_executor=executor,
                **cap_kwargs,
            )
        )
        cap_part = f", cap={plan.cap}" if plan.cap is not None else ""
        print(f"worker running on task queue {plan.queue!r} (pool=harness{cap_part})")
    if plan.core_worker:
        single = plan.queue is None
        # Single pool is today, exactly (G-1): same activities, same line,
        # no identity key. `all`+queue keeps everything on core (pre-024
        # clients may send harness work unrouted); `core` is core-only.
        acts = get_worker_activities() if single or plan.harness_worker else core_activities()
        id_kwargs: dict[str, Any] = {} if single else {"identity": pool_identity("core")}
        workers.append(
            Worker(
                client,
                task_queue=TASK_QUEUE,
                workflows=_ALL_WORKFLOWS,
                activities=acts,
                activity_executor=executor,
                **id_kwargs,
            )
        )
        pool_part = "" if single else " (pool=core)"
        print(f"worker running on task queue {TASK_QUEUE!r}{pool_part}")
    return workers


async def main() -> None:
    # 024 T009: the pool plan comes first, before anything connects —
    # every refuse row of the R5 truth table exits here (worker-boot G-2).
    try:
        plan = boot_plan_from_env()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    # Fail closed: a registry that violates the ADR-6 family-inequality
    # invariant must never boot a worker (FR-204/US-5).
    validate_registry(load_registry())
    # E-88 step 2: same rule one level down. A crew role naming a CLI this
    # image does not carry must kill the worker here, not forty minutes and
    # one billed lead into a run.
    validate_crew_clis()
    # E-74: a registry the graph interpreter cannot run must never boot a worker.
    graph_problems = graph_boot_problems()
    if graph_problems:
        raise SystemExit("graph registry unhealthy: " + "; ".join(graph_problems))
    # E-24 (via E-35): warn — not fail — on harness CLI version drift.
    # The boot checks above run in every pool mode (worker-boot G-1).
    check_harness_versions()

    from .observability.logfire_setup import configure as configure_logfire

    if configure_logfire():
        logging.getLogger(__name__).info("logfire instrumentation enabled")

    client = await Client.connect(
        os.environ.get("TEMPORAL_HOST", "localhost:7233"),
        data_converter=sdlc_data_converter,
        plugins=[SdlcPydanticAIPlugin()],
    )

    workers = _build_workers(client, plan)

    # A-terminal backstop: sweeps run dirs whose workflow is gone and has
    # been untouched past the grace period (killed/crashed runs — the
    # workflow-side teardown cannot fire for those). Harness-capable modes
    # only (R5: all and harness; core never mutates worktrees).
    janitor = asyncio.create_task(worktree_janitor(client)) if plan.janitor else None
    try:
        await asyncio.gather(*(w.run() for w in workers))
    finally:
        if janitor is not None:
            janitor.cancel()


if __name__ == "__main__":
    asyncio.run(main())
