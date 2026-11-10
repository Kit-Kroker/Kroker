from __future__ import annotations

import ast
from pathlib import Path

import pytest
from test_factory_purity import GRAPH_MODULES, _load_class, _methods

from sdlc.agents.roles import PROMPT_SHAS

# Spec A "stage surgery": _cached_stage lives on the RoleHost mixin;
# the cached-stage calls live in the slices. 020 T026: the _pipeline term
# is gone with FeatureWorkflow — the slices alone satisfy the count, and
# the model-literal scan sweeps the graph modules.
ROLE_HOST_PY = Path(__file__).resolve().parents[1] / "src" / "sdlc" / "workflows" / "role_host.py"
CLARIFY_STEP_PY = (
    Path(__file__).resolve().parents[1] / "src" / "sdlc" / "stages" / "clarify" / "step.py"
)
ARCH_STEP_PY = (
    Path(__file__).resolve().parents[1] / "src" / "sdlc" / "stages" / "architecture" / "step.py"
)
PLAN_STEP_PY = Path(__file__).resolve().parents[1] / "src" / "sdlc" / "stages" / "plan" / "step.py"


@pytest.fixture(scope="module")
def role_host_class():
    source = ROLE_HOST_PY.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(ROLE_HOST_PY))
    return _load_class(tree, "RoleHost")


def test_prompt_shas_cover_the_cached_stages():
    for stage in ("clarify", "architect", "plan", "devops"):
        assert stage in PROMPT_SHAS
        assert len(PROMPT_SHAS[stage]) == 64  # sha256 hex digest


def test_cached_stage_helper_exists(role_host_class):
    methods = _methods(role_host_class)
    assert "_cached_stage" in methods


def test_the_slices_use_cached_stage_for_clarify_architect_plan():
    """Spec A: the cached-stage calls live in the slices
    (ctx.cached_stage in step.py); 020 T026 drops the workflow term —
    the three slices carry the count on their own."""
    slice_src = ast.unparse(ast.parse(CLARIFY_STEP_PY.read_text(encoding="utf-8")))
    arch_slice_src = ast.unparse(ast.parse(ARCH_STEP_PY.read_text(encoding="utf-8")))
    plan_slice_src = ast.unparse(ast.parse(PLAN_STEP_PY.read_text(encoding="utf-8")))
    assert (
        slice_src.count("ctx.cached_stage(")
        + arch_slice_src.count("ctx.cached_stage(")
        + plan_slice_src.count("ctx.cached_stage(")
        >= 3
    )


def test_cached_stage_resolves_the_model_itself(role_host_class):
    """_cached_stage resolves the model internally via resolve_role_model,
    mirroring its PROMPT_SHAS[stage] lookup — one resolution point, so the
    two stage-keyed maps cannot disagree about what a stage is. E-37 moved
    the lookup behind resolve_role_model so a per-run override moves the key."""
    methods = _methods(role_host_class)
    src = ast.unparse(methods["_cached_stage"])
    assert "resolve_role_model(cfg, stage)" in src
    assert "PROMPT_SHAS[stage]" in src


def test_no_hardcoded_model_literals_in_the_workflow():
    """Five benchmark records hardcoded the author model, so they lied the
    moment any role's model changed. The registry is the only source.
    020 T026: the scan sweeps the graph modules (graph_nodes/*.py +
    graph.py + graph_dispatch.py)."""
    for path in GRAPH_MODULES:
        source = path.read_text(encoding="utf-8")
        assert "anthropic:glm-5.2" not in source, path.name
        assert "zai-coding-plan/glm-5.2" not in source, path.name
        assert "zai:glm-5.3" not in source, path.name  # 005: the new proposer id
