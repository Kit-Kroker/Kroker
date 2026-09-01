"""CLI handlers for the `sdlc benchmark` subcommands.

python -m sdlc.cli benchmark run    --case benchmarks/cases/add-login/case.yaml
python -m sdlc.cli benchmark drift  --since 168
python -m sdlc.cli benchmark score  --bench <id> | --case <id> | --all
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import yaml

from ..crew.loader import preflight_crew
from ..models import GatePolicy, HarnessKind
from ..worker import TASK_QUEUE
from .matrix import expand_matrix
from .models import CaseSpec
from .workflow import BenchmarkWorkflow


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
    return render_deltas_markdown(exp.deltas) + f"\nWritten to {path}. Verdict is yours to write.\n"


def dispatch_calibrate(
    rubric: str, *, judge_model: str | None, epsilon: float, threshold: float, calib_root=None
) -> str:
    from .calibration import (
        _CALIB_DIR,
        load_scored_fixtures,
        run_calibration,
        write_calibration_report,
    )

    root = Path(calib_root) if calib_root is not None else _CALIB_DIR
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


async def _run_matrix(case_path: str, gate_policy: str | None = None) -> str:
    from temporalio.client import Client
    from temporalio.contrib.pydantic import pydantic_data_converter

    spec = load_case_spec(case_path)
    # Refuse a colliding sweep before the matrix starts, not at each cell's
    # code stage (parent §5). expand_matrix already turned `crew:<harness>`
    # entries into cells, so this reads the same strings the arms will use.
    for cell in expand_matrix(spec):
        if cell.harness is HarnessKind.CREW:
            preflight_crew("code", cell.lead_harness, cell.role_models.get("dev"))
    if gate_policy is not None:
        spec = spec.model_copy(update={"gate_policy": GatePolicy(gate_policy)})
    client = await Client.connect(
        os.environ.get("TEMPORAL_HOST", "localhost:7233"), data_converter=pydantic_data_converter
    )
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
        print(asyncio.run(_run_matrix(args.case, args.gate_policy)))
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

    src_root = Path(src)
    dest = Path(out) if out else (Path(__file__).resolve().parents[3] / "benchmarks" / "cases")
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

    root = (
        Path(cases_root)
        if cases_root
        else (Path(__file__).resolve().parents[3] / "benchmarks" / "cases")
    )
    result = verify_case(root / case)
    head = f"{result.case_id}: {'PASS' if result.ok else 'FAIL'}"
    return head if result.ok else f"{head}\n{result.output}"
