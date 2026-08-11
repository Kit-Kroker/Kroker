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
  python -m sdlc.cli benchmark import-deveval --src /path/DevEval/benchmark_data/python
  python -m sdlc.cli benchmark verify-case --case deveval-lice
  python -m sdlc.cli eval clarify --case add-login-greenfield --gate
  python -m sdlc.cli eval planner --case cat-cafe-monitoring --n 5
  python -m sdlc.cli triage --repo /path/to/repo [--commit HEAD]
  python -m sdlc.cli triage --repo /path/to/repo --no-build-probe
  python -m sdlc.cli triage show --id triage-myrepo-20260809T101500Z
  python -m sdlc.cli tidyup --repo /path/to/repo
  python -m sdlc.cli tidyup select --id tidyup-myrepo-20260809T101500Z --identities a,b
  python -m sdlc.cli tidyup show --id tidyup-myrepo-20260809T101500Z
  python -m sdlc.cli assess --repo /path/to/repo [--commit HEAD]
  python -m sdlc.cli assess show --id assess-myrepo-20260810T101500Z
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
from .workflows.assessment import AssessmentInput, AssessmentWorkflow
from .workflows.feature import FeatureWorkflow
from .workflows.tidyup import TidyUpInput, TidyUpWorkflow
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


def tidyup_workflow_id(repo: str, now: datetime | None = None) -> str:
    """A distinct id per tidy-up RUN, for the same reason triage_workflow_id
    carries a stamp (E-42 D5): Temporal refuses to start a workflow whose id
    is already RUNNING, so a bare `tidyup-<slug>` would let one tidy-up parked
    on the gate block the next one for that repository."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"tidyup-{slug(os.path.basename(repo))}-{stamp}"


def assess_workflow_id(repo: str, now: datetime | None = None) -> str:
    """A distinct id per assessment RUN, for the same reason
    triage_workflow_id carries a stamp (E-42 D5): Temporal refuses to start a
    workflow whose id is already RUNNING, so a bare `assess-<slug>` would let
    one assessment parked on its child's readiness gate (HARD by default,
    48h) block the next assessment of that repository."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"assess-{slug(os.path.basename(repo))}-{stamp}"


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
        or args.cmd == "eval"
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


def build_parser() -> argparse.ArgumentParser:
    """The operator CLI's argument parser. Extracted to module level so the
    tidyup-cli wiring test can exercise the same parser main() uses, and so
    `tidyup select`/`tidyup show` subcommands resolve identically in tests
    and at runtime."""
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
    bi = bsub.add_parser("import-deveval")
    bi.add_argument("--src", required=True,
                    help="a DevEval benchmark_data/<language> directory")
    bi.add_argument("--repo", default=None,
                    help="import only this repository (default: all)")
    bi.add_argument("--out", default=None,
                    help="destination cases dir (default: benchmarks/cases)")
    bi.add_argument("--judge-model", default="google:gemini-3.5-flash",
                    dest="judge_model")
    bv = bsub.add_parser("verify-case")
    bv.add_argument("--case", required=True, help="a case_id")
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
    ev.add_argument("target", help="a role name")
    ev.add_argument("--case", default=None)
    ev.add_argument("--against", default="HEAD")
    ev.add_argument("--n", type=int, default=1, dest="k")
    ev.add_argument("--judge-model", default=None, dest="judge_model")
    ev.add_argument("--gate", action="store_true",
                    help="exit non-zero on a failing verdict")
    ev.add_argument("--view", action="store_true",
                    help="open the promptfoo viewer after the run")

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

    tu = sub.add_parser("tidyup")
    tusub = tu.add_subparsers(dest="tidyup_cmd")
    tu.add_argument("--repo", help="path to an already-cloned repository")
    tu.add_argument("--commit", default="HEAD")
    tu.add_argument("--no-build-probe", action="store_true",
                    dest="no_build_probe")
    tu.add_argument("--advisory-source", default="none")
    tu.add_argument("--base-branch", default="main", dest="base_branch")
    tu.add_argument("--max-fix-runs", type=int, default=10,
                    dest="max_fix_runs",
                    help="cap on fix runs; the excess is deferred and "
                         "recorded, never dropped silently")
    tus = tusub.add_parser("select")
    tus.add_argument("--id", required=True)
    tus.add_argument("--identities", required=True,
                     help="comma-separated finding identities to fix; "
                          "omit the verb entirely to fix all of them")
    tush = tusub.add_parser("show")
    tush.add_argument("--id", required=True)

    asr = sub.add_parser("assess")
    asrsub = asr.add_subparsers(dest="assess_cmd")
    asr.add_argument("--repo", help="path to an already-cloned repository")
    asr.add_argument("--commit", default="HEAD")
    asr.add_argument("--no-build-probe", action="store_true",
                     dest="no_build_probe",
                     help="skip the one signal that executes the repo's own "
                          "code; readiness becomes INDETERMINATE, so "
                          "admission then requires a human override")
    asr.add_argument("--advisory-source", default="none",
                     help="'osv' enables a declared outbound vulnerability "
                          "lookup; default collects nothing")
    ash = asrsub.add_parser("show")
    ash.add_argument("--id", required=True)
    return p


