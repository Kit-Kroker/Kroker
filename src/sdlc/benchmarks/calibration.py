"""Rubric-judge calibration (E-36, FR-110).

Offline measurement tool: hand-score a sample of rubric fixtures, run the
cross-family judge over the same fixtures, report judge-human agreement.
Advisory only -- never modifies a composite score or a gate outcome.

Pure compute here; the CLI (cli.py) owns file I/O and the live-history seam.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


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
