"""Operator CLI — the human side of the loop.

  python -m sdlc.cli start   --title "Add SSO" --mode brownfield --repo <url>
  python -m sdlc.cli status  --id feature-add-sso
  python -m sdlc.cli answer  --id feature-add-sso --q Q1 --text "Use OIDC"
  python -m sdlc.cli approve --id feature-add-sso --gate architecture
  python -m sdlc.cli reject  --id feature-add-sso --gate merge --comment "..."
"""
from __future__ import annotations

import argparse
import asyncio
import re

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from .models import GateDecision, GateOutcome, IdeaBrief, ProjectMode
from .worker import TASK_QUEUE
from .workflows.feature import FeatureWorkflow


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


async def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start")
    s.add_argument("--title", required=True)
    s.add_argument("--description", default="")
    s.add_argument("--mode", choices=["greenfield", "brownfield"],
                   default="brownfield")
    s.add_argument("--repo")

    for name in ("approve", "reject"):
        g = sub.add_parser(name)
        g.add_argument("--id", required=True)
        g.add_argument("--gate", required=True)
        g.add_argument("--comment", default=None)

    a = sub.add_parser("answer")
    a.add_argument("--id", required=True)
    a.add_argument("--q", required=True)
    a.add_argument("--text", required=True)

    st = sub.add_parser("status")
    st.add_argument("--id", required=True)

    from .benchmarks.cli import build_parser as _bench_parser
    # delegate benchmark subcommands to the benchmarks.cli parser
    bp = sub.add_parser("benchmark")
    bsub = bp.add_subparsers(dest="bench_cmd", required=True)
    br = bsub.add_parser("run"); br.add_argument("--case", required=True)
    bd = bsub.add_parser("drift"); bd.add_argument("--since", type=int, default=168)
    bf = bsub.add_parser("report"); bf.add_argument("--bench", required=True)

    args = p.parse_args()
    client = None
    if args.cmd != "benchmark":
        client = await Client.connect(
            "localhost:7233", data_converter=pydantic_data_converter)

    if args.cmd == "start":
        wf_id = f"feature-{slug(args.title)}"
        handle = await client.start_workflow(
            FeatureWorkflow.run,
            IdeaBrief(title=args.title, description=args.description,
                      mode=ProjectMode(args.mode), repo_url=args.repo),
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
            print(asyncio.run(_run_matrix(args.case)))
            return
        if args.bench_cmd == "drift":
            print("drift requires a live Temporal client; see ARCHITECTURE.md §8.")
            return

    handle = client.get_workflow_handle_for(FeatureWorkflow.run, args.id)

    if args.cmd in ("approve", "reject"):
        await handle.signal(
            FeatureWorkflow.submit_gate_decision,
            GateDecision(gate=args.gate,
                         outcome=(GateOutcome.APPROVE if args.cmd == "approve"
                                  else GateOutcome.REJECT),
                         decided_by="human", comments=args.comment),
        )
        print(f"{args.cmd}d gate {args.gate!r} on {args.id}")
    elif args.cmd == "answer":
        await handle.signal(FeatureWorkflow.answer_question,
                            args=[args.q, args.text])
        print(f"answered {args.q} on {args.id}")
    elif args.cmd == "status":
        print(await handle.query(FeatureWorkflow.status))


if __name__ == "__main__":
    asyncio.run(main())
