"""E-79: DevEval corpus conversion. Every test here is pure or tmp_path-
scoped -- the importer never touches the network."""
import json
from pathlib import Path

import pytest

from sdlc.benchmarks.importers.deveval import RepoConfig, load_repo_config

MANIFEST = {
    "PRD": "docs/PRD.md",
    "UML_class": "docs/UML_class.md",
    "UML_sequence": "docs/UML_sequence.md",
    "architecture_design": "docs/architecture_design.md",
    "dependencies": "docs/requirements.txt",
    "language": "python",
    "unit_tests": "unit_tests",
    "acceptance_tests": "acceptance_tests",
    "usage_examples": "examples",
    "unit_test_linking": {"unit_tests/test_a.py": ["mod.py"]},
    "code_file_DAG": {"mod.py": []},
    "incremental_development": False,
}


def test_load_repo_config_reads_every_declared_path(tmp_path):
    (tmp_path / "repo_config.json").write_text(
        json.dumps(MANIFEST), encoding="utf-8")
    cfg = load_repo_config(tmp_path)
    assert isinstance(cfg, RepoConfig)
    assert cfg.prd == "docs/PRD.md"
    assert cfg.uml_class == "docs/UML_class.md"
    assert cfg.architecture_design == "docs/architecture_design.md"
    assert cfg.language == "python"
    assert cfg.unit_test_linking == {"unit_tests/test_a.py": ["mod.py"]}
    assert cfg.code_file_dag == {"mod.py": []}


def test_load_repo_config_ignores_unknown_keys(tmp_path):
    """DevEval manifests carry prompt blobs we do not consume; extra keys
    must not break the import."""
    extra = dict(MANIFEST, coarse_unit_test_prompt={"x": "y"})
    (tmp_path / "repo_config.json").write_text(
        json.dumps(extra), encoding="utf-8")
    assert load_repo_config(tmp_path).language == "python"


def test_load_repo_config_raises_on_missing_manifest(tmp_path):
    """The importer fails loud -- it is offline, human-run, one-shot."""
    with pytest.raises(FileNotFoundError):
        load_repo_config(tmp_path)


def test_load_repo_config_raises_on_missing_required_key(tmp_path):
    broken = {k: v for k, v in MANIFEST.items() if k != "PRD"}
    (tmp_path / "repo_config.json").write_text(
        json.dumps(broken), encoding="utf-8")
    with pytest.raises(Exception):
        load_repo_config(tmp_path)


from sdlc.benchmarks.importers.deveval import collect_node_ids

TEST_SRC = '''
import unittest

def test_module_level():
    assert True

def helper_not_a_test():
    pass

class TestThing(unittest.TestCase):
    def test_method(self):
        assert True
    def setUp(self):
        pass
'''


def test_collect_node_ids_finds_functions_and_methods(tmp_path):
    d = tmp_path / "unit_tests"
    d.mkdir()
    (d / "test_a.py").write_text(TEST_SRC, encoding="utf-8")
    ids = collect_node_ids(d, "unit_tests")
    assert ids == ["unit_tests/test_a.py::test_method",
                   "unit_tests/test_a.py::test_module_level"]


def test_collect_node_ids_skips_non_test_files(tmp_path):
    d = tmp_path / "unit_tests"
    d.mkdir()
    (d / "__init__.py").write_text("", encoding="utf-8")
    (d / "conftest.py").write_text("def test_nope(): pass", encoding="utf-8")
    (d / "test_a.py").write_text("def test_one(): pass", encoding="utf-8")
    assert collect_node_ids(d, "unit_tests") == [
        "unit_tests/test_a.py::test_one"]


def test_collect_node_ids_uses_forward_slashes(tmp_path):
    d = tmp_path / "unit_tests" / "sub"
    d.mkdir(parents=True)
    (d / "test_b.py").write_text("def test_two(): pass", encoding="utf-8")
    ids = collect_node_ids(tmp_path / "unit_tests", "unit_tests")
    assert ids == ["unit_tests/sub/test_b.py::test_two"]


