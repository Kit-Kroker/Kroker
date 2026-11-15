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
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from ..maintenance.models import MaintenanceConfig, MaintenanceState, MaintenanceSummary
from ..maintenance.render import incidents_table
from ..task_queue import TASK_QUEUE


def register_maintain_subparsers(msub: argparse._SubParsersAction) -> None:
    """The maintain subtree: enable, incidents, nudge and disable
    (contracts/cli.md)."""
    en = msub.add_parser(
        "enable",
        epilog="disable followed by re-enable resets the 7-day start window "
        "(the rolling window lives in the workflow's durable state, which a "
        "re-enable starts fresh).",
    )
    en.add_argument("project")
    en.add_argument("--repo", required=True, help="the project repository (a git work tree)")
    en.add_argument("--branch", default="main")
    en.add_argument("--advisory-source", choices=["none", "osv"], default="none")
    en.add_argument("--threshold", type=float, default=0.8)
    en.add_argument("--gate-timeout-hours", type=int, default=48)
    en.add_argument(
        "--execute",
        action="store_true",
        help="turn on Execute/Report for this project: approved plans run as "
        "repair children and incidents re-verify. Requires the unattended "
        "build-probe acknowledgement, gh on PATH, an origin remote and a "
        "resolvable default branch",
    )
    en.add_argument(
        "--max-starts-per-cycle",
        type=_bounded("--max-starts-per-cycle", 1, 3),
        default=None,
        help="child starts allowed per cycle, 1-3 (default 1); only with --execute",
    )
    en.add_argument(
        "--max-starts-per-window",
        type=_bounded("--max-starts-per-window", 1, 10),
        default=None,
        help="child starts per rolling 7 days, 1-10 (default 3); only with --execute",
    )
    en.add_argument(
        "--max-reopens",
        type=_bounded("--max-reopens", 0, 2),
        default=None,
        help="reopen rounds per incident, 0-2 (default 2); only with --execute",
    )
    en.add_argument(
        "--child-timeout-hours",
        type=_bounded("--child-timeout-hours", 1, 168),
        default=None,
        help="repair child timeout in hours, 1-168 (default 24); only with --execute",
    )
    probe = en.add_argument_group("build probe (NFR-9)")
    probe_exclusive = probe.add_mutually_exclusive_group(required=False)
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

    for verb, help_text in (
        ("nudge", "trigger one maintenance cycle on an enabled project"),
        ("disable", "withdraw open gates and end the project's loop"),
    ):
        v = msub.add_parser(verb, help=help_text)
        v.add_argument("project")


def _is_git_work_tree(repo: str) -> bool:
    # A checkout has .git as a directory; a linked worktree as a file
    # pointing at the real gitdir. Both mean "git knows this path".
    return (Path(repo).expanduser() / ".git").exists()


def _bounded(flag: str, lo: int, hi: int) -> Callable[[str], int]:
    """An argparse type for a bounded integer cap (contracts/cli.md): out of
    range exits 2 with the flag and its range named, not the pydantic exit-1
    path."""

    def convert(text: str) -> int:
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{flag} expects an integer, got {text!r}") from None
        if not lo <= value <= hi:
            raise argparse.ArgumentTypeError(f"{flag} must be {lo}-{hi}, got {value}")
        return value

    return convert


def _probe_refusal(args: argparse.Namespace) -> str | None:
    """Exactly one probe flag is required (NFR-9); --execute narrows it to
    the acknowledgement (R14). None means the argv may proceed."""
    ack, no_probe = args.ack_unattended_build_probe, args.no_build_probe
    if ack and no_probe:
        return "--ack-unattended-build-probe and --no-build-probe are mutually exclusive"
    if args.execute:
        if no_probe:
            return (
                "--execute cannot run with --no-build-probe: unattended execution "
                "requires the build probe and its acknowledgement "
                "(--ack-unattended-build-probe)"
            )
        if not ack:
            return (
                "--execute requires --ack-unattended-build-probe: the repair children "
                "run the repository's own code unattended"
            )
    elif not ack and not no_probe:
        return "exactly one of --ack-unattended-build-probe / --no-build-probe is required"
    return None


