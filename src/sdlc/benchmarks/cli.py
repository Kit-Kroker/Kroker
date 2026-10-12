"""CLI handlers for the `sdlc benchmark` subcommands.

python -m sdlc.cli benchmark run    --case benchmarks/cases/add-login/case.yaml
python -m sdlc.cli benchmark drift  --since 168
python -m sdlc.cli benchmark score  --bench <id> | --case <id> | --all
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import os
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from ..core.models import (
    GatePolicy,
    HarnessKind,
)
from .matrix import expand_matrix
from .models import CaseRole, CaseSpec
from .smoke import (
    SmokeStamp,
    check_smoke,
    extract_bench_run_id,
    passing_stamp,
    resolve_repo_status,
    write_stamp,
)


def _run_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as ex:
            return ex.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def load_case_spec(path: str) -> CaseSpec:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    # harnesses stay raw strings: `crew:<lead_harness>` entries (spec §5)
    # are not HarnessKind values. expand_matrix validates them.
    return CaseSpec(**raw)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("benchmark")
    bsub = b.add_subparsers(dest="bench_cmd", required=True)

    run = bsub.add_parser("run")
    run.add_argument("--case", required=True)
    run.add_argument(
        "--gate-policy",
        choices=["off", "soft", "hard"],
        default=None,
        dest="gate_policy",
        help="override the case's gate_policy for every gate "
        "in the child FeatureWorkflow (default: use the "
        "case's own setting, SOFT unless the case file "
        "says otherwise)",
    )
    run.add_argument("--arm", default=None, help="run only cells for this arm name")
    run.add_argument(
        "--all-arms",
        action="store_true",
        default=False,
        dest="all_arms",
        help="allow running all arms on a corpus case",
    )
    run.add_argument(
        "--skip-smoke",
        action="store_true",
        default=False,
        dest="skip_smoke",
        help="skip smoke check before starting",
    )
    run.add_argument(
        "--allow-parked",
        action="store_true",
        default=False,
        dest="allow_parked",
        help="allow running a parked case",
    )

    drift = bsub.add_parser("drift")
    drift.add_argument("--since", type=int, default=168)  # hours

    bs = bsub.add_parser("score")
    bsg = bs.add_mutually_exclusive_group(required=True)
    bsg.add_argument("--bench", help="one bench_run_id")
    bsg.add_argument("--case", help="every bench run for one case")
    bsg.add_argument(
        "--all", action="store_true", dest="all_", help="every bench run for every case"
    )
    bs.add_argument("--out", default=None, help="output dir (default: <root>/<selector>/score)")
    bs.add_argument(
        "--weights",
        default=None,
        metavar="Q,C,S",
        help="composite weights as quality,cost,speed; defaults to benchmarks/config.yaml",
    )

    register_benchmark_subparsers(bsub)

    cal = sub.add_parser("calibrate")
    cal.add_argument("rubric")
    cal.add_argument("--judge-model", default=None, dest="judge_model")
    cal.add_argument("--epsilon", type=float, default=0.15)
    cal.add_argument("--threshold", type=float, default=0.75)
    return p


def dispatch_score(
    *,
    bench: str | None = None,
    case: str | None = None,
    all_: bool = False,
    out: str | None = None,
    weights: str | None = None,
    root: str | None = None,
) -> str:
    """Read every evidence store for one selector and write the full score
    directory. Seconds, no Temporal client, no worker."""
    from .evidence import load_evidence
    from .score import default_out_dir, load_config_weights, parse_weights, write_score

    ev = load_evidence(bench=bench, case=case, all_=all_, root=root)
    w = parse_weights(weights) if weights else load_config_weights()
    out_dir = Path(out) if out else default_out_dir(ev.selector, root)
    written = write_score(ev, out_dir, w)
    return "\n".join(str(p) for p in written)


def dispatch_experiment_new(
    *,
    name: str,
    axis: str,
    change: str,
    baseline: str,
    commit: str = "",
    hypothesis: str = "",
    exp_dir: str | None = None,
) -> str:
    from .experiments import experiments_dir, new_experiment, save_experiment

    exp = new_experiment(
        name=name, axis=axis, change=change, baseline=baseline, commit=commit, hypothesis=hypothesis
    )
    base = Path(exp_dir) if exp_dir else experiments_dir()
    p = save_experiment(exp, base / f"{exp.id}.yaml")
    return (
        f"{p}\n\nRun the candidate matrix, then:\n"
        f"  sdlc benchmark experiment compare --experiment {exp.id} "
        f"--candidate <bench_id>\n"
        f"Then write `verdict: keep` or `verdict: rollback` yourself "
        f"and commit the file."
    )


def dispatch_experiment_compare(
    *, experiment: str, candidate: str, exp_dir: str | None = None, root: str | None = None
) -> str:
    """Hard-errors on a missing bench_id. Reporting degrades; comparison
    does not -- a silent half-comparison produces a verdict on partial data."""
    from .evidence import load_evidence
    from .experiments import (
        compute_deltas,
        experiments_dir,
        load_experiment,
        render_deltas_markdown,
        save_experiment,
    )
    from .models import BenchmarkScope, is_pre012
    from .runs import build_runs, composite_shown
    from .score import load_config_weights

    base = Path(exp_dir) if exp_dir else experiments_dir()
    path = base / f"{experiment}.yaml"
    if not path.is_file():
        raise SystemExit(f"no experiment {experiment!r} at {path}")

    exp = load_experiment(path)
    baseline_ev = load_evidence(bench=exp.baseline, root=root)
    candidate_ev = load_evidence(bench=candidate, root=root)
    for label, ev in (("baseline", baseline_ev), ("candidate", candidate_ev)):
        if not ev.records:
            raise SystemExit(
                f"{label} bench {ev.selector!r} has no records; refusing to compare against nothing"
            )

    exp.candidate = candidate
    exp.deltas = compute_deltas(baseline_ev, candidate_ev, load_config_weights())
    save_experiment(exp, path)
    # 012 (contract §7.6, the T010-deferred hook): is_pre012 over both
    # evidence sets, cell-scope records excluded like every §7.6 view.
    compared = [
        r
        for r in [*baseline_ev.records, *candidate_ev.records]
        if r.scope is not BenchmarkScope.CELL
    ]
    pre012 = sum(1 for r in compared if is_pre012(r))
    # 013 (contract 7.2): the composite column prints only when a compared
    # case shows one -- the decision from composite_shown, true when either
    # side's case has two graded arms in one generation.
    show_composite = any(
        d.shown
        for d in (
            *composite_shown(build_runs(baseline_ev.records)).values(),
            *composite_shown(build_runs(candidate_ev.records)).values(),
        )
    )
    return (
        render_deltas_markdown(exp.deltas, pre012_records=pre012, show_composite=show_composite)
        + f"\nWritten to {path}. Verdict is yours to write.\n"
    )


def dispatch_calibrate(
    rubric: str, *, judge_model: str | None, epsilon: float, threshold: float, calib_root=None
) -> str:
    from .calibration import (
        load_scored_fixtures,
        run_calibration,
        write_calibration_report,
    )
    from .paths import calibration_dir

    root = Path(calib_root) if calib_root is not None else calibration_dir()
    rubric_dir = root / rubric
    fixtures = load_scored_fixtures(rubric_dir)
    if not fixtures:
        return (
            f"no scored fixtures under {rubric_dir}; capture some with "
            f"`sdlc calibrate capture --case <c> --rubric {rubric}` and "
            f"fill in human_score."
        )
    if judge_model is None:
        from ..eval.cli import default_judge_model

        judge_model = default_judge_model()
    rep = run_calibration(rubric, fixtures, judge_model, epsilon=epsilon, threshold=threshold)
    write_calibration_report(rep, rubric_dir)
    return (
        f"calibrate {rubric}: n={rep.n_fixtures} "
        f"agreement={rep.agreement_rate:.2f} mae={rep.mae:.3f} "
        f"spearman={rep.spearman:.2f} -> {rep.verdict}"
    )


async def _run_matrix(
    case_path: str,
    gate_policy: str | None = None,
    arm: str | None = None,
    all_arms: bool = False,
    skip_smoke: bool = False,
    allow_parked: bool = False,
) -> str:
    from temporalio.client import Client
    from temporalio.contrib.pydantic import pydantic_data_converter

    spec = load_case_spec(case_path)
    # 012 (contract §1.3): a registered rubric or veto file that is missing
    # or empty stops the run HERE — before any Temporal client exists and
    # before any cell can spend model budget (SC-008).
    from .paths import check_case_assets

    problems = check_case_assets(spec.rubrics, spec.vetoes, Path(case_path).parent)
    if problems:
        raise SystemExit("\n".join(problems))

    # 1. Parked case refusal
    if spec.role == CaseRole.PARKED and not allow_parked:
        raise SystemExit(f"case '{spec.case_id}' is parked; use --allow-parked to run")

    # 2. Smoke check & dirty tree refusal for corpus cases
    commit, dirty = resolve_repo_status()
    if spec.role == CaseRole.CORPUS:
        if skip_smoke:
            print("smoke check skipped")
        else:
            if dirty:
                raise SystemExit(
                    f"tree is dirty; smoke check refuses uncommitted changes (commit: {commit})"
                )
            stamp = passing_stamp(commit)
            if stamp is None:
                raise SystemExit(
                    f"no passing smoke stamp for commit {commit}; run `sdlc benchmark smoke` first"
                )

    # 3. Arm filtering and multi-cell refusal
    from .matrix import _arms_for

    known_arms = [a.name for a in (spec.arms or _arms_for(spec))]
    if arm is not None:
        matching = [a for a in (spec.arms or _arms_for(spec)) if a.name == arm]
        if not matching:
            raise SystemExit(f"unknown arm '{arm}'; known arms: {', '.join(known_arms)}")
        spec = spec.model_copy(update={"arms": matching})
    else:
        cells = expand_matrix(spec)
        if spec.role == CaseRole.CORPUS and len(cells) > 1 and not all_arms:
            raise SystemExit(
                f"corpus case '{spec.case_id}' has {len(cells)} cells; "
                f"specify --arm or --all-arms. Available arms: {', '.join(known_arms)}"
            )

    # Refuse a colliding sweep before the matrix starts, not at each cell's
    # code stage (parent §5). expand_matrix already turned `crew:<harness>`
    # entries into cells, so this reads the same strings the arms will use.
    from ..crew.loader import preflight_crew
    from .workflow import BenchmarkWorkflow

    for cell in expand_matrix(spec):
        if cell.harness is HarnessKind.CREW:
            preflight_crew("code", cell.lead_harness, cell.role_models.get("dev"))
    if gate_policy is not None:
        spec = spec.model_copy(update={"gate_policy": GatePolicy(gate_policy)})
    client = await Client.connect(
        os.environ.get("TEMPORAL_HOST", "localhost:7233"), data_converter=pydantic_data_converter
    )
    from ..worker import TASK_QUEUE

    handle = await client.start_workflow(
        BenchmarkWorkflow.run,
        spec.model_dump_json(),
        id=f"bench-{spec.case_id}-{int(__import__('time').time())}",
        task_queue=TASK_QUEUE,
    )
    return await handle.result()


async def _run_drift(since_hours: int) -> int:
    # production wiring uses a real Temporal client; left to operator runtime
    from .drift import DriftHarvester, HistoryProvider  # noqa: F401

    raise NotImplementedError(
        "drift requires a live Temporal client; run via the operator CLI "
        "with a connected client. See ARCHITECTURE.md §8."
    )


def main_async(args: argparse.Namespace) -> None:
    if args.cmd != "benchmark":
        return
    if args.bench_cmd == "run":
        print(
            asyncio.run(
                _run_matrix(
                    args.case,
                    gate_policy=args.gate_policy,
                    arm=getattr(args, "arm", None),
                    all_arms=getattr(args, "all_arms", False),
                    skip_smoke=getattr(args, "skip_smoke", False),
                    allow_parked=getattr(args, "allow_parked", False),
                )
            )
        )
    elif args.bench_cmd == "drift":
        print(asyncio.run(_run_drift(args.since)))
    elif args.bench_cmd == "score":
        print(
            dispatch_score(
                bench=getattr(args, "bench", None),
                case=getattr(args, "case", None),
                all_=getattr(args, "all_", False),
                out=getattr(args, "out", None),
                weights=getattr(args, "weights", None),
            )
        )
    elif dispatch_benchmark_cmd(args):
        return


def _resolve_kroker_commit() -> str:
    commit, _ = resolve_repo_status()
    return commit


def register_benchmark_subparsers(bsub: argparse._SubParsersAction) -> None:
    """Registers benchmark subcommands on the benchmark subparser."""
    ba = bsub.add_parser("accept")
    ba.add_argument("--case", required=True, help="a case_id")
    ba.add_argument(
        "--offline",
        action="store_true",
        default=False,
        help="run only offline reference and floor checks",
    )

    bsmoke = bsub.add_parser("smoke")
    bsmoke.add_argument("--cases-root", default=None, help="override cases directory")
    bsmoke.add_argument("--ops-root", default=None, help="override ops directory")

    bcorpus = bsub.add_parser("corpus")
    bcorpus.add_argument("--cases-root", default=None, help="override cases directory")


def dispatch_benchmark_cmd(args: argparse.Namespace) -> bool:
    """Dispatches registered benchmark subcommands. Returns True if handled."""
    cmd = getattr(args, "bench_cmd", None)
    if cmd == "accept":
        dispatch_accept(
            case=args.case,
            offline=getattr(args, "offline", False),
            cases_root=getattr(args, "cases_root", None),
        )
        return True
    if cmd == "smoke":
        dispatch_smoke(
            cases_root=getattr(args, "cases_root", None),
            ops_dir=getattr(args, "ops_root", None),
        )
        return True
    if cmd == "corpus":
        dispatch_corpus(
            cases_root=getattr(args, "cases_root", None),
        )
        return True
    return False


def dispatch_corpus(*, cases_root: str | None = None) -> str:
    """Prints the status of all cases in the corpus and returns the rendered output."""
    from .corpus import corpus_status, render_corpus_status
    from .paths import cases_dir

    root = Path(cases_root) if cases_root else cases_dir()
    rows = corpus_status(root)
    rendered = render_corpus_status(rows)
    print(rendered)
    return rendered


def dispatch_accept(
    *,
    case: str,
    offline: bool = False,
    cases_root: str | None = None,
) -> str:
    """Run acceptance checks for one case and write <case dir>/acceptance.yaml."""
    from .acceptance import AcceptanceRecord, Verdict, decide, save_acceptance
    from .offline_checks import run_floor_check, run_reference_check
    from .oracle_id import oracle_identity
    from .paths import cases_dir

    root = Path(cases_root) if cases_root else cases_dir()
    case_dir = root / case
    if not case_dir.is_dir():
        raise SystemExit(f"case directory not found: {case_dir}")

    spec = load_case_spec(str(case_dir / "case.yaml"))
    commit = _resolve_kroker_commit()
    updated = datetime.now(UTC).isoformat()

    if spec.language is None:
        rec = AcceptanceRecord(
            case_id=spec.case_id,
            verdict=Verdict.NOT_ASSESSED,
            note="no oracle",
            role=spec.role,
            visibility=spec.visibility,
            exposure="repo_public",
            kroker_commit=commit,
            updated=updated,
        )
        save_acceptance(rec, case_dir)
        line = f"{spec.case_id}: not_assessed (no oracle)"
        print(line)
        return line

    oracle_path = case_dir / "oracle"
    oid = oracle_identity(oracle_path) if oracle_path.is_dir() else None

    ref_check = run_reference_check(case_dir)
    floor_check = run_floor_check(case_dir)

    sep_check = None
    if not offline:
        from .acceptance import SeparationCheck, separation
        from .evidence import load_evidence
        from .models import CaseRole
        from .runs import build_runs

        if spec.role != CaseRole.CORPUS:
            sep_check = SeparationCheck(
                passed=None,
                detail=f"separation not assessed for {spec.role.value} case",
            )
        else:
            ev = load_evidence(case=spec.case_id)
            runs = build_runs(ev.records) if (ev and ev.records) else []
            sep_check = separation(
                runs=runs,
                strong=spec.strong_arm,
                weak=spec.weak_arm,
                oracle_id=oid,
            )

    verdict, reason, detail = decide(ref_check, floor_check, separation=sep_check)

    oracle_tests = ref_check.tests_total or floor_check.tests_total
    rec = AcceptanceRecord(
        case_id=spec.case_id,
        verdict=verdict,
        reason=reason,
        note=detail,
        oracle_id=oid,
        oracle_tests=oracle_tests,
        reference=ref_check,
        floor=floor_check,
        separation=sep_check,
        role=spec.role,
        visibility=spec.visibility,
        exposure="repo_public",
        kroker_commit=commit,
        updated=updated,
    )
    save_acceptance(rec, case_dir)

    reason_suffix = f" ({reason.value})" if reason is not None else ""
    line = f"{spec.case_id}: {verdict.value}{reason_suffix}"
    print(line)
    return line


def dispatch_smoke(
    *,
    cases_root: str | None = None,
    ops_dir: str | None = None,
    run_fn: Callable[[str], str] | None = None,
) -> str:
    """Run the smoke test case, verify smoke conditions, and record stamp."""
    from .corpus import smoke_case
    from .matrix import expand_matrix
    from .paths import cases_dir
    from .report import _read_all
    from .report import _root as benchmarks_root

    root_path = Path(cases_root) if cases_root else cases_dir()
    spec = smoke_case(root_path)
    case_file = root_path / spec.case_id / "case.yaml"

    if run_fn is not None:
        raw_result = run_fn(str(case_file))
    else:
        raw_result = _run_sync(_run_matrix(str(case_file), skip_smoke=True))

    bench_run_id = extract_bench_run_id(raw_result)

    records = _read_all(bench_run_id, None)
    bench_path = Path(benchmarks_root()) / bench_run_id
    record_files = sorted(bench_path.rglob("*.jsonl")) if bench_path.is_dir() else []

    n_cells = len(expand_matrix(spec))
    commit = records[0].kroker_commit if (records and records[0].kroker_commit) else "unknown"

    failed = check_smoke(records, record_files, n_cells)
    if not failed:
        stamp = SmokeStamp(
            kroker_commit=commit,
            bench_run_id=bench_run_id,
            passed=True,
            failed_conditions=[],
            written=datetime.now(UTC).isoformat(),
        )
        write_stamp(stamp, root=ops_dir)
        line = f"smoke: PASS {commit}"
        print(line)
        return line

    stamp = SmokeStamp(
        kroker_commit=commit,
        bench_run_id=bench_run_id,
        passed=False,
        failed_conditions=failed,
        written=datetime.now(UTC).isoformat(),
    )
    write_stamp(stamp, root=ops_dir)
    for cond in failed:
        print(f"smoke: FAIL condition {cond}")
    raise SystemExit(f"smoke check failed: {', '.join(failed)}")


def dispatch_import_deveval(
    *,
    src: str,
    out: str | None = None,
    judge_model: str = "google:gemini-3.5-flash",
    repo: str | None = None,
) -> str:
    """Convert every repository under `src` (a DevEval
    benchmark_data/<language> directory) into a case directory under `out`.

    Fails loud on the first bad repository rather than importing a partial
    corpus -- see the importer's module docstring.
    """
    from .importers.deveval import convert_repo
    from .paths import cases_dir

    src_root = Path(src)
    dest = Path(out) if out else cases_dir()
    repos = [src_root / repo] if repo else [d for d in sorted(src_root.iterdir()) if d.is_dir()]
    if not repos:
        raise SystemExit(f"no repositories under {src_root}")

    lines: list[str] = []
    for d in repos:
        rep = convert_repo(d, dest, judge_model=judge_model)
        flag = " QUARANTINED (network_required)" if rep.network_required else ""
        lines.append(
            f"{rep.case_id}: {rep.n_tasks} draft tasks, "
            f"{rep.n_oracle_tests} oracle tests, "
            f"{rep.reference_files} reference files{flag}"
        )
        for e in rep.network_evidence[:5]:
            lines.append(f"    network: {e}")
    lines.append("")
    lines.append(
        "Next: review each tasks.yaml (drafts are test-file "
        "granularity), then run `sdlc benchmark verify-case "
        "--case <case_id>` for each."
    )
    return "\n".join(lines)


def dispatch_verify_case(*, case: str, cases_root: str | None = None) -> str:
    """Run one imported case's oracle against its own reference/."""
    from .importers.verify import verify_case
    from .paths import cases_dir

    root = Path(cases_root) if cases_root else cases_dir()
    result = verify_case(root / case)
    head = f"{result.case_id}: {'PASS' if result.ok else 'FAIL'}"
    return head if result.ok else f"{head}\n{result.output}"