def test_collect_node_ids_raises_on_unparseable_test(tmp_path):
    d = tmp_path / "unit_tests"
    d.mkdir()
    (d / "test_a.py").write_text("def test_(:\n", encoding="utf-8")
    with pytest.raises(SyntaxError):
        collect_node_ids(d, "unit_tests")


from sdlc.benchmarks.importers.deveval import (draft_task_suite,
                                               render_tasks_yaml)


def test_draft_task_suite_groups_by_test_file():
    ids = ["unit_tests/test_check_date.py::test_a",
           "unit_tests/test_check_date.py::test_b",
           "acceptance_tests/test_cli.py::test_c"]
    suite = draft_task_suite(ids)
    assert suite["tasks"] == [
        {"id": "cli", "error_class": "functional",
         "oracle_tests": ["acceptance_tests/test_cli.py::test_c"]},
        {"id": "check_date", "error_class": "functional",
         "oracle_tests": ["unit_tests/test_check_date.py::test_a",
                          "unit_tests/test_check_date.py::test_b"]},
    ]


def test_draft_task_suite_ids_are_unique():
    """Same stem in two dirs must not collide -- TaskSuite rejects dupes."""
    ids = ["unit_tests/test_core.py::test_a",
           "acceptance_tests/test_core.py::test_b"]
    suite = draft_task_suite(ids)
    task_ids = [t["id"] for t in suite["tasks"]]
    assert len(task_ids) == len(set(task_ids))


def test_draft_task_suite_validates_against_the_real_loader(tmp_path):
    """The emitted draft must load through benchmarks.tasks.load_task_suite,
    or the case is dead on arrival."""
    from sdlc.benchmarks.tasks import load_task_suite
    ids = ["unit_tests/test_a.py::test_one"]
    case = tmp_path / "deveval-x"
    case.mkdir()
    (case / "tasks.yaml").write_text(
        render_tasks_yaml(draft_task_suite(ids)), encoding="utf-8")
    suite = load_task_suite("deveval-x", cases_dir=tmp_path)
    assert suite is not None
    assert suite.tasks[0].oracle_tests == ["unit_tests/test_a.py::test_one"]


def test_render_tasks_yaml_carries_a_review_banner():
    text = render_tasks_yaml(draft_task_suite(
        ["unit_tests/test_a.py::test_one"]))
    assert "REVIEW" in text


def test_draft_task_suite_rejects_empty():
    with pytest.raises(ValueError):
        draft_task_suite([])


from sdlc.benchmarks.importers.deveval import detect_network


def test_detect_network_flags_urllib(tmp_path):
    p = tmp_path / "test_q.py"
    p.write_text("import urllib.request\nurllib.request.urlopen(u)\n",
                 encoding="utf-8")
    required, evidence = detect_network([p])
    assert required is True
    assert any("urllib" in e for e in evidence)


def test_detect_network_flags_http_urls(tmp_path):
    p = tmp_path / "test_q.py"
    p.write_text('URL = "http://export.arxiv.org/api/query"\n',
                 encoding="utf-8")
    required, _ = detect_network([p])
    assert required is True