def _origin_url(repo: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo, "config", "--get", "remote.origin.url"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _branch_resolves(repo: str, branch: str) -> bool:
    for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"):
        result = subprocess.run(
            ["git", "-C", repo, "rev-parse", "--verify", "--quiet", ref],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True
    return False


def _execute_refusal(args: argparse.Namespace, cap_kwargs: dict[str, int], repo: str) -> str | None:
    """The cap-without-execute and --execute preconditions
    (contracts/cli.md), each refusal naming what is missing. Order is
    stable so a cell with exactly one item absent gets exactly that item
    named. ``repo`` is the un-resolved path on purpose: the origin/branch
    checks run BEFORE the work-tree check so a usage-class refusal never
    depends on the repo being valid."""
    caps = {
        "--max-starts-per-cycle": cap_kwargs.get("max_starts_per_cycle"),
        "--max-starts-per-window": cap_kwargs.get("max_starts_per_window"),
        "--max-reopens": cap_kwargs.get("max_reopens"),
        "--child-timeout-hours": cap_kwargs.get("child_timeout_hours"),
    }
    given = [flag for flag, value in caps.items() if value is not None]
    if given and not args.execute:
        return f"{given[0]} is only meaningful with --execute"
    if not args.execute:
        return None
    if shutil.which("gh") is None:
        return "--execute requires gh on PATH: the repair child's merge gate is a GitHub PR"
    if not _origin_url(repo):
        return f"--execute requires an origin remote in {repo}: children push and open PRs"
    if not _branch_resolves(repo, args.branch):
        return (
            f"--execute requires default_branch to resolve: no local branch or "
            f"origin/{args.branch} for {args.branch!r}"
        )
    return None


async def _enable(args: argparse.Namespace, client) -> int:  # noqa: ANN001
    # contracts/cli.md: usage-class refusals (exit 2) precede filesystem
    # checks (exit 1) — the argv shape is validated before the repo is.
    probe_problem = _probe_refusal(args)
    if probe_problem is not None:
        print(probe_problem, file=sys.stderr)
        return 2
    cap_kwargs: dict[str, int] = {}
    for dest in (
        "max_starts_per_cycle",
        "max_starts_per_window",
        "max_reopens",
        "child_timeout_hours",
    ):
        value = getattr(args, dest)
        if value is not None:
            cap_kwargs[dest] = value
    execute_problem = _execute_refusal(args, cap_kwargs, str(Path(args.repo).expanduser()))
    if execute_problem is not None:
        print(execute_problem, file=sys.stderr)
        return 2
    repo = str(Path(args.repo).expanduser().resolve())
    if not _is_git_work_tree(repo):
        print(f"not a git work tree: {repo}", file=sys.stderr)
        return 1
    try:
        cfg = MaintenanceConfig(
            project=args.project,
            repo_dir=repo,
            default_branch=args.branch,
            build_probe=not args.no_build_probe,
            ack_unattended_build_probe=args.ack_unattended_build_probe,
            advisory_source=args.advisory_source,
            threshold=args.threshold,
            gate_timeout_hours=args.gate_timeout_hours,
            execute=args.execute,
            **cap_kwargs,
        )
    except Exception as e:  # noqa: BLE001 -- a refusal, never a traceback
        # contracts/cli.md: one line on stderr — pydantic's multi-line
        # ValidationError flattens, field names included.
        reason = " ".join(str(e).split())[:300]
        print(f"invalid configuration: {reason}", file=sys.stderr)
        return 1
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


async def _signal_verb(verb: str, args: argparse.Namespace, client) -> int:  # noqa: ANN001
    """nudge/disable (FR-004/018): stateless shells that signal maint-<p> —
    only enable starts a workflow (FR-604). A loop that is absent or already
    finished is `not enabled`; any other failure is a one-line refusal."""
    project = args.project
    try:
        handle = client.get_workflow_handle(f"maint-{project}")
        await handle.signal(verb)
    except Exception as e:  # noqa: BLE001 -- a refusal, never a traceback
        reason = " ".join(str(e).split())
        if "not found" in reason.lower() or "already completed" in reason.lower():
            print(f"not enabled: {project}", file=sys.stderr)
        else:
            print(f"{verb} failed: {reason}"[:300], file=sys.stderr)
        return 1
    if verb == "disable":
        print(f"disabling maint-{project}")
    else:
        print(f"nudged maint-{project}")
    return 0


async def run_maintain(args: argparse.Namespace, client) -> int:  # noqa: ANN001
    if args.maintain_cmd == "enable":
        return await _enable(args, client)
    if args.maintain_cmd == "incidents":
        return await _incidents(args, client)
    if args.maintain_cmd in ("nudge", "disable"):
        return await _signal_verb(args.maintain_cmd, args, client)
    print(f"unknown maintain command: {getattr(args, 'maintain_cmd', None)}", file=sys.stderr)
    return 2
