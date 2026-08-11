"""CLI glue for `sdlc eval`: case resolution, gate invocation, rendering.

Fully local: `eval capture` was the only target needing a Temporal client and
it was retired with E-82 (fixtures are constructed, not captured).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..agents.loader import _resolve_agents_dir
from .fixtures import FixtureError
from .gate import GateUnavailable, run_gate
from .verdict import GateVerdict, PromptGateResult

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CASES_ROOT = _REPO_ROOT / "benchmarks" / "cases"
_BENCH_CONFIG = _REPO_ROOT / "benchmarks" / "config.yaml"

# (role, case) pairs the gate covers today. Grows as rubrics and seeds are
# authored -- no machinery change needed (E-82 design doc 8).
DEFAULT_PAIRS: list[tuple[str, str]] = [
    ("clarify", "add-login-greenfield"),
    ("clarify", "cat-cafe-monitoring"),
    ("clarify", "todo-api-greenfield"),
    ("planner", "cat-cafe-monitoring"),
    ("qa", "cat-cafe-monitoring"),
]


class EvalError(Exception):
    """A user-facing eval failure. The CLI prints it and exits non-zero."""


def default_judge_model(config_path: Path = _BENCH_CONFIG) -> str:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    model = data.get("default_judge_model")
    if not model:
        raise EvalError(f"no default_judge_model in {config_path}; "
                        f"pass --judge-model")
    return model


def _resolve_case(role: str, case: str | None) -> str:
    if case:
        return case
    found = [c for r, c in DEFAULT_PAIRS if r == role]
    if len(found) == 1:
        return found[0]
    if not found:
        raise EvalError(
            f"role '{role}' has no gated case; add a (role, case) pair to "
            f"DEFAULT_PAIRS once its rubric and seed exist.")
    raise EvalError(f"role '{role}' covers multiple cases "
                    f"({', '.join(found)}); pass --case.")


def render_report(r: PromptGateResult) -> str:
    head = f"eval {r.role} (case {r.case}) -> {r.verdict.value}"
    lines = [head, f"  {r.reason}"]
    if r.mean_baseline is not None:
        lines.append(f"  baseline  {r.mean_baseline:.2f}  (n={r.n_baseline})")
        lines.append(f"  working   {r.mean_working:.2f}  (n={r.n_working})")
        lines.append(f"  delta     {r.delta:+.2f}   floor {r.floor:.2f}")
    for f in r.absolute_failures:
        lines.append(f"  ABSOLUTE  {f}")
    return "\n".join(lines)


def run_eval(role: str, *, case: str | None, against: str, k: int,
             judge_model: str, gate: bool) -> str:
    try:
        result = run_gate(
            role, _resolve_case(role, case), repo_root=_REPO_ROOT,
            cases_root=_CASES_ROOT, agents_dir=_resolve_agents_dir(),
            judge_model=judge_model, repeat=k, baseline_ref=against)
    except (GateUnavailable, FixtureError) as e:
        raise EvalError(str(e)) from e
    text = render_report(result)
    if gate and result.verdict is not GateVerdict.PASS:
        raise EvalError(text)
    return text
