from pathlib import Path

import pytest

from sdlc.benchmarks.corpus import load_corpus, smoke_case
from sdlc.benchmarks.matrix import expand_matrix
from sdlc.benchmarks.models import CaseRole, CaseVisibility

CASES_ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"

CORPUS_BASE_CELL_IDS = {
    "cat-cafe-monitoring": "cat-cafe-monitoring#opencode#zai-coding-plan-glm-5.2",
    "deveval-geotext": "deveval-geotext#opencode#zai-coding-plan-glm-5.2",
    "deveval-hone": "deveval-hone#opencode#zai-coding-plan-glm-5.2",
    "deveval-lice": "deveval-lice#opencode#zai-coding-plan-glm-5.2",
    "deveval-particle-swarm-optimization": (
        "deveval-particle-swarm-optimization#opencode#zai-coding-plan-glm-5.2"
    ),
    "deveval-readtime": "deveval-readtime#opencode#zai-coding-plan-glm-5.2",
    "deveval-stocktrends": "deveval-stocktrends#opencode#zai-coding-plan-glm-5.2",
}


def test_load_corpus_returns_ten_specs_with_roles_and_visibilities():
    specs = load_corpus(CASES_ROOT)
    assert len(specs) == 10
    by_id = {s.case_id: s for s in specs}

    assert by_id["todo-api-greenfield"].role == CaseRole.SMOKE
    assert by_id["cat-cafe-monitoring"].role == CaseRole.CORPUS
    assert by_id["cat-cafe-monitoring"].visibility == CaseVisibility.PRIVATE

    deveval_ids = [
        "deveval-geotext",
        "deveval-hone",
        "deveval-lice",
        "deveval-particle-swarm-optimization",
        "deveval-readtime",
        "deveval-stocktrends",
    ]
    for cid in deveval_ids:
        assert by_id[cid].role == CaseRole.CORPUS
        assert by_id[cid].visibility == CaseVisibility.PUBLIC

    assert by_id["add-login-greenfield"].role == CaseRole.PROBE
    assert by_id["add-login-greenfield"].visibility == CaseVisibility.PRIVATE
    assert by_id["crew-probe"].role == CaseRole.PROBE
    assert by_id["crew-probe"].visibility == CaseVisibility.PRIVATE


def test_smoke_case_resolution_and_errors(tmp_path):
    s = smoke_case(CASES_ROOT)
    assert s.case_id == "todo-api-greenfield"

    case_yaml_template = (
        "case_id: {cid}\n"
        "idea_summary: s\n"
        "harnesses: [opencode]\n"
        "models: [m]\n"
        "judge_model: j\n"
        "role: {role}\n"
    )

    # zero smoke cases on tmp_path corpus raises error
    (tmp_path / "case1").mkdir()
    (tmp_path / "case1" / "case.yaml").write_text(
        case_yaml_template.format(cid="case1", role="corpus"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="smoke"):
        smoke_case(tmp_path)

    # two smoke cases on tmp_path corpus raises error
    (tmp_path / "case2").mkdir()
    (tmp_path / "case2" / "case.yaml").write_text(
        case_yaml_template.format(cid="case2", role="smoke"),
        encoding="utf-8",
    )
    (tmp_path / "case1" / "case.yaml").write_text(
        case_yaml_template.format(cid="case1", role="smoke"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="smoke"):
        smoke_case(tmp_path)


def test_seven_corpus_cases_have_two_arms_and_matching_base_cells():
    specs = load_corpus(CASES_ROOT)
    by_id = {s.case_id: s for s in specs}

    for cid, base_cell_id in CORPUS_BASE_CELL_IDS.items():
        spec = by_id[cid]
        assert spec.strong_arm == "zai-coding-plan-glm-5.2"
        assert spec.weak_arm == "zai-coding-plan-glm-5.3-flash"

        arm_map = {a.name: a for a in spec.arms}
        assert set(arm_map.keys()) == {
            "zai-coding-plan-glm-5.2",
            "zai-coding-plan-glm-5.3-flash",
        }
        for arm in spec.arms:
            assert set(arm.role_models.keys()) == {"dev", "test", "devops"}

        cells = expand_matrix(spec)
        assert len(cells) == 2
        strong_cell = next(c for c in cells if c.arm_name == spec.strong_arm)
        assert strong_cell.cell_id == base_cell_id


def test_reference_isolation_fr031():
    import ast
    import inspect

    from sdlc.benchmarks.paths import cases_dir
    from sdlc.benchmarks.workflow import BenchmarkWorkflow

    root = cases_dir()
    for case_dir in root.iterdir():
        if not case_dir.is_dir():
            continue
        ref_dir = case_dir / "reference"
        if not ref_dir.is_dir():
            continue
        case_yaml_text = (case_dir / "case.yaml").read_text(encoding="utf-8")
        assert "reference/" not in case_yaml_text

        # For every file under reference/, no path under reference/ is named in case.yaml
        for p in ref_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(ref_dir).as_posix()
                assert f"reference/{rel}" not in case_yaml_text

    # The function that seeds a run (execute_pipeline_child in BenchmarkWorkflow)
    # is given no path under Cases (seeded=None).
    import textwrap

    source = inspect.getsource(BenchmarkWorkflow.run)
    tree = ast.parse(textwrap.dedent(source))
    found_call = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "execute_pipeline_child"
        ):
            found_call = True
            kw_names = {kw.arg: kw.value for kw in node.keywords}
            assert "seeded" in kw_names
            val = kw_names["seeded"]
            assert isinstance(val, ast.Constant) and val.value is None
    assert found_call
