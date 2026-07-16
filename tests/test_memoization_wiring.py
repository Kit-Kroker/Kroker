from __future__ import annotations

import ast

import pytest

from test_factory_purity import FEATURE_PY, _load_class, _methods
from sdlc.agents.roles import PROMPT_SHAS, STAGE_MODELS


@pytest.fixture(scope="module")
def feature_class():
    source = FEATURE_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FEATURE_PY))
    return _load_class(tree, "FeatureWorkflow")


def test_prompt_shas_cover_the_cached_stages():
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


def test_cached_stage_resolves_the_model_itself(feature_class):
    """_cached_stage looks up STAGE_MODELS[stage] internally, mirroring its
    PROMPT_SHAS[stage] lookup — one resolution point, so the two stage-keyed
    maps cannot disagree about what a stage is."""
    methods = _methods(feature_class)
    src = ast.unparse(methods["_cached_stage"])
    assert "STAGE_MODELS[stage]" in src
    assert "PROMPT_SHAS[stage]" in src


def test_no_hardcoded_model_literals_in_the_workflow():
    """Five benchmark records hardcoded the author model, so they lied the
    moment any role's model changed. The registry is the only source."""
    source = FEATURE_PY.read_text(encoding="utf-8")
    assert "anthropic:glm-5.2" not in source
    assert "zai-coding-plan/glm-5.2" not in source
