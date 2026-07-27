"""CLI handlers for the `sdlc benchmark` subcommands.

  python -m sdlc.cli benchmark run    --case benchmarks/cases/add-login/case.yaml
  python -m sdlc.cli benchmark drift  --since 168
  python -m sdlc.cli benchmark report --bench <id>
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
import yaml

from ..models import HarnessKind
from ..worker import TASK_QUEUE
from .models import CaseSpec
from .workflow import BenchmarkWorkflow
from .report import aggregate, render_markdown
from .models import CompositeWeights
from .recorder import _root


def load_case_spec(path: str) -> CaseSpec:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    raw["harnesses"] = [HarnessKind(h) for h in raw.get("harnesses", [])]
    return CaseSpec(**raw)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("benchmark")
    bsub = b.add_subparsers(dest="bench_cmd", required=True)

    run = bsub.add_parser("run")
    run.add_argument("--case", required=True)

    drift = bsub.add_parser("drift")
    drift.add_argument("--since", type=int, default=168)   # hours

    rep = bsub.add_parser("report")
    rep.add_argument("--bench", required=True)

    hist = bsub.add_parser("history")
    hist.add_argument("--case", required=True)

    cal = sub.add_parser("calibrate")
    cal.add_argument("rubric")
    cal.add_argument("--judge-model", default=None, dest="judge_model")
    cal.add_argument("--epsilon", type=float, default=0.15)
    cal.add_argument("--threshold", type=float, default=0.75)
    return p


def dispatch_report(bench: str,
                    root: str | None = None) -> str:
    from .calibration import load_calibration_reports, render_calibration_html
    from .report import (
        _read_all, resolve_language_map, write_heatmap,
        write_report_with_calibration)
    records = _read_all(bench, root)
    summaries = aggregate(bench, CompositeWeights(), root=root, _records=records)
    calibration = load_calibration_reports()
    md = render_markdown(summaries, calibration=calibration)
    out_dir = Path(root if root is not None else _root()) / bench
    write_report_with_calibration(summaries, str(out_dir / "report.md"), calibration)
    lang = resolve_language_map(sorted({r.case_id for r in records}))
    write_heatmap(records, out_dir, lang, render_calibration_html(calibration))
    return md


def dispatch_history(case_id: str, root: str | None = None) -> tuple[str, str]:
    from .error_matrix import (
        build_error_matrix, render_error_matrix_html, render_error_matrix_json)
    from .report import scan_case_records
    from .task_matrix import (
        build_task_matrix, render_task_matrix_html, render_task_matrix_json)
    from .tasks import load_task_suite

    suite = load_task_suite(case_id)
    if suite is None:
        raise ValueError(f"no tasks.yaml for case {case_id!r}; nothing to build")
    records = scan_case_records(case_id, root)
    tm = build_task_matrix(case_id, records, suite)
    em = build_error_matrix(case_id, records, suite)

    out_dir = Path(root if root is not None else _root()) / "_history" / case_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "task-matrix.html").write_text(
        render_task_matrix_html(tm), encoding="utf-8")
    (out_dir / "task-matrix.json").write_text(
        render_task_matrix_json(tm), encoding="utf-8")
    (out_dir / "error-matrix.html").write_text(
        render_error_matrix_html(em), encoding="utf-8")
    (out_dir / "error-matrix.json").write_text(
        render_error_matrix_json(em), encoding="utf-8")
    return str(out_dir / "task-matrix.html"), str(out_dir / "error-matrix.html")


def dispatch_calibrate(rubric: str, *, judge_model: str | None,
                       epsilon: float, threshold: float,
                       calib_root=None) -> str:
    from .calibration import (
        _CALIB_DIR, load_scored_fixtures, run_calibration,
        write_calibration_report)
    root = Path(calib_root) if calib_root is not None else _CALIB_DIR
    rubric_dir = root / rubric
    fixtures = load_scored_fixtures(rubric_dir)
    if not fixtures:
        return (f"no scored fixtures under {rubric_dir}; capture some with "
                f"`sdlc calibrate capture --case <c> --rubric {rubric}` and "
                f"fill in human_score.")
    if judge_model is None:
        from ..eval.cli import default_judge_model
        judge_model = default_judge_model()
    rep = run_calibration(rubric, fixtures, judge_model,
                          epsilon=epsilon, threshold=threshold)
    write_calibration_report(rep, rubric_dir)
    return (f"calibrate {rubric}: n={rep.n_fixtures} "
            f"agreement={rep.agreement_rate:.2f} mae={rep.mae:.3f} "
            f"spearman={rep.spearman:.2f} -> {rep.verdict}")


async def _run_matrix(case_path: str) -> str:
    spec = load_case_spec(case_path)
    client = await Client.connect(
        "localhost:7233", data_converter=pydantic_data_converter)
    handle = await client.start_workflow(
        BenchmarkWorkflow.run, spec.model_dump_json(),
        id=f"bench-{spec.case_id}-{int(__import__('time').time())}",
        task_queue=TASK_QUEUE,
    )
    return await handle.result()


async def _run_drift(since_hours: int) -> int:
    # production wiring uses a real Temporal client; left to operator runtime
    from .drift import DriftHarvester, HistoryProvider  # noqa: F401
    raise NotImplementedError(
        "drift requires a live Temporal client; run via the operator CLI "
        "with a connected client. See ARCHITECTURE.md §8.")


def main_async(args: argparse.Namespace) -> None:
    if args.cmd != "benchmark":
        return
    if args.bench_cmd == "run":
        print(asyncio.run(_run_matrix(args.case)))
    elif args.bench_cmd == "drift":
        print(asyncio.run(_run_drift(args.since)))
    elif args.bench_cmd == "report":
        print(dispatch_report(args.bench))
    elif args.bench_cmd == "history":
        tm_path, em_path = dispatch_history(args.case)
        print(tm_path)
        print(em_path)
