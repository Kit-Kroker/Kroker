"""CLI glue for `sdlc eval`: rendering, case resolution, capture wiring.

The eval (non-capture) path is synchronous and local-only. capture needs a
Temporal history source; the live adapter is a documented seam (below),
mirroring benchmarks/drift.py whose real provider is operator-runtime wiring.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .compare import EvalError, EvalReport, compare
from .fixtures import DEPS_ROLES, fixtures_from_events, write_fixtures

_REPO_ROOT = Path(__file__).resolve().parents[3]
_AGENTS_DIR = _REPO_ROOT / "agents"
_CASES_ROOT = _REPO_ROOT / "benchmarks" / "cases"
_BENCH_CONFIG = _REPO_ROOT / "benchmarks" / "config.yaml"


def default_judge_model(config_path: Path = _BENCH_CONFIG) -> str:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    model = data.get("default_judge_model")
    if not model:
        raise EvalError(f"no default_judge_model in {config_path}; "
                        f"pass --judge-model")
    return model


def _resolve_case(role: str, case: str | None, agents_dir: Path) -> str:
    if case:
        return case
    fx_dir = agents_dir / role / "fixtures"
    found = sorted(fx_dir.glob("*.json")) if fx_dir.is_dir() else []
    if len(found) == 1:
        return found[0].stem
    if not found:
        raise EvalError(f"no fixtures for role '{role}' under {fx_dir}; "
                        f"capture one first.")
    raise EvalError(f"role '{role}' has multiple fixtures "
                    f"({', '.join(p.stem for p in found)}); pass --case.")


def render_report(report: EvalReport) -> str:
    head = (f"eval {report.role}  (case {report.case}, "
            f"judge {report.judge_model}, against {report.against_ref})")
    if report.unchanged:
        return f"{head}\n  no change vs {report.against_ref}"
    lines = [head]
    if report.no_baseline:
        lines.append(f"  no committed baseline at {report.against_ref}; "
                     f"working-tree score only")
        lines.append(f"  working   {_fmt(report.mean_b)}")
        return "\n".join(lines)
    lines.append(f"  {report.against_ref:<8}  {_fmt(report.mean_a)}")
    lines.append(f"  working   {_fmt(report.mean_b)}")
    lines.append(f"  delta     {_fmt_delta(report.mean_delta)}")
    errs = sum(1 for r in report.runs if r.score_a is None or r.score_b is None)
    if errs:
        lines.append(f"  ({errs} judge error{'s' if errs > 1 else ''})")
    return "\n".join(lines)


def _fmt(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.2f}"


def _fmt_delta(v: float | None) -> str:
    return "n/a" if v is None else f"{v:+.2f}"


def run_eval(role: str, *, against: str, case: str | None, k: int,
             judge_model: str, agents_dir: Path = _AGENTS_DIR,
             cases_root: Path = _CASES_ROOT,
             repo_root: Path = _REPO_ROOT) -> str:
    if role in DEPS_ROLES:
        raise EvalError(
            f"role '{role}' carries deps; deps-aware eval is future work")
    resolved_case = _resolve_case(role, case, agents_dir)
    report = compare(role, resolved_case, against_ref=against, k=k,
                     agents_dir=agents_dir, cases_root=cases_root,
                     repo_root=repo_root, judge_model=judge_model)
    return render_report(report)


async def run_capture(client, run_id: str, case: str,
                      agents_dir: Path = _AGENTS_DIR) -> list[Path]:
    """Live capture: fetch a run's history, normalize to events, write fixtures.

    SEAM: `_history_to_events` converts a Temporal history into the normalized
    event dicts fixtures_from_events consumes. Like drift.py's real provider it
    needs a live run to validate; the pure core it feeds is fully tested. A
    fixture is trivial JSON, so hand-authoring is the offline fallback.
    """
    from ..agents.roles import REGISTRY
    history = await client.get_workflow_handle(run_id).fetch_history()
    events = _history_to_events(history)
    fixtures = fixtures_from_events(run_id, case, events, REGISTRY)
    return write_fixtures(fixtures, agents_dir)


def _history_to_events(history) -> list[dict]:
    """Temporal history -> normalized {activity, input:{messages}} dicts for
    ActivityTaskScheduled events of proposer model-request activities. Reads
    each scheduled event's activity_type name and decoded input payload."""
    events: list[dict] = []
    for ev in getattr(history, "events", history):
        attrs = getattr(ev, "activity_task_scheduled_event_attributes", None)
        if attrs is None:
            continue
        activity = attrs.activity_type.name
        try:
            inp = attrs.input.payloads[0].data
            import json
            messages_payload = json.loads(inp)
        except Exception:
            continue
        events.append({"activity": activity, "input": messages_payload})
    return events
