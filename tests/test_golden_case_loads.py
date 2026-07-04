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
