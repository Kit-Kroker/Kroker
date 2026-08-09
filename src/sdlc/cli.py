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
  python -m sdlc.cli triage --repo /path/to/repo [--commit HEAD]
  python -m sdlc.cli triage --repo /path/to/repo --no-build-probe
  python -m sdlc.cli triage show --id triage-myrepo-20260809T101500Z
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
from datetime import datetime, timezone

from dotenv import load_dotenv

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from .models import GateOutcome, IdeaBrief, PipelineConfig, ProjectMode
from .worker import TASK_QUEUE
from .workflows.feature import FeatureWorkflow
from .workflows.triage import TriageInput, TriageWorkflow


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def triage_workflow_id(repo: str, now: datetime | None = None) -> str:
    """A distinct id per triage RUN, not per repository.

    Spec D5 asked for `triage-<slug>-<short-sha>`, which is not available here:
    the sha is resolved by triage_resolve_commit INSIDE the workflow, and the
    id must exist before the workflow starts. A UTC timestamp supplies the
    distinctness the sha was there to provide.

    Distinctness is load-bearing, not cosmetic. Temporal refuses to start a
    workflow whose id is already RUNNING, so a bare `triage-<slug>` means a
    triage parked on the readiness gate (HARD by default, 48h) blocks the next
    triage of that repository -- and E-44's assess -> fix -> RE-TRIAGE loop is
    the first thing that would hit it.
    """
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"triage-{slug(os.path.basename(repo))}-{stamp}"


_OUTCOME = {
    "approve": GateOutcome.APPROVE,
    "reject": GateOutcome.REJECT,
    "revise": GateOutcome.REVISE,
}

DECISION_CMDS = ("approve", "reject", "revise", "answer")


