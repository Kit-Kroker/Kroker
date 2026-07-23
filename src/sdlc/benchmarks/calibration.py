"""Rubric-judge calibration (E-36, FR-110).

Offline measurement tool: hand-score a sample of rubric fixtures, run the
cross-family judge over the same fixtures, report judge-human agreement.
Advisory only -- never modifies a composite score or a gate outcome.

Pure compute here; the CLI (cli.py) owns file I/O and the live-history seam.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

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
