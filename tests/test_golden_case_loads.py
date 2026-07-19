from pathlib import Path

from sdlc.benchmarks.cli import load_case_spec
from sdlc.benchmarks.matrix import expand_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
CASE = REPO_ROOT / "benchmarks" / "cases" / "add-login-greenfield" / "case.yaml"
CONFIG = REPO_ROOT / "benchmarks" / "config.yaml"


def test_default_case_file_exists_and_loads():
    assert CASE.exists(), f"missing {CASE}"
    spec = load_case_spec(str(CASE))
    assert spec.case_id == "add-login-greenfield"
    cells = expand_matrix(spec)
    assert len(cells) >= 2     # at least 2 harnesses × 1 model


def test_config_yaml_has_weights():
    assert CONFIG.exists()
    import yaml
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert "weights" in cfg
    w = cfg["weights"]
    assert abs(w["quality"] + w["cost"] + w["speed"] - 1.0) < 1e-9


def test_rubric_files_exist():
    d = CASE.parent
    assert (d / "rubric-architect.md").exists()
    assert (d / "rubric-clarifier.md").exists()


CAT_CASE = (REPO_ROOT / "benchmarks" / "cases" / "cat-cafe-monitoring"
            / "case.yaml")


def test_cat_cafe_case_loads_as_one_cell():
    assert CAT_CASE.exists(), f"missing {CAT_CASE}"
    spec = load_case_spec(str(CAT_CASE))
    assert spec.case_id == "cat-cafe-monitoring"
    assert spec.research_enabled is True
    assert len(expand_matrix(spec)) == 1


def test_cat_cafe_ships_five_rubrics():
    d = CAT_CASE.parent
    for key in ("clarifier", "architect", "planner", "qa", "research"):
        assert (d / f"rubric-{key}.md").exists(), f"missing rubric-{key}.md"


def test_cat_cafe_rubrics_are_all_registered():
    """A rubric file on disk that case.yaml does not name is dead weight;
    a named rubric with no file is silently skipped by load_case_assets."""
    spec = load_case_spec(str(CAT_CASE))
    assert set(spec.rubrics) == {
        "clarifier", "architect", "planner", "qa", "research"}
    for rel in spec.rubrics.values():
        assert (CAT_CASE.parent / rel).exists()


def test_cat_cafe_description_preserves_every_activity():
    """The kata's functional requirements must not shrink -- all six
    activities must survive into the case description."""
    spec = load_case_spec(str(CAT_CASE))
    body = spec.description.lower()
    for activity in ("sleeping", "eating", "drinking", "litter",
                     "playing", "fighting"):
        assert activity in body, f"description dropped '{activity}'"
