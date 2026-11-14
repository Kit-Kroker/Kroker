"""The `sdlc maintain` verbs (023a T021, contracts/cli.md).

Stateless shells over Temporal (FR-604, ADR-8): enable IS the project's
registration (FR-001) — it validates MaintenanceConfig, refuses a path
that is not a git work tree, and starts ``maint-<project>`` with a fresh
``MaintenanceState``. Exit contract: 0 success, 2 argparse usage error,
1 refused operation with a one-line reason on stderr.

There are deliberately no gate-policy flags (R9): the repair gate is
built in code, and `--gate-policy` / `--on-timeout` are rejected by
argparse as unknown arguments.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..maintenance.models import MaintenanceConfig, MaintenanceState, MaintenanceSummary
from ..maintenance.render import incidents_table
from ..task_queue import TASK_QUEUE


def register_maintain_subparsers(msub: argparse._SubParsersAction) -> None:
    """The maintain subtree: enable + incidents here; nudge/disable in T031."""
    en = msub.add_parser("enable")
    en.add_argument("project")
    en.add_argument("--repo", required=True, help="the project repository (a git work tree)")
    en.add_argument("--branch", default="main")
    en.add_argument("--advisory-source", choices=["none", "osv"], default="none")
    en.add_argument("--threshold", type=float, default=0.8)
    en.add_argument("--gate-timeout-hours", type=int, default=48)
    probe = en.add_argument_group("build probe (NFR-9)")
    probe_exclusive = probe.add_mutually_exclusive_group(required=True)
    probe_exclusive.add_argument(
        "--ack-unattended-build-probe",
        action="store_true",
        help="acknowledge the probe runs the repository's own code unattended",
    )
    probe_exclusive.add_argument(
        "--no-build-probe",
        dest="no_build_probe",
        action="store_true",
        help="disable the build probe for this project",
    )

    inc = msub.add_parser("incidents")
    inc.add_argument("project")
    inc.add_argument("--all", action="store_true", help="include terminal incidents")
    inc.add_argument("--state", action="store_true", help="print the loop summary")


def _is_git_work_tree(repo: str) -> bool:
    # A checkout has .git as a directory; a linked worktree as a file
    # pointing at the real gitdir. Both mean "git knows this path".
    return (Path(repo).expanduser() / ".git").exists()


async def _enable(args: argparse.Namespace, client) -> int:  # noqa: ANN001
    repo = str(Path(args.repo).expanduser().resolve())
    if not _is_git_work_tree(repo):
        print(f"not a git work tree: {repo}", file=sys.stderr)
        return 1
    cfg = MaintenanceConfig(
        project=args.project,
        repo_dir=repo,
        default_branch=args.branch,
        build_probe=not args.no_build_probe,
        ack_unattended_build_probe=args.ack_unattended_build_probe,
        advisory_source=args.advisory_source,
        threshold=args.threshold,
        gate_timeout_hours=args.gate_timeout_hours,
    )
    from ..workflows.maintenance import MaintenanceWorkflow

    try:
        await client.start_workflow(
            MaintenanceWorkflow.run,
            MaintenanceState(config=cfg),
            id=f"maint-{cfg.project}",
            task_queue=TASK_QUEUE,
        )
    except Exception as e:  # noqa: BLE001 -- refused, never a traceback
        if "already started" in str(e).lower() or type(e).__name__ == (
            "WorkflowExecutionAlreadyStartedError"
        ):
            print(f"already enabled: maint-{cfg.project}", file=sys.stderr)
        else:
            print(f"enable failed: {type(e).__name__}: {e}"[:300], file=sys.stderr)
        return 1
    print(f"enabled maint-{cfg.project}")
    return 0


async def _incidents(args: argparse.Namespace, client) -> int:  # noqa: ANN001
    from ..maintenance.models import Incident

    handle = client.get_workflow_handle(f"maint-{args.project}")
    try:
        incidents = await handle.query("incidents", result_type=list[Incident])
    except Exception as e:  # noqa: BLE001
        print(f"not enabled: {args.project} ({type(e).__name__})", file=sys.stderr)
        return 1
    print(incidents_table(incidents, include_terminal=args.all))
    if args.state:
        summary = await handle.query("maintenance_state", result_type=MaintenanceSummary)
        print(
            f"project {summary.project}  cycle {summary.cycle}  "
            f"baseline {'recorded' if summary.baseline_recorded else 'pending'}  "
            f"running_cycle {summary.running_cycle}  open_gates {summary.open_gates}  "
            f"ack_unattended_build_probe {summary.ack_unattended_build_probe}"
        )
        if summary.not_collected_streak:
            print(
                "not_collected_streak "
                + " ".join(f"{k}={v}" for k, v in sorted(summary.not_collected_streak.items()))
            )
    return 0


async def run_maintain(args: argparse.Namespace, client) -> int:  # noqa: ANN001
    if args.maintain_cmd == "enable":
        return await _enable(args, client)
    if args.maintain_cmd == "incidents":
        return await _incidents(args, client)
    print(f"unknown maintain command: {getattr(args, 'maintain_cmd', None)}", file=sys.stderr)
    return 2
