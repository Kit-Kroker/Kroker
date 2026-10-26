"""Cross-family LLM-judge for proposer-stage artifacts.

The real LLM call is behind JudgeFn so tests inject a fake and CI makes no
model calls. On any failure (exception, bad JSON, out-of-range) we return
QualityScore(score=None, judge="error", detail=<reason>) — the judge never
raises, so a broken judge can never fail a benchmark cell; the record is
simply excluded from the composite, and the detail explains why.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from pydantic_ai import Agent
from pydantic_ai.models import Model, ModelResolutionContext
from pydantic_ai.settings import ModelSettings
from temporalio import activity

from ..agents.model_ids import single_retry_layer
from ..agents.retry_policy import (
    DEFAULT_LADDER,
    DEFAULT_TRANSIENT_STATUSES,
    RetryBackoffModel,
    extract_status_and_retry_after,
    is_transient,
)
from .models import QualityScore
from .vetoes import check, parse_vetoes

# 016 ruling R3 (Names "Judge"): the judge's output budget. Without it the
# provider default applies and pydantic-ai surfaces truncation as
# "(provider default)" (V1: _agent_graph.py prints last_max_tokens or that
# text exactly when max_tokens is None). 16000 is the working start; the
# offline proof (step 6) may move it and rewrite this constant.
JUDGE_MAX_TOKENS_ENV = "SDLC_JUDGE_MAX_TOKENS"
DEFAULT_JUDGE_MAX_TOKENS = 16000


def judge_max_tokens() -> int:
    """The judge's max_tokens, read at call time (paths house style):
    SDLC_JUDGE_MAX_TOKENS when set to a non-empty value, else the default."""
    value = os.environ.get(JUDGE_MAX_TOKENS_ENV, "")
    return int(value) if value.strip() else DEFAULT_JUDGE_MAX_TOKENS


@dataclass
class JudgeInput:
    artifact_json: str  # the stage's emitted artifact, serialized
    rubric: str  # rubric markdown/text for this case+stage
    author_model: str  # to assert cross-family at call time
    judge_model: str | None = None  # model the judge should USE (A1)
    # E-83: raw YAML text of this stage's vetoes. A STRING, not parsed
    # objects: JudgeInput crosses a Temporal activity boundary, and plain
    # text serializes under any converter -- the same reason `rubric` and
    # `artifact_json` are strings. Empty means no vetoes.
    vetoes_yaml: str = ""


def _build_judge_input(
    artifact_json: str,
    rubrics: dict[str, str],
    stage: str,
    author_model: str,
    judge_model: str | None,
    vetoes: dict[str, str] | None = None,
) -> JudgeInput | None:
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


_LOGGER = logging.getLogger(__name__)

# R0 attempts 3-4 (verification.md §7.4): all four rubric calls across two
# runs died to gemini-3.5-flash 503s with zero retries — _judge_sync turns
# the exception into a graceful error score and the activity then completes
# "successfully", so Temporal's retry policy never engages. Transient
# statuses retry in RetryBackoffModel when wrapped via single_retry_layer
# (or in the legacy loop below for raw unwrapped models), at the seam both
# staged phases share; anything else (or the last attempt) still raises into
# the fail-safe in _judge_sync.
_JUDGE_RETRY_DELAYS: tuple[float, ...] = DEFAULT_LADDER
_JUDGE_RETRY_STATUSES = DEFAULT_TRANSIENT_STATUSES


def _status_of(exc: Exception) -> int | None:
    """The HTTP status behind a model-call failure, whatever the provider
    stack raised: pydantic-ai's ModelHTTPError or the raw httpx error."""
    status, _, _ = extract_status_and_retry_after(exc)
    return status


def _transient(exc: Exception) -> bool:
    """Worth a backoff retry: a transient HTTP status, or a provider hang
    (read timeout) — the R0 attempt-5 probe watched a toy prompt time out
    minutes after an identical probe returned 200."""
    status, _, timed_out = extract_status_and_retry_after(exc)
    return is_transient(status, timed_out=timed_out)


