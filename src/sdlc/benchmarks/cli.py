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
from .report import aggregate, render_markdown, write_report
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
    return p


def dispatch_report(bench: str,
                    root: str | None = None) -> str:
    summaries = aggregate(bench, CompositeWeights(), root=root)
    md = render_markdown(summaries)
    out_path = Path(root if root is not None else _root()) / bench / "report.md"
    write_report(summaries, str(out_path))
    return md


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
