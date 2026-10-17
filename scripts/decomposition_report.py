"""Decomposition report (016 T011, plan D-11, US5).

Public and generic; its output is AGGREGATES ONLY (plan shape figures,
tier names, counts and means) — never a task id, test name or
requirement text (FR-028). Two modes:

- ``--case <id> --bench-run <id> [...]``: per-run plan shape (the latest
  plan-v<N>.json of each run's cell artifacts) and per-tier credit per
  arm, from the oracle-task records of runs with the case's CURRENT
  oracle identity. ``--case`` and ``--bench-run`` go together.
- ``--baseline-plan <path> [...]``: prints only the shape of each named
  plan file (V6's mode).

Numbers are copied by hand into verification.md / BENCHMARK.md (D-11).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_PLAN_RE = re.compile(r"^plan-v(\d+)\.json$")


class _CountedPath(type(Path())):
    """A Path that can carry ``count``: pathlib 3.13 flavour classes are
    slotted, so the count rides on this ad-hoc subclass instead."""

    count = 0


class PlanShape:
    """Names (Report): tasks, edges (resolvable depends_on entries),
    longest_chain (NODE count), dangling (unresolvable entries)."""

    __slots__ = ("tasks", "edges", "longest_chain", "dangling")

    def __init__(self, tasks: int, edges: int, longest_chain: int, dangling: int) -> None:
        self.tasks = tasks
        self.edges = edges
        self.longest_chain = longest_chain
        self.dangling = dangling

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"PlanShape(tasks={self.tasks}, edges={self.edges}, "
            f"longest_chain={self.longest_chain}, dangling={self.dangling})"
        )


def plan_shape(plan_json: dict) -> PlanShape:
    """Shape of one plan artifact. Reads the real artifact schema
    ({"tasks": [{"id": ..., "depends_on": [...]}]}); an entry naming an
    unknown id is dangling, not an edge, and adds no chain node."""
    entries = plan_json.get("tasks") or []
    ids = [t.get("id") for t in entries if isinstance(t, dict) and t.get("id")]
    id_set = set(ids)
    edges = 0
    dangling = 0
    children: dict[str, list[str]] = {i: [] for i in ids}
    for t in entries:
        if not isinstance(t, dict) or not t.get("id"):
            continue
        for dep in t.get("depends_on") or []:
            if dep in id_set:
                edges += 1
                children[dep].append(t["id"])
            else:
                dangling += 1

    memo: dict[str, int] = {}

    def depth(node: str, seen: frozenset[str]) -> int:
        if node in memo:
            return memo[node]
        if node in seen:  # cycle guard: a back-edge adds no node
            return 1
        nxt = seen | {node}
        best = 1 + max((depth(c, nxt) for c in children[node]), default=0)
        memo[node] = best
        return best

    chain = max((depth(i, frozenset()) for i in ids), default=0)
    return PlanShape(len(ids), edges, chain, dangling)


def latest_plan(cell_artifacts: Path) -> Path | None:
    """The highest-numeric plan-v<N>.json under the cell's artifacts dir,
    or None when there is none. The count of candidate plan files rides
    on the returned path as ``.count`` (reported beside it)."""
    candidates: list[tuple[int, Path]] = []
    for p in sorted(Path(cell_artifacts).glob("plan-v*.json")):
        m = _PLAN_RE.match(p.name)
        if m:
            candidates.append((int(m.group(1)), p))
    if not candidates:
        return None
    version, raw = max(candidates, key=lambda pair: pair[0])
    chosen = _CountedPath(raw)
    chosen.count = len(candidates)
    return chosen


TierCredit = dict[tuple[str, str], tuple[float, int, int]]


def tier_credit(case_id: str, runs, oracle_id: str) -> TierCredit:
    """Per (arm, tier): (mean, n_requirements, n_tests). The mean is over
    that arm's runs whose oracle_id matches ``oracle_id``, of the per-run
    test-weighted fraction sum(score * n_tests_of_task) / n_tests_in_tier;
    a task with no record in a run contributes nothing to that run's
    numerator. Runs of another identity contribute nothing anywhere.
    The mapping is read through load_task_suite (so the private store is
    found when configured)."""
    from sdlc.benchmarks.tasks import load_task_suite

    suite = load_task_suite(case_id)
    if suite is None:
        return {}
    tier_of: dict[str, tuple[str, int]] = {}
    totals: dict[str, list[int]] = {}
    for task in suite.tasks:
        if task.tier is None or not task.oracle_tests:
            continue
        tier_of[task.id] = (task.tier, len(task.oracle_tests))
        totals.setdefault(task.tier, []).append(len(task.oracle_tests))
    tier_tests = {tier: sum(counts) for tier, counts in totals.items()}
    tier_reqs = {tier: len(counts) for tier, counts in totals.items()}

    fractions: dict[tuple[str, str], list[float]] = {}
    for run in runs:
        if getattr(run, "case_id", case_id) != case_id:
            continue
        if getattr(run, "oracle_id", None) != oracle_id:
            continue
        arm = getattr(run, "arm", "")
        numer: dict[str, float] = {tier: 0.0 for tier in tier_tests}
        for record in getattr(run, "records", []):
            if getattr(record, "scope", None) != "oracle_task":
                continue
            info = tier_of.get(getattr(record, "task_id", ""))
            if info is None:
                continue
            score = getattr(getattr(record, "quality", None), "score", None)
            if score is None:
                continue
            tier, n_tests = info
            numer[tier] += float(score) * n_tests
        for tier, total in tier_tests.items():
            fractions.setdefault((arm, tier), []).append(numer[tier] / total)

    return {
        (arm, tier): (
            sum(vals) / len(vals),
            tier_reqs[tier],
            tier_tests[tier],
        )
        for (arm, tier), vals in fractions.items()
    }


def _shape_line(label: str, shape: PlanShape, extra: str = "") -> str:
    line = (
        f"{label}: tasks {shape.tasks}, edges {shape.edges}, "
        f"longest chain {shape.longest_chain} nodes, dangling {shape.dangling}"
    )
    if extra:
        line += f", {extra}"
    return line


def _run_report(case_id: str, bench_run_ids: list[str]) -> int:
    from sdlc.benchmarks.oracle_id import oracle_identity
    from sdlc.benchmarks.paths import case_dir
    from sdlc.benchmarks.report import _read_all
    from sdlc.benchmarks.runs import build_runs

    export_root = Path(__import__("os").environ.get("SDLC_EXPORT_ROOT", "./runs/pipeline"))
    oracle_dir = case_dir(case_id) / "oracle"
    identity = oracle_identity(oracle_dir) if oracle_dir.is_dir() else None

    for bench_run_id in bench_run_ids:
        runs = [r for r in build_runs(_read_all(bench_run_id, None)) if r.case_id == case_id]
        for run in runs:
            artifacts = export_root / bench_run_id / (run.records[0].cell_id or "") / "artifacts"
            plan = latest_plan(artifacts) if artifacts.is_dir() else None
            if plan is None:
                print(f"run of arm {run.arm}: no plan artifact")
                continue
            shape = plan_shape(json.loads(plan.read_text(encoding="utf-8")))
            print(
                _shape_line(
                    f"run of arm {run.arm}",
                    shape,
                    extra=f"plan files {getattr(plan, 'count', 1)}",
                )
            )
        if identity is not None:
            credit = tier_credit(case_id, runs, identity)
            for (arm, tier), (mean, n_req, n_tests) in sorted(credit.items()):
                print(
                    f"tier credit arm {arm} tier {tier}: mean {mean:.4f}, "
                    f"requirements {n_req}, tests {n_tests}"
                )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="decomposition_report", description="plan shape and per-tier credit (aggregates only)"
    )
    parser.add_argument("--case", help="case id (goes together with --bench-run)")
    parser.add_argument(
        "--bench-run", action="append", default=None, help="bench run id (repeatable)"
    )
    parser.add_argument(
        "--baseline-plan", action="append", default=None, help="plan artifact path (repeatable)"
    )
    args = parser.parse_args(argv)

    has_pair = args.case is not None and args.bench_run
    half_pair = (args.case is not None) != bool(args.bench_run)
    if half_pair:
        parser.error("--case and --bench-run go together")
    if not has_pair and not args.baseline_plan:
        parser.error("at least one of --case/--bench-run or --baseline-plan is required")

    if has_pair:
        return _run_report(args.case, args.bench_run)

    for plan_path in args.baseline_plan or []:
        p = Path(plan_path)
        shape = plan_shape(json.loads(p.read_text(encoding="utf-8")))
        print(_shape_line(f"plan {p.name}", shape))
    return 0


if __name__ == "__main__":
    sys.exit(main())