_JUDGE_SYSTEM_PROMPT = (
    "You are an impartial quality judge. Work through the supplied "
    "evaluation steps in order and score the artifact against them. "
    "Respond with ONLY a JSON object of exactly this shape and nothing else "
    "(no prose, no markdown fences):\n"
    '  {"score": <float between 0.0 and 1.0>, '
    '"components": {<name>: <float between 0.0 and 1.0>}}\n'
    'The overall "score" must reflect the artifact\'s rubric compliance; '
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
    raw = _run_judge_agent(judge_model, _STEPS_SYSTEM_PROMPT, f"Rubric:\n{rubric}")
    steps = json.loads(raw).get("steps") or []
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"step generation returned no steps for rubric sha {key[0][:12]}")
    _STEP_CACHE[key] = [str(s) for s in steps]
    return _STEP_CACHE[key]


def _run_judge_agent(model, system_prompt: str, user_prompt: str) -> str:
    """Construct a Pydantic AI agent lazily and run it synchronously.

    The agent is built per call (never at module import) to avoid the
    eager-construction smell that bit ``agents/roles.py``. Kept as a small,
    explicitly-patchable seam: ``TestModel`` cannot flow through
    ``JudgeInput.judge_model`` (typed ``str | None``), so tests patch this
    helper rather than the ``Agent`` class. 005 T012 (plan D2 site 6,
    contract C7): a string model resolves through the shared seam first, so
    a ``zai:`` judge id reaches the coding endpoint; non-zai strings build
    exactly as the framework builds them. T1 (sbatch 2026-10-19): that
    resolution runs through the single-retry layer, so the provider SDK
    keeps no retry layer of its own beneath the loop below.
    """
    if isinstance(model, str):
        # T1 (sbatch 2026-10-19): resolve the string through the
        # single-retry seam. ``single_retry_layer()``'s resolver is the
        # resolve_model chain — infer_model over the shared provider
        # factory, 005 zai URL policy included — with the provider
        # client's SDK retry count zeroed, so the backoff loop below is
        # the only retry layer inside one judge call (was: SDK default
        # max_retries=2 stacked under it, up to 12 HTTP requests per
        # always-429 call against the loop's budget of 4). The ctx argument
        # is None by design: the shared resolver ignores it, and no agent
        # exists yet at this eager resolution site (the repo's capability
        # tests pass None for the same reason).
        resolved = single_retry_layer().resolver(cast("ModelResolutionContext[Any]", None), model)
        assert isinstance(resolved, Model), "the single-retry resolver returned no model"
        model = resolved
    agent = Agent(
        model,
        name="benchmark_judge",
        system_prompt=system_prompt,
        # R3: the output budget, so truncation surfaces as a number, not
        # "(provider default)". Read at call time (env overridable).
        model_settings=ModelSettings(max_tokens=judge_max_tokens()),
    )
    if isinstance(model, RetryBackoffModel):
        return agent.run_sync(user_prompt).output

    for attempt in range(len(_JUDGE_RETRY_DELAYS) + 1):
        try:
            result = agent.run_sync(user_prompt)
        except Exception as exc:
            if not _transient(exc) or attempt >= len(_JUDGE_RETRY_DELAYS):
                raise
            delay = _JUDGE_RETRY_DELAYS[attempt]
            _LOGGER.warning(
                "judge model call failed (%s, HTTP %s) (attempt %d/%d); retrying in %ss",
                type(exc).__name__,
                _status_of(exc),
                attempt + 1,
                len(_JUDGE_RETRY_DELAYS) + 1,
                delay,
            )
            time.sleep(delay)
        else:
            return result.output
    raise AssertionError("unreachable: the loop returns or raises")


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
            "_set_judge_fn)"
        )
    steps = generate_steps(inp.rubric, inp.judge_model)
    checklist = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    user_prompt = (
        f"Evaluation steps:\n{checklist}\n\n"
        f"Rubric (for component names and weights):\n{inp.rubric}\n\n"
        f"Artifact:\n{inp.artifact_json}"
    )
    return _run_judge_agent(inp.judge_model, _JUDGE_SYSTEM_PROMPT, user_prompt)


