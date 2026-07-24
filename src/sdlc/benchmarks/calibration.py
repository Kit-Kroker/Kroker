"""Rubric-judge calibration (E-36, FR-110).

Offline measurement tool: hand-score a sample of rubric fixtures, run the
cross-family judge over the same fixtures, report judge-human agreement.
Advisory only -- never modifies a composite score or a gate outcome.

Pure compute here; the CLI (cli.py) owns file I/O and the live-history seam.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, TYPE_CHECKING

from pydantic import BaseModel, Field

from ..agents.loader import model_family
from .models import QualityScore

if TYPE_CHECKING:
    from .judge import JudgeInput


class CalibrationFixture(BaseModel):
    artifact_json: str
    rubric_ref: str                       # e.g. "cat-cafe-monitoring/architect"
    rubric_text: str                      # pinned at capture -> reproducible
    rubric_sha: str
    author_model: str
    human_score: float | None = None      # None => unscored, skipped
    human_components: dict[str, float] = Field(default_factory=dict)
    scored_by: str | None = None
    notes: str | None = None


def rubric_sha_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_capture_fixture(artifact_json: str, author_model: str,
                         rubric_ref: str, rubric_text: str) -> CalibrationFixture:
    return CalibrationFixture(
        artifact_json=artifact_json, rubric_ref=rubric_ref,
        rubric_text=rubric_text, rubric_sha=rubric_sha_of(rubric_text),
        author_model=author_model, human_score=None)


def write_fixture(fx: CalibrationFixture, rubric_dir: Path, name: str) -> Path:
    rubric_dir.mkdir(parents=True, exist_ok=True)
    p = rubric_dir / f"{name}.json"
    p.write_text(fx.model_dump_json(indent=2), encoding="utf-8")
    return p


def load_scored_fixtures(rubric_dir: Path) -> list[CalibrationFixture]:
    if not rubric_dir.is_dir():
        return []
    out: list[CalibrationFixture] = []
    for p in sorted(rubric_dir.glob("*.json")):
        if p.name == "calibration.json":
            continue
        try:
            fx = CalibrationFixture.model_validate_json(
                p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if fx.human_score is not None:
            out.append(fx)
    return out


def _ranks(xs: list[float]) -> list[float]:
    """Average ranks (1-based), ties share the mean of their positions."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    denx = sum((a - mx) ** 2 for a in rx)
    deny = sum((b - my) ** 2 for b in ry)
    if denx == 0 or deny == 0:      # zero variance -> correlation undefined
        return 0.0
    result = num / (denx ** 0.5 * deny ** 0.5)
    # Round to handle floating point precision (e.g., perfect correlation may be 0.9999999999999998)
    return round(result, 15)


class AgreementStats(BaseModel):
    n: int
    epsilon: float
    threshold: float
    agreement_rate: float
    mae: float
    spearman: float
    verdict: Literal["calibrated", "uncalibrated"]


def compute_agreement(pairs: list[tuple[float, float]],
                      epsilon: float = 0.15,
                      threshold: float = 0.75) -> AgreementStats:
    """pairs are (human, judge). Verdict is 'calibrated' iff the within-epsilon
    agreement rate meets the threshold."""
    n = len(pairs)
    if n == 0:
        return AgreementStats(n=0, epsilon=epsilon, threshold=threshold,
                              agreement_rate=0.0, mae=0.0, spearman=0.0,
                              verdict="uncalibrated")
    diffs = [abs(j - h) for h, j in pairs]
    # Use a small tolerance for floating point boundary condition
    agree = sum(1 for d in diffs if d <= epsilon + 1e-9) / n
    mae = sum(diffs) / n
    sp = _spearman([h for h, _ in pairs], [j for _, j in pairs])
    verdict = "calibrated" if agree >= threshold else "uncalibrated"
    return AgreementStats(n=n, epsilon=epsilon, threshold=threshold,
                          agreement_rate=agree, mae=mae, spearman=sp,
                          verdict=verdict)


_log = logging.getLogger(__name__)

JudgeScoreFn = Callable[["JudgeInput"], "QualityScore"]


class CalibrationReport(BaseModel):
    rubric: str
    judge_model: str
    n_fixtures: int
    epsilon: float
    threshold: float
    agreement_rate: float
    mae: float
    spearman: float
    verdict: str
    computed_at: datetime


def _default_judge(inp: JudgeInput) -> QualityScore:
    # judge_artifact.sync is attached in judge.py as a test/sync convenience.
    from .judge import judge_artifact
    return judge_artifact.sync(inp)