def _needs_temporal_client(args) -> bool:
    """True if this invocation must connect to Temporal. calibrate is fully
    local (calibrate <rubric> is offline file+judge work; calibrate capture is
    a stub that only prints a seam message) — mirroring how every `benchmark`
    subcommand is client-free."""
    local_only = (
        args.cmd == "benchmark"
        or (args.cmd == "schedules" and args.sched_cmd == "list")
        or (args.cmd == "eval" and args.target != "capture")
        or args.cmd == "calibrate"
        or args.cmd == "capability")
    return not local_only


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
    s.add_argument("--role-model", action="append", default=[],
                   dest="role_model", metavar="ROLE=MODEL",
                   help="override a role's model, e.g. --role-model "
                        "architect=anthropic:claude-opus-4-8 (repeatable)")

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

    bp = sub.add_parser("benchmark")
    bsub = bp.add_subparsers(dest="bench_cmd", required=True)
    br = bsub.add_parser("run")
    br.add_argument("--case", required=True)
    br.add_argument("--gate-policy", choices=["off", "soft", "hard"],
                    default=None, dest="gate_policy",
                    help="override the case's gate_policy for every gate "
                         "in the child FeatureWorkflow")
    bd = bsub.add_parser("drift"); bd.add_argument("--since", type=int, default=168)
    bs = bsub.add_parser("score")
    bsg = bs.add_mutually_exclusive_group(required=True)
    bsg.add_argument("--bench", help="one bench_run_id")
    bsg.add_argument("--case", help="every bench run for one case")
    bsg.add_argument("--all", action="store_true", dest="all_",
                     help="every bench run for every case")
    bs.add_argument("--out", default=None,
                    help="output dir (default: <root>/<selector>/score)")
    bs.add_argument("--weights", default=None, metavar="Q,C,S",
                    help="composite weights as quality,cost,speed; "
                         "defaults to benchmarks/config.yaml")

    bx = bsub.add_parser("experiment")
    bxsub = bx.add_subparsers(dest="exp_cmd", required=True)
    bxn = bxsub.add_parser("new")
    bxn.add_argument("--name", required=True)
    bxn.add_argument("--axis", required=True,
                     choices=["prompt", "model", "harness", "schema",
                              "tool_org", "memory"])
    bxn.add_argument("--change", required=True,
                     help="one line: what is under test")
    bxn.add_argument("--baseline", required=True, help="a bench_run_id")
    bxn.add_argument("--commit", default="")
    bxn.add_argument("--hypothesis", default="")
    bxc = bxsub.add_parser("compare")
    bxc.add_argument("--experiment", required=True)
    bxc.add_argument("--candidate", required=True, help="a bench_run_id")

    ev = sub.add_parser("eval")
    ev.add_argument("target", help="a role name, or 'capture'")
    ev.add_argument("--from", dest="from_run", help="run id (capture only)")
    ev.add_argument("--case", default=None)
    ev.add_argument("--against", default="HEAD")
    ev.add_argument("--n", type=int, default=1, dest="k")
    ev.add_argument("--judge-model", default=None, dest="judge_model")

    cal = sub.add_parser("calibrate")
    cal.add_argument("target", help="a rubric/role name, or 'capture'")
    cal.add_argument("--rubric", default=None,
                     help="rubric/role (capture only)")
    cal.add_argument("--case", default=None, help="case id (capture only)")
    cal.add_argument("--from", dest="from_run", default=None,
                     help="run id (capture only)")
    cal.add_argument("--judge-model", default=None, dest="judge_model")
    cal.add_argument("--epsilon", type=float, default=0.15)
    cal.add_argument("--threshold", type=float, default=0.75)

    from .capability.cli import add_capability_parser
    add_capability_parser(sub)

    tr = sub.add_parser("triage")
    trsub = tr.add_subparsers(dest="triage_cmd")
    tr.add_argument("--repo", help="path to an already-cloned repository")
    tr.add_argument("--commit", default="HEAD")
    tr.add_argument("--no-build-probe", action="store_true",
                    dest="no_build_probe",
                    help="skip the one signal that executes the repo's own "
                         "code; readiness becomes INDETERMINATE")
    tr.add_argument("--advisory-source", default="none",
                    help="'osv' enables a declared outbound vulnerability "
                         "lookup; default collects nothing")
    ts = trsub.add_parser("show")
    ts.add_argument("--id", required=True)

    args = p.parse_args()

    if args.cmd == "eval" and args.target == "capture" \
            and not (args.from_run and args.case):
        print("eval capture requires --from <run_id> and --case <name>")
        raise SystemExit(1)

    if args.cmd == "revise" and not args.comment:
        print("revise requires --comment <guidance>")
        raise SystemExit(1)

    client = None
    if _needs_temporal_client(args):
        client = await Client.connect(
            os.environ.get("TEMPORAL_HOST", "localhost:7233"),
            data_converter=pydantic_data_converter)

    if args.cmd == "start":
        from .cli_roles import build_role_overrides, parse_role_models
        cfg = PipelineConfig()
        if args.role_model:
            try:
                overrides = parse_role_models(args.role_model)
                cfg.roles.update(build_role_overrides(overrides))
            except Exception as e:      # ValueError / RegistryError
                print(f"invalid --role-model: {e}")
                raise SystemExit(1)
        wf_id = f"feature-{slug(args.title)}"
        handle = await client.start_workflow(
            FeatureWorkflow.run,
            args=[
                IdeaBrief(title=args.title, description=args.description,
                          mode=ProjectMode(args.mode), repo_url=args.repo),
                cfg,
                None,
            ],
            id=wf_id, task_queue=TASK_QUEUE,
        )
        print(f"started {handle.id}")
        return

    if args.cmd == "benchmark":
        if args.bench_cmd == "score":
            from .benchmarks.cli import dispatch_score
            print(dispatch_score(bench=args.bench, case=args.case,
                                 all_=args.all_, out=args.out,
                                 weights=args.weights))
            return
        if args.bench_cmd == "experiment":
            from .benchmarks.cli import (dispatch_experiment_compare,
                                         dispatch_experiment_new)
            if args.exp_cmd == "new":
                print(dispatch_experiment_new(
                    name=args.name, axis=args.axis, change=args.change,
                    baseline=args.baseline, commit=args.commit,
                    hypothesis=args.hypothesis))
            else:
                print(dispatch_experiment_compare(
                    experiment=args.experiment, candidate=args.candidate))
            return
        if args.bench_cmd == "run":
            from .benchmarks.cli import _run_matrix
            print(await _run_matrix(args.case, args.gate_policy))
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

    if args.cmd == "calibrate":
        if args.target == "capture":
            print("calibrate capture requires a live Temporal client and a "
                  "run id; run via the operator CLI. See the E-36 spec: the "
                  "pure normalizer is tested, the live artifact-history adapter "
                  "is operator-runtime. Hand-authoring fixtures under "
                  "benchmarks/calibration/<rubric>/ is the offline path.")
            return
        from .benchmarks.cli import dispatch_calibrate
        print(dispatch_calibrate(args.target, judge_model=args.judge_model,
                                 epsilon=args.epsilon, threshold=args.threshold))
        return

    if args.cmd == "capability":
        from .capability.cli import run_capability
        raise SystemExit(run_capability(args))

    if args.cmd == "triage" and args.triage_cmd == "show":
        handle = client.get_workflow_handle(args.id)
        # Query by METHOD, not by name: a string query carries no result type,
        # so the converter returns raw decoded JSON (a dict) and every model
        # method on it is an AttributeError. transport.py:139 queries by name
        # and validates with a TypeAdapter for the same reason.
        report = await handle.query(TriageWorkflow.triage)
        print("no triage yet" if report is None
              else report.model_dump_json(indent=2))
        return

    if args.cmd == "triage":
        if not args.repo:
            raise SystemExit("triage requires --repo")
        repo = os.path.abspath(args.repo)
        wf_id = triage_workflow_id(repo)
        handle = await client.start_workflow(
            TriageWorkflow.run,
            TriageInput(repo_dir=repo, commit=args.commit,
                        build_probe=not args.no_build_probe,
                        advisory_source=args.advisory_source),
            id=wf_id, task_queue=TASK_QUEUE)
        print(f"started {handle.id}")
        print("NOTE: the build probe executes this repository's own code as "
              "the worker user. Operator-run only (NFR-9).")
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