def _judge_sync(inp: JudgeInput) -> QualityScore:
    # Vetoes FIRST and outside the judge's try: they are deterministic, so a
    # malformed veto file is a config error (not measured), while a veto that
    # FIRES is a measurement that succeeded and must survive a judge failure.
    # Broad `except Exception` on purpose: the judge's governing invariant
    # (this module's docstring) is that it NEVER raises -- a veto-engine
    # surprise (e.g. a not_both veto against a non-dict artifact) must surface
    # as not-measured, not propagate out and fail a benchmark cell.
    try:
        vetoes = parse_vetoes(inp.vetoes_yaml)
        artifact = json.loads(inp.artifact_json) if vetoes else {}
        failures = check(artifact, vetoes) if vetoes else []
    except Exception as exc:
        return QualityScore(
            score=None,
            judge="error",
            detail=f"veto config: {type(exc).__name__}: {exc}"[:400],
        )

    fn = _judge_fn or _default_judge
    try:
        payload = json.loads(fn(inp))
        score = max(0.0, min(1.0, float(payload.get("score", 0.0))))
        components = dict(payload.get("components") or {})
    except Exception as exc:
        if not failures:
            return QualityScore(
                score=None, judge="error", detail=f"{type(exc).__name__}: {exc}"[:400]
            )
        # A veto fired. That IS a finding, and discarding it because the
        # advisory judge fell over would throw away the sharper signal.
        score, components = 0.0, {}

    if failures:
        for f in failures:
            components[f.veto_id] = 0.0
        score = 0.0
    return QualityScore(score=score, components=components, judge="staged_rubric")


@activity.defn
async def judge_artifact(inp: JudgeInput) -> QualityScore:
    """012 T025: the sync judge (agent.run_sync) must run OFF the event
    loop — awaited inline it raised RuntimeError 'This event loop is
    already running', swallowed by _judge_sync into judge='error' on
    every rubric-judged stage (T024 smoke runs)."""
    return await asyncio.to_thread(_judge_sync, inp)


# test convenience
judge_artifact.sync = _judge_sync  # type: ignore[attr-defined]


@activity.defn
async def load_case_assets(case_id: str, rubric_files: dict[str, str]) -> dict[str, str]:
    """Read each rubric file and return {stage: rubric_text}.

    ``rubric_files`` is the CaseSpec.rubrics map (stage -> file path). Paths
    may be absolute or relative to the case dir, resolved through
    ``paths.case_dir()`` (012 R-1: one cases location for every reader;
    016: the lenient resolver spans the private store too).

    012 (contract §1.4): a registered file that is missing or empty RAISES
    a non-retryable ApplicationError of type ``MissingCaseAsset`` carrying
    the ``check_case_assets`` messages — the activity runs under a
    five-attempt retry policy, and a plain exception would be retried five
    times before failing the run. The run stops before the first cell is
    built, at zero model spend; a broken manifest is a manifest that names
    a file it does not ship.

    All filesystem I/O lives here (the activity); the workflow passes only
    serializable args (``case_id`` + the path map).
    """
    from temporalio.exceptions import ApplicationError

    from .paths import MISSING_CASE_ASSET, case_roots, check_case_assets, private_cases_dir
    from .paths import case_dir as resolve_case_dir

    resolved = resolve_case_dir(case_id)
    problems = check_case_assets(rubric_files, {}, resolved)
    # 016 A5 (D-6): when the case directory exists in no root, the missing
    # rubric is a symptom -- the cause is the case itself. Append one line
    # so a worker that cannot see the store says so. Only appended to an
    # existing problem list: an empty registration keeps today's behaviour.
    if problems and not resolved.is_dir():
        roots = ", ".join(str(r) for r in case_roots())
        configured = "yes" if private_cases_dir() is not None else "no"
        problems.append(
            f"case {case_id} is in no cases root ({roots}); private root configured: {configured}"
        )
    if problems:
        raise ApplicationError("\n".join(problems), type=MISSING_CASE_ASSET, non_retryable=True)

    out: dict[str, str] = {}
    for stage, rel in rubric_files.items():
        p = Path(rel) if Path(rel).is_absolute() else resolved / rel
        if p.exists():
            out[stage] = p.read_text(encoding="utf-8")
    return out