def run_calibration(rubric: str, fixtures: list[CalibrationFixture],
                    judge_model: str, *, epsilon: float = 0.15,
                    threshold: float = 0.75, now: datetime | None = None,
                    judge: JudgeScoreFn | None = None) -> CalibrationReport:
    from .judge import JudgeInput
    judge = judge or _default_judge
    now = now or datetime.now(timezone.utc)
    pairs: list[tuple[float, float]] = []
    for fx in fixtures:
        if fx.human_score is None:
            continue
        if model_family(judge_model) == model_family(fx.author_model):
            _log.warning(
                "calibration: skipping fixture (judge %s shares family with "
                "author %s; ADR-6)", judge_model, fx.author_model)
            continue
        qs = judge(JudgeInput(artifact_json=fx.artifact_json,
                              rubric=fx.rubric_text,
                              author_model=fx.author_model,
                              judge_model=judge_model))
        if qs.score is None:            # judge errored -> exclude, never crash
            continue
        pairs.append((fx.human_score, qs.score))

    stats = compute_agreement(pairs, epsilon=epsilon, threshold=threshold)
    return CalibrationReport(
        rubric=rubric, judge_model=judge_model, n_fixtures=stats.n,
        epsilon=stats.epsilon, threshold=stats.threshold,
        agreement_rate=stats.agreement_rate, mae=stats.mae,
        spearman=stats.spearman, verdict=stats.verdict, computed_at=now)


# --- Trust surfacing (E-36 Task 8): report load + render helpers ----------

_CALIB_DIR = Path(__file__).resolve().parents[3] / "benchmarks" / "calibration"

# record stage (BenchmarkSummary.stage) -> rubric key (calibration bucket)
STAGE_TO_RUBRIC: dict[str, str] = {
    "clarify": "clarifier",
    "architecture": "architect",
    "planning": "planner",
    "qa": "qa",
    "research": "research",
    "review": "reviewer",
    "analyze": "analyst",
}


def write_calibration_report(rep: CalibrationReport, rubric_dir: Path) -> Path:
    rubric_dir.mkdir(parents=True, exist_ok=True)
    p = rubric_dir / "calibration.json"
    p.write_text(rep.model_dump_json(indent=2), encoding="utf-8")
    return p


def load_calibration_reports(
        calib_root: Path | None = None) -> dict[str, CalibrationReport]:
    root = calib_root if calib_root is not None else _CALIB_DIR
    out: dict[str, CalibrationReport] = {}
    if not Path(root).is_dir():
        return out
    for cj in sorted(Path(root).glob("*/calibration.json")):
        try:
            rep = CalibrationReport.model_validate_json(
                cj.read_text(encoding="utf-8"))
        except Exception:
            continue
        out[rep.rubric] = rep
    return out


def trust_for_stage(stage: str,
                    reports: dict[str, CalibrationReport]) -> str:
    rubric = STAGE_TO_RUBRIC.get(stage)
    if rubric is None:
        return "-"                       # stage has no rubric (e.g. code)
    rep = reports.get(rubric)
    return f"{rep.agreement_rate:.2f}" if rep else "uncalibrated"


def render_calibration_markdown(
        reports: dict[str, CalibrationReport]) -> str:
    if not reports:
        return ""
    lines = ["", "## Rubric calibration", "",
             "| rubric | n | agreement | MAE | spearman | verdict |",
             "|---|---|---|---|---|---|"]
    for rubric in sorted(reports):
        r = reports[rubric]
        lines.append(f"| {rubric} | {r.n_fixtures} | {r.agreement_rate:.2f} | "
                     f"{r.mae:.3f} | {r.spearman:.2f} | {r.verdict} |")
    return "\n".join(lines) + "\n"


def render_calibration_html(
        reports: dict[str, CalibrationReport]) -> str:
    if not reports:
        return ""
    from html import escape
    rows = "".join(
        f"<tr><td>{escape(rubric)}</td><td>{reports[rubric].n_fixtures}</td>"
        f"<td>{reports[rubric].agreement_rate:.2f}</td>"
        f"<td>{reports[rubric].mae:.3f}</td>"
        f"<td>{reports[rubric].spearman:.2f}</td>"
        f"<td>{escape(reports[rubric].verdict)}</td></tr>"
        for rubric in sorted(reports))
    return ("<h2>Rubric calibration</h2><table><tr><th>rubric</th><th>n</th>"
            "<th>agreement</th><th>MAE</th><th>spearman</th><th>verdict</th></tr>"
            + rows + "</table>")
