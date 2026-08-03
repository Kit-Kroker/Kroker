"""_stage_record calls workflow.info(), so it cannot run outside a Temporal
context. Following tests/test_pending_wiring.py, assert the signature and
the call-site wiring from source instead of spinning up a server."""
from __future__ import annotations

import inspect
import pathlib

from sdlc.workflows.feature import FeatureWorkflow

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def test_stage_record_accepts_waste():
    sig = inspect.signature(FeatureWorkflow._stage_record)
    assert "waste" in sig.parameters
    assert sig.parameters["waste"].default is None


def test_feature_imports_waste_bag():
    assert "WasteBag" in SRC.read_text(encoding="utf-8")


def test_code_stage_record_passes_the_session_digest():
    """The stage='code' record is the ONE site where a HarnessRunResult with
    a digest exists per task attempt."""
    src = SRC.read_text(encoding="utf-8")
    assert "waste=WasteBag.from_digest(run.session_digest)" in src


def test_only_one_call_site_passes_waste():
    """Proposer stages have no transcript; passing waste anywhere else would
    fabricate a measurement."""
    src = SRC.read_text(encoding="utf-8")
    assert src.count("waste=WasteBag.from_digest") == 1
