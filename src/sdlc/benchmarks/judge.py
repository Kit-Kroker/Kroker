"""Cross-family LLM-judge for proposer-stage artifacts.

The real LLM call is behind JudgeFn so tests inject a fake and CI makes no
model calls. On any failure (exception, bad JSON, out-of-range) we return
QualityScore(score=None, judge="error") — the judge never raises, so a
broken judge can never fail a benchmark cell; the record is simply excluded
from the composite.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable

from pydantic_ai import Agent
from temporalio import activity

from .models import QualityScore
from .vetoes import VetoConfigError, check, parse_vetoes


@dataclass
class JudgeInput:
    artifact_json: str          # the stage's emitted artifact, serialized
    rubric: str                 # rubric markdown/text for this case+stage
    author_model: str           # to assert cross-family at call time
    judge_model: str | None = None     # model the judge should USE (A1)
    # E-83: raw YAML text of this stage's vetoes. A STRING, not parsed
    # objects: JudgeInput crosses a Temporal activity boundary, and plain
    # text serializes under any converter -- the same reason `rubric` and
    # `artifact_json` are strings. Empty means no vetoes.
    vetoes_yaml: str = ""


def _build_judge_input(artifact_json: str, rubrics: dict[str, str],
                       stage: str, author_model: str,
                       judge_model: str | None,
                       vetoes: dict[str, str] | None = None) -> JudgeInput | None:
    """Build a JudgeInput iff a rubric is registered for ``stage``.

    ``stage`` is the rubric-map key — i.e. the keys carried on
    ``BenchmarkConfig.rubrics`` (populated from ``CaseSpec.rubrics`` by
    ``load_case_assets``): e.g. ``clarifier`` / ``architect``. It is NOT
    necessarily the record's ``stage`` field, which uses a different
    vocabulary (``clarify`` / ``architecture``).

    Returns ``None`` when no rubric exists for the stage (or it is empty),
    so the workflow skips judging and emits the record with a graceful
    ``quality_score=None`` instead. Pure function — no I/O — so it can be
    unit-tested without a Temporal environment.
    """
    rubric = rubrics.get(stage, "")
    if not rubric:
        return None
    return JudgeInput(
        artifact_json=artifact_json,
        rubric=rubric,
        author_model=author_model,
        judge_model=judge_model,
        vetoes_yaml=(vetoes or {}).get(stage, ""),
    )


JudgeFn = Callable[[JudgeInput], str]
_judge_fn: JudgeFn | None = None


def _set_judge_fn(fn: JudgeFn | None) -> None:
    global _judge_fn
    _judge_fn = fn


_JUDGE_SYSTEM_PROMPT = (
    "You are an impartial quality judge. Work through the supplied "
    "evaluation steps in order and score the artifact against them. "
    "Respond with ONLY a JSON object of exactly this shape and nothing else "
    "(no prose, no markdown fences):\n"
    '  {"score": <float between 0.0 and 1.0>, '
    '"components": {<name>: <float between 0.0 and 1.0>}}\n'
    "The overall \"score\" must reflect the artifact's rubric compliance; "
    "each component score must be grounded in a named rubric criterion. "
    "Do not invent components the rubric does not name."
)

_STEPS_SYSTEM_PROMPT = (
    "You convert a grading rubric into an explicit, ordered checklist an "
    "impartial judge will follow. Each step must be a single concrete "
    "check, phrased so two judges would agree on whether it holds, and must "
    "name the rubric component it belongs to. Do not score anything. "
    "Respond with ONLY a JSON object of exactly this shape and nothing else "
    "(no prose, no markdown fences):\n"
    '  {"steps": ["<step>", "<step>", ...]}'
)

# (sha256(rubric), judge_model) -> steps. Baseline and working MUST be scored
# against identical steps or the A/B comparison is not a comparison; caching
# is what guarantees that within a process, and is why one rubric costs one
# generation call rather than one per artifact.
_STEP_CACHE: dict[tuple[str, str], list[str]] = {}


def _clear_step_cache() -> None:
    _STEP_CACHE.clear()


def generate_steps(rubric: str, judge_model: str) -> list[str]:
    """Phase 1: rubric text -> ordered evaluation steps.

    Raises on any failure. The caller turns that into
    QualityScore(score=None, judge="error") -- falling back to the raw rubric
    would silently restore the single-shot judge under the staged label.
    """
    key = (sha256(rubric.encode()).hexdigest(), judge_model)
    if key in _STEP_CACHE:
        return _STEP_CACHE[key]
    raw = _run_judge_agent(judge_model, _STEPS_SYSTEM_PROMPT,
                           f"Rubric:\n{rubric}")
    steps = json.loads(raw).get("steps") or []
    if not isinstance(steps, list) or not steps:
        raise ValueError(
            f"step generation returned no steps for rubric sha {key[0][:12]}")
    _STEP_CACHE[key] = [str(s) for s in steps]
    return _STEP_CACHE[key]


def _run_judge_agent(model, system_prompt: str, user_prompt: str) -> str:
    """Construct a Pydantic AI agent lazily and run it synchronously.

    The agent is built per call (never at module import) to avoid the
    eager-construction smell that bit ``agents/roles.py``. Kept as a small,
    explicitly-patchable seam: ``TestModel`` cannot flow through
    ``JudgeInput.judge_model`` (typed ``str | None``), so tests patch this
    helper rather than the ``Agent`` class.
    """
    agent = Agent(model, name="benchmark_judge", system_prompt=system_prompt)
    result = agent.run_sync(user_prompt)
    return result.output


def _default_judge(inp: JudgeInput) -> str:
    """Production default: two staged calls on the configured cross-family
    judge model. Phase 1 turns the rubric into an explicit checklist (cached
    per rubric sha); phase 2 scores the artifact against that checklist.

    Returns the raw JSON string; parsing, clamping, veto application and
    error-handling live in _judge_sync.
    """
    if inp.judge_model is None:
        raise RuntimeError(
            "no judge_model configured; cannot run production judge "
            "(set BenchmarkConfig.judge_model or inject a fn via "
            "_set_judge_fn)")
    steps = generate_steps(inp.rubric, inp.judge_model)
    checklist = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    user_prompt = (
        f"Evaluation steps:\n{checklist}\n\n"
        f"Rubric (for component names and weights):\n{inp.rubric}\n\n"
        f"Artifact:\n{inp.artifact_json}")
    return _run_judge_agent(
        inp.judge_model, _JUDGE_SYSTEM_PROMPT, user_prompt)


def _judge_sync(inp: JudgeInput) -> QualityScore:
    # Vetoes FIRST and outside the judge's try: they are deterministic, so a
    # malformed veto file is a config error (not measured), while a veto that
    # FIRES is a measurement that succeeded and must survive a judge failure.
    try:
        vetoes = parse_vetoes(inp.vetoes_yaml)
        artifact = json.loads(inp.artifact_json) if vetoes else {}
        failures = check(artifact, vetoes) if vetoes else []
    except (VetoConfigError, json.JSONDecodeError):
        return QualityScore(score=None, judge="error")

    fn = _judge_fn or _default_judge
    try:
        payload = json.loads(fn(inp))
        score = max(0.0, min(1.0, float(payload.get("score", 0.0))))
        components = dict(payload.get("components") or {})
    except Exception:
        if not failures:
            return QualityScore(score=None, judge="error")
        # A veto fired. That IS a finding, and discarding it because the
        # advisory judge fell over would throw away the sharper signal.
        score, components = 0.0, {}

    if failures:
        for f in failures:
            components[f.veto_id] = 0.0
        score = 0.0
    return QualityScore(score=score, components=components,
                        judge="staged_rubric")


@activity.defn
async def judge_artifact(inp: JudgeInput) -> QualityScore:
    return _judge_sync(inp)


# test convenience
judge_artifact.sync = _judge_sync   # type: ignore[attr-defined]


# Repo root, derived from this module's location (editable install resolves
# __file__ to the worktree source). Used to locate golden-case dirs:
#   <root>/benchmarks/cases/<case_id>/
_CASES_DIR = Path(__file__).resolve().parents[3] / "benchmarks" / "cases"


@activity.defn
async def load_case_assets(case_id: str,
                           rubric_files: dict[str, str]) -> dict[str, str]:
    """Read each rubric file and return {stage: rubric_text}.

    ``rubric_files`` is the CaseSpec.rubrics map (stage -> file path). Paths
    may be absolute or relative to the case dir
    (``benchmarks/cases/<case_id>/``). A missing file is skipped — that stage
    simply won't be judged — so the workflow never crashes on a absent rubric.

    All filesystem I/O lives here (the activity); the workflow passes only
    serializable args (``case_id`` + the path map).
    """
    case_dir = _CASES_DIR / case_id
    out: dict[str, str] = {}
    for stage, rel in rubric_files.items():
        p = Path(rel) if Path(rel).is_absolute() else case_dir / rel
        if p.exists():
            out[stage] = p.read_text(encoding="utf-8")
    return out
