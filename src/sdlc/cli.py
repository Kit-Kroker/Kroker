"""Operator CLI — the human side of the loop.

  python -m sdlc.cli start   --title "Add SSO" --mode brownfield --repo <url>
  python -m sdlc.cli status  --id feature-add-sso
  python -m sdlc.cli inbox
  python -m sdlc.cli answer  --id feature-add-sso --q Q1 --text "Use OIDC"
  python -m sdlc.cli approve --id feature-add-sso --gate architecture
  python -m sdlc.cli revise  --id feature-add-sso --gate architecture --comment "split task 3"
  python -m sdlc.cli reject  --id feature-add-sso --gate merge --comment "..."
  python -m sdlc.cli schedules list
  python -m sdlc.cli schedules apply --dry-run
  python -m sdlc.cli schedules apply
  python -m sdlc.cli eval capture --from feature-add-sso --case add-login-greenfield
  python -m sdlc.cli eval reviewer --against HEAD
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re

from dotenv import load_dotenv

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from .models import GateOutcome, IdeaBrief, PipelineConfig, ProjectMode
from .worker import TASK_QUEUE
from .workflows.feature import FeatureWorkflow


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


_OUTCOME = {
    "approve": GateOutcome.APPROVE,
    "reject": GateOutcome.REJECT,
    "revise": GateOutcome.REVISE,
}

DECISION_CMDS = ("approve", "reject", "revise", "answer")


def add_decision_parsers(sub) -> None:
    """The four human-in-the-loop verbs. No --round: the round is read off
    the pending item, so a reply can never land on a stale round (E-7)."""
    for name in ("approve", "reject", "revise"):
        g = sub.add_parser(name)
        g.add_argument("--id", required=True)
        g.add_argument("--gate", default=None,
                       help="gate name; omit if exactly one gate is pending")
        g.add_argument("--comment", default=None,
                       help="comment; required for revise (becomes guidance)")

    a = sub.add_parser("answer")
    a.add_argument("--id", required=True)
    a.add_argument("--q", default=None,
                   help="question id; omit if exactly one is pending")
    a.add_argument("--text", required=True)


def selector_for(args):
    """Map parsed args to the surface-neutral (Selector, Reply) pair."""
    from .channels.contract import Reply
    from .channels.transport import Selector

    if args.cmd == "answer":
        return Selector(reply_kind="text", name=args.q), Reply(text=args.text)
    return (Selector(reply_kind="gate", name=args.gate),
            Reply(outcome=_OUTCOME[args.cmd], text=args.comment))


async def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start")
    s.add_argument("--title", required=True)
    s.add_argument("--description", default="")
    s.add_argument("--mode", choices=["greenfield", "brownfield"],
                   default="brownfield")
    s.add_argument("--repo")

    add_decision_parsers(sub)

    st = sub.add_parser("status")
    st.add_argument("--id", required=True)

    sub.add_parser("inbox")

    sc = sub.add_parser("schedules")
    scsub = sc.add_subparsers(dest="sched_cmd", required=True)
    scsub.add_parser("list")
    sa = scsub.add_parser("apply")
    sa.add_argument("--dry-run", action="store_true",
                    help="print the plan without touching Temporal")
    sa.add_argument("--prune", action="store_true",
                    help="delete server schedules that have no yaml asset")

    from .benchmarks.cli import build_parser as _bench_parser
    # delegate benchmark subcommands to the benchmarks.cli parser
    bp = sub.add_parser("benchmark")
    bsub = bp.add_subparsers(dest="bench_cmd", required=True)
    br = bsub.add_parser("run"); br.add_argument("--case", required=True)
    bd = bsub.add_parser("drift"); bd.add_argument("--since", type=int, default=168)
    bf = bsub.add_parser("report"); bf.add_argument("--bench", required=True)

    ev = sub.add_parser("eval")
    ev.add_argument("target", help="a role name, or 'capture'")
    ev.add_argument("--from", dest="from_run", help="run id (capture only)")
    ev.add_argument("--case", default=None)
    ev.add_argument("--against", default="HEAD")
    ev.add_argument("--n", type=int, default=1, dest="k")
    ev.add_argument("--judge-model", default=None, dest="judge_model")

    args = p.parse_args()

    if args.cmd == "eval" and args.target == "capture" \
            and not (args.from_run and args.case):
        print("eval capture requires --from <run_id> and --case <name>")
        raise SystemExit(1)

    if args.cmd == "revise" and not args.comment:
        print("revise requires --comment <guidance>")
        raise SystemExit(1)

    client = None
    _local_only = (args.cmd == "benchmark"
                   or (args.cmd == "schedules" and args.sched_cmd == "list")
                   or (args.cmd == "eval" and args.target != "capture"))
    if not _local_only:
        client = await Client.connect(
            os.environ.get("TEMPORAL_HOST", "localhost:7233"),
            data_converter=pydantic_data_converter)

    if args.cmd == "start":
        wf_id = f"feature-{slug(args.title)}"
        handle = await client.start_workflow(
            FeatureWorkflow.run,
            args=[
                IdeaBrief(title=args.title, description=args.description,
                          mode=ProjectMode(args.mode), repo_url=args.repo),
                PipelineConfig(),
            ],
            id=wf_id, task_queue=TASK_QUEUE,
        )
        print(f"started {handle.id}")
        return

    if args.cmd == "benchmark":
        from .benchmarks.cli import dispatch_report
        if args.bench_cmd == "report":
            print(dispatch_report(args.bench))
            return
        if args.bench_cmd == "run":
            from .benchmarks.cli import _run_matrix
            print(await _run_matrix(args.case))
            return
        if args.bench_cmd == "drift":
            print("drift requires a live Temporal client; see ARCHITECTURE.md section 8.")
            return

    if args.cmd == "schedules":
        from .schedules.apply import apply_changes, fetch_existing, format_plan
        from .schedules.loader import load_schedules
        from .schedules.reconcile import plan_changes

        desired = load_schedules()
        if args.sched_cmd == "list":
            if not desired:
                print("no schedule assets found")
                return
            for a in desired:
                print(f"{a.id:<24} {a.spec.cron!r} {a.spec.timezone} "
                      f"-> {a.action.workflow} banks={a.action.banks}")
            return
        existing = await fetch_existing(client)
        changes = plan_changes(desired, existing)
        if args.dry_run:
            print(format_plan(changes))
            return
        for line in await apply_changes(client, desired, changes,
                                        prune=args.prune):
            print(line)
        return

    if args.cmd == "eval":
        from .eval.cli import default_judge_model, run_capture, run_eval
        from .eval.compare import EvalError
        if args.target == "capture":
            paths = await run_capture(client, args.from_run, args.case)
            print(f"captured {len(paths)} fixtures:")
            for p in paths:
                print(f"  {p}")
            return
        try:
            judge = args.judge_model or default_judge_model()
            print(run_eval(args.target, against=args.against, case=args.case,
                           k=args.k, judge_model=judge))
        except EvalError as e:
            print(f"eval error: {e}")
            raise SystemExit(1)
        return

    if args.cmd == "inbox":
        from .channels.inbox import fetch_inbox, render_inbox
        print(render_inbox(await fetch_inbox(client)))
        return

    handle = client.get_workflow_handle_for(FeatureWorkflow.run, args.id)

    if args.cmd in DECISION_CMDS:
        from .channels.transport import Ambiguous, NoMatch, resolve, submit
        selector, reply = selector_for(args)
        try:
            pending = await resolve(handle, selector)
        except (NoMatch, Ambiguous) as e:
            print(e.message)
            if isinstance(e, Ambiguous):
                flag = "--q" if args.cmd == "answer" else "--gate"
                print(f"re-run with {flag} <name>")
            raise SystemExit(1)
        print((await submit(handle, pending, reply)).message)
        return

    if args.cmd == "status":
        print(await handle.query(FeatureWorkflow.status))


if __name__ == "__main__":
    asyncio.run(main())