async def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()

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
        if args.bench_cmd == "import-deveval":
            from .benchmarks.cli import dispatch_import_deveval
            print(dispatch_import_deveval(
                src=args.src, out=args.out, repo=args.repo,
                judge_model=args.judge_model))
            return
        if args.bench_cmd == "verify-case":
            from .benchmarks.cli import dispatch_verify_case
            print(dispatch_verify_case(case=args.case))
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
        from .eval.cli import EvalError, default_judge_model, run_eval
        try:
            judge = args.judge_model or default_judge_model()
            print(run_eval(args.target, case=args.case, against=args.against,
                           k=args.k, judge_model=judge, gate=args.gate))
        except EvalError as e:
            print(f"eval error: {e}")
            raise SystemExit(1)
        if args.view:
            import subprocess

            from .eval.promptfoo import promptfoo_bin
            subprocess.run([promptfoo_bin(), "view"])
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

    if args.cmd == "tidyup" and args.tidyup_cmd == "show":
        handle = client.get_workflow_handle(args.id)
        report = await handle.query(TidyUpWorkflow.report)
        print("no tidy-up report yet" if report is None
              else report.model_dump_json(indent=2))
        return

    if args.cmd == "tidyup" and args.tidyup_cmd == "select":
        handle = client.get_workflow_handle(args.id)
        identities = [s.strip() for s in args.identities.split(",")
                      if s.strip()]
        await handle.signal(TidyUpWorkflow.select_items, identities)
        print(f"selected {len(identities)} finding(s); "
              f"approve with: sdlc approve --id {args.id} --gate tidy_up")
        return

    if args.cmd == "tidyup":
        if not args.repo:
            raise SystemExit("tidyup requires --repo")
        repo = os.path.abspath(args.repo)
        wf_id = tidyup_workflow_id(repo)
        handle = await client.start_workflow(
            TidyUpWorkflow.run,
            TidyUpInput(repo_dir=repo, commit=args.commit,
                        build_probe=not args.no_build_probe,
                        advisory_source=args.advisory_source,
                        base_branch=args.base_branch,
                        max_fix_runs=args.max_fix_runs),
            id=wf_id, task_queue=TASK_QUEUE)
        print(f"started {handle.id}")
        print("NOTE: the build probe AND the fix runs execute this "
              "repository's own code as the worker user. Operator-run only "
              "(NFR-9).")
        return

    if args.cmd == "assess" and args.assess_cmd == "show":
        handle = client.get_workflow_handle(args.id)
        # Query by METHOD, not by name -- see the triage show handler.
        report = await handle.query(AssessmentWorkflow.assessment)
        print("no assessment yet" if report is None
              else report.model_dump_json(indent=2))
        return

    if args.cmd == "assess":
        if not args.repo:
            raise SystemExit("assess requires --repo")
        repo = os.path.abspath(args.repo)
        wf_id = assess_workflow_id(repo)
        handle = await client.start_workflow(
            AssessmentWorkflow.run,
            AssessmentInput(repo_dir=repo, commit=args.commit,
                            build_probe=not args.no_build_probe,
                            advisory_source=args.advisory_source),
            id=wf_id, task_queue=TASK_QUEUE)
        print(f"started {handle.id}")
        # The FR-903 gate opens on the CHILD, so the operator needs the
        # child's id -- `sdlc approve --id <parent>` reaches nothing.
        print(f"NOTE: the readiness gate opens on {wf_id}-triage; approve "
              f"with: sdlc approve --id {wf_id}-triage --gate readiness")
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
