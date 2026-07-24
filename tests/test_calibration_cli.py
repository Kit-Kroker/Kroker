from datetime import datetime, timezone

from sdlc.benchmarks.calibration import (
    CalibrationFixture, rubric_sha_of, write_fixture)
from sdlc.benchmarks.cli import dispatch_calibrate
import sdlc.benchmarks.calibration as calib


def test_dispatch_calibrate_writes_calibration_json(tmp_path, monkeypatch):
    rubric_dir = tmp_path / "architect"
    for i, human in enumerate([0.8, 0.6, 0.4]):
        fx = CalibrationFixture(
            artifact_json="{}", rubric_ref="c/architect", rubric_text="r",
            rubric_sha=rubric_sha_of("r"), author_model="zai/glm-5.2",
            human_score=human)
        write_fixture(fx, rubric_dir, f"fixt-{i:04d}")
    # stub the judge so no model call happens
    from sdlc.benchmarks.models import QualityScore
    monkeypatch.setattr(
        calib, "_default_judge",
        lambda inp: QualityScore(score=0.7, judge="llm_judge"))
    out = dispatch_calibrate("architect", judge_model="openai/gpt-5.2",
                             epsilon=0.15, threshold=0.75, calib_root=tmp_path)
    assert (rubric_dir / "calibration.json").exists()
    assert "architect" in out and "agreement" in out.lower()
