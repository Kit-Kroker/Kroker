"""Integration residual verification for Task 21."""

from __future__ import annotations

import json
import pathlib


def test_feature_py_is_under_the_ceiling():
    lines = pathlib.Path("src/sdlc/workflows/feature.py").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 1000, len(lines)


def test_the_four_src_entries_left_the_baseline():
    baseline = json.loads(pathlib.Path(".file-size-baseline.json").read_text(encoding="utf-8"))
    assert not [k for k in baseline if k.startswith("src/")], baseline
    # The one survivor is out of A's scope by the spec's "Does not cover".
    assert set(baseline) <= {"tests/test_assessment_workflow_e2e.py"}


def test_every_stage_row_says_migrated():
    table = pathlib.Path("AGENTS.md").read_text(encoding="utf-8")
    assert "in `feature.py`" not in table
    assert "types moved, step pending" not in table
