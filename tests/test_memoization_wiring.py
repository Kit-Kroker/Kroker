from __future__ import annotations

import ast

import pytest

from test_factory_purity import FEATURE_PY, _load_class, _methods
from sdlc.agents.roles import PROMPT_SHAS


@pytest.fixture(scope="module")
def feature_class():
    source = FEATURE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FEATURE_PY))
    return _load_class(tree, "FeatureWorkflow")


def test_prompt_shas_cover_the_four_cached_stages():
    for stage in ("clarify", "architect", "plan", "devops"):
        assert stage in PROMPT_SHAS
        assert len(PROMPT_SHAS[stage]) == 64  # sha256 hex digest


def test_cached_stage_helper_exists(feature_class):
    methods = _methods(feature_class)
    assert "_cached_stage" in methods


def test_run_uses_cached_stage_for_clarify_architect_plan(feature_class):
    methods = _methods(feature_class)
    src = ast.unparse(methods["run"])
    assert src.count("self._cached_stage(") >= 3