def test_detect_network_clean_file(tmp_path):
    p = tmp_path / "test_q.py"
    p.write_text("def test_add():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    assert detect_network([p]) == (False, [])


def test_detect_network_evidence_names_file_and_line(tmp_path):
    p = tmp_path / "test_q.py"
    p.write_text("x = 1\nimport requests\n", encoding="utf-8")
    _, evidence = detect_network([p])
    assert "test_q.py:2" in evidence[0]


from sdlc.benchmarks.importers.deveval import (build_case_dict, case_id_for,
                                               frozen_contract,
                                               render_case_yaml)


def test_case_id_is_slugged_and_prefixed():
    assert case_id_for("ArXiv_digest") == "deveval-arxiv-digest"
    assert case_id_for("particle-swarm-optimization") == (
        "deveval-particle-swarm-optimization")


def test_frozen_contract_contains_both_artifacts_and_a_freeze_notice():
    c = frozen_contract("# Tree\n- mod.py\n", "```mermaid\nclassDiagram\n```")
    assert "mod.py" in c
    assert "classDiagram" in c
    assert "frozen" in c.lower()


def test_build_case_dict_matches_the_CaseSpec_contract():
    """The emitted dict must construct a CaseSpec, or `benchmark run` dies
    on a case the importer swore was valid."""
    case = build_case_dict(
        case_id="deveval-x", prd="# Introduction\nA tool.\n",
        contract="CONTRACT", language="python",
        judge_model="google:gemini-3.5-flash", network_required=False,
        repo_url="/srv/scratch-repos/deveval-x")
    assert case["case_id"] == "deveval-x"
    assert case["language"] == "python"
    assert case["network_required"] is False
    assert "CONTRACT" in case["description"]
    assert "A tool." in case["description"]


def test_render_case_yaml_round_trips_through_load_case_spec(tmp_path):
    from sdlc.benchmarks.cli import load_case_spec
    case = build_case_dict(
        case_id="deveval-x", prd="# Introduction\nA tool.\n",
        contract="CONTRACT", language="python",
        judge_model="google:gemini-3.5-flash", network_required=True,
        repo_url="/srv/scratch-repos/deveval-x")
    p = tmp_path / "case.yaml"
    p.write_text(render_case_yaml(case), encoding="utf-8")
    spec = load_case_spec(str(p))
    assert spec.case_id == "deveval-x"
    assert spec.network_required is True
    assert spec.language == "python"
    assert spec.judge_model == "google:gemini-3.5-flash"


from sdlc.benchmarks.importers.deveval import ImportReport, convert_repo

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_calc"


def _convert(tmp_path):
    return convert_repo(FIXTURE, tmp_path,
                        judge_model="google:gemini-3.5-flash")


def test_convert_repo_writes_every_expected_path(tmp_path):
    report = _convert(tmp_path)
    case = tmp_path / "deveval-mini-calc"
    assert isinstance(report, ImportReport)
    for rel in ("case.yaml", "tasks.yaml", "ATTRIBUTION.md",
                "oracle/unit_tests/test_calc.py",
                "oracle/acceptance_tests/test_cli.py",
                "reference/calc.py",
                "reference_artifacts/UML_class.md",
                "reference_artifacts/UML_sequence.md",
                "reference_artifacts/architecture_design.md",
                "reference_env/requirements.txt",
                "reference_env/examples/run.sh"):
        assert (case / rel).is_file(), f"missing {rel}"


def test_convert_repo_keeps_docs_and_tests_out_of_reference(tmp_path):
    """reference/ is the gold implementation only -- shipping the oracle
    inside it would hand E-81 the answer key."""
    _convert(tmp_path)
    ref = tmp_path / "deveval-mini-calc" / "reference"
    assert not (ref / "unit_tests").exists()
    assert not (ref / "acceptance_tests").exists()
    assert not (ref / "docs").exists()
    assert not (ref / "repo_config.json").exists()


def test_convert_repo_case_yaml_loads_and_tasks_validate(tmp_path):
    from sdlc.benchmarks.cli import load_case_spec
    from sdlc.benchmarks.tasks import load_task_suite
    _convert(tmp_path)
    spec = load_case_spec(str(tmp_path / "deveval-mini-calc" / "case.yaml"))
    assert spec.case_id == "deveval-mini-calc"
    suite = load_task_suite("deveval-mini-calc", cases_dir=tmp_path)
    assert suite is not None
    assert {t.id for t in suite.tasks} == {"calc", "cli"}


def test_convert_repo_report_counts(tmp_path):
    report = _convert(tmp_path)
    assert report.case_id == "deveval-mini-calc"
    assert report.n_tasks == 2
    assert report.n_oracle_tests == 3
    assert report.network_required is False
    assert report.reference_files == 1


def test_convert_repo_refuses_to_overwrite(tmp_path):
    _convert(tmp_path)
    with pytest.raises(FileExistsError):
        _convert(tmp_path)
