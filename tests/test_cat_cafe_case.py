"""Tests for cat-cafe-monitoring case structure, mapping, grown oracle, and reference (T013)."""

import ast
import re
from pathlib import Path

import pytest
import yaml

from sdlc.benchmarks.offline_checks import run_floor_check, run_reference_check
from sdlc.benchmarks.tasks import load_task_suite

CASE_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "cases" / "cat-cafe-monitoring"

# Pinned literal copied from base manifest (FR-028)
PINNED_DESCRIPTION = (
    "Ten cats live in the café. Each cat wears a smart collar that sends the\n"
    "cat's exact coordinates and the cat's breathing rate. Sensor data arrives\n"
    "every 5 seconds.\n\n"
    "Generate this sensor data randomly. Do not build collar data emulators.\n"
    "Keep it as simple as possible.\n\n"
    "The café floor plan includes the coordinates of rest areas, litter boxes,\n"
    "water bowls, and food bowls.\n\n"
    "Anything not described here is your choice — the rules are up to you. The\n"
    "functional requirements below must not be changed: do not make them\n"
    "smaller and do not add new ones.\n\n"
    "Task 1. Activity Detection\n"
    "Detect the current activity of each cat from collar telemetry and distance\n"
    "to café zones. The detectable activities are: sleeping, eating, drinking,\n"
    "using the litter box, playing, and fighting.\n\n"
    "Task 2. Monitoring\n"
    "Show in real time on the café floor plan: the movement of all cats; the\n"
    "possible current activity of each cat from Task 1; and a risk analysis for\n"
    "each cat's life or health based on collar data. Cats with a detected life\n"
    "or health risk must be marked in red.\n\n"
    "For each cat the user must also be able to see detailed sensor data and\n"
    "movement history for the last 24 hours.\n\n"
    "Interface contract (frozen — graded through it; not a functional\n"
    "requirement and it changes none of the tasks above):\n"
    "Implement in Python. Expose an ASGI application object importable as\n"
    "`app:app` (module `app.py` at the repo root, attribute named `app`).\n"
    "Importing `app:app` must not auto-start the random telemetry generator;\n"
    "the simulation runs only when launched explicitly (e.g. `python app.py`).\n"
    "  POST /telemetry {cat_id, x, y, breathing_rate, timestamp} -> 2xx;\n"
    "    the reading is processed exactly as if a collar emitted it, and a\n"
    "    reading for a new cat_id begins tracking that cat.\n"
    '  GET /floorplan -> 200 {"zones": [{kind, x, y}, ...]} with kind one of\n'
    "    rest_area | litter_box | water_bowl | food_bowl; richer zone shapes\n"
    "    are allowed and all coordinates are your choice.\n"
    "  GET /cats -> 200 [{id, x, y, activity, at_risk}, ...]; activity is one\n"
    "    of sleeping | eating | drinking | litter_box | playing | fighting,\n"
    "    or null when undetermined; at_risk is a boolean.\n"
    "  GET /cats/{id} -> 200 detail with the latest reading and history: that\n"
    "    cat's readings {timestamp, x, y, breathing_rate} from the last 24\n"
    "    hours relative to the cat's newest reading (never the wall clock);\n"
    "    unknown id -> 404.\n"
    "Timestamps are ISO-8601 strings supplied by the caller; detection and\n"
    "the 24-hour window are computed from telemetry timestamps.\n"
)

# Approved requirements from cat-cafe-requirements.md: (error_class, present, target)
APPROVED_REQUIREMENTS: dict[str, tuple[str, int, int]] = {
    "act_eating": ("functional", 1, 2),
    "act_drinking": ("functional", 1, 2),
    "act_sleeping": ("functional", 1, 2),
    "act_litter_box": ("functional", 1, 2),
    "act_playing_fighting": ("functional", 1, 3),
    "act_vocabulary": ("api_contract", 0, 2),
    "mon_movement": ("functional", 1, 3),
    "mon_floorplan": ("api_contract", 0, 3),
    "mon_cats_shape": ("api_contract", 0, 2),
    "mon_detail": ("functional", 1, 3),
    "mon_history_window": ("data_integrity", 1, 3),
    "mon_unknown_cat": ("error_handling", 1, 1),
    "risk_flag": ("functional", 3, 5),
    "telemetry_ingest": ("api_contract", 0, 2),
    "import_no_autostart": ("api_contract", 0, 1),
}

# The 12 baseline tests from T012
BASELINE_12_TESTS = {
    "test_activity.py::test_stationary_at_food_bowl_is_eating",
    "test_activity.py::test_stationary_at_water_bowl_is_drinking",
    "test_activity.py::test_resting_low_bpm_is_sleeping",
    "test_activity.py::test_stationary_at_litter_box_is_litter_box",
    "test_activity.py::test_colocated_fast_high_bpm_is_playing_or_fighting",
    "test_monitoring.py::test_post_moves_cat_on_cats_view",
    "test_monitoring.py::test_history_contains_injected_readings",
    "test_monitoring.py::test_history_window_is_24h_from_newest_reading",
    "test_monitoring.py::test_unknown_cat_is_404",
    "test_risk.py::test_sustained_180_bpm_at_rest_is_risk",
    "test_risk.py::test_sustained_5_bpm_is_risk",
    "test_risk.py::test_calm_resting_cat_is_not_risk",
}


def test_task_suite_matches_all_15_approved_requirements():
    suite = load_task_suite("cat-cafe-monitoring")
    assert suite is not None, "tasks.yaml missing for cat-cafe-monitoring"
    assert len(suite.tasks) == 15

    suite_map = {t.id: t for t in suite.tasks}
    total_tests = 0
    for req_id, (err_class, present_count, target_count) in APPROVED_REQUIREMENTS.items():
        assert req_id in suite_map, f"missing requirement {req_id}"
        t = suite_map[req_id]
        assert t.error_class == err_class, f"{req_id} error_class mismatch"
        count = len(t.oracle_tests)
        assert count >= present_count, f"{req_id} has fewer tests than present count"
        assert count == target_count, f"{req_id} test count != target {target_count}"
        total_tests += count

    assert 30 <= total_tests <= 40
    assert total_tests == 36


def test_every_oracle_test_is_in_exactly_one_requirement():
    oracle_dir = CASE_DIR / "oracle"
    discovered_tests: set[str] = set()

    for py_file in oracle_dir.glob("test_*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    discovered_tests.add(f"{py_file.name}::{node.name}")

    suite = load_task_suite("cat-cafe-monitoring")
    assert suite is not None

    all_mapped_tests: list[str] = []
    for t in suite.tasks:
        for nid in t.oracle_tests:
            all_mapped_tests.append(nid)

    assert len(all_mapped_tests) == len(set(all_mapped_tests)), "Duplicate mapped test found"
    assert set(all_mapped_tests) == discovered_tests
    assert 30 <= len(discovered_tests) <= 40
    assert len(discovered_tests) == 36


def test_oracle_tests_have_docstrings_citing_requirement():
    oracle_dir = CASE_DIR / "oracle"
    suite = load_task_suite("cat-cafe-monitoring")
    assert suite is not None

    nid_to_req = {}
    for t in suite.tasks:
        for nid in t.oracle_tests:
            nid_to_req[nid] = t.id

    for py_file in oracle_dir.glob("test_*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    nid = f"{py_file.name}::{node.name}"
                    if nid not in BASELINE_12_TESTS:
                        doc = ast.get_docstring(node)
                        assert doc is not None and doc.strip(), f"{nid} missing docstring"
                        req_id = nid_to_req.get(nid)
                        assert req_id is not None, f"{nid} not mapped in tasks.yaml"
                        assert req_id in doc, f"{nid} docstring does not cite {req_id}: {doc!r}"


def test_oracle_has_no_forbidden_patterns():
    oracle_dir = CASE_DIR / "oracle"
    for py_file in oracle_dir.glob("test_*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert not re.search(r"\b(time\.sleep|asyncio\.sleep)\b", text), (
            f"sleep found in {py_file.name}"
        )
        assert not re.search(r"\bimport\s+sleep\b|\bfrom\s+\S+\s+import\s+.*\bsleep\b", text), (
            f"sleep import found in {py_file.name}"
        )
        assert not re.search(r"\bimport\s+random\b|\bfrom\s+random\b", text), (
            f"random found in {py_file.name}"
        )
        assert "datetime.now" not in text, f"datetime.now found in {py_file.name}"
        assert "time.time" not in text, f"time.time found in {py_file.name}"

        tree = ast.parse(text, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "sleep":
                    raise AssertionError(f"sleep call found in {py_file.name}")
                if isinstance(node.func, ast.Attribute) and node.func.attr in (
                    "sleep",
                    "now",
                    "time",
                ):
                    raise AssertionError(f"forbidden call {node.func.attr} in {py_file.name}")


def test_no_numeric_literal_passed_as_zone_coordinate():
    """Rule 2 / tasks.md: no numeric literal is passed as a zone coordinate

    (the tests take coordinates from the helpers).
    """
    oracle_dir = CASE_DIR / "oracle"
    zone_activities = {
        "test_stationary_at_food_bowl_is_eating",
        "test_stationary_at_water_bowl_is_drinking",
        "test_resting_low_bpm_is_sleeping",
        "test_stationary_at_litter_box_is_litter_box",
        "test_two_cats_different_zones_one_eating",
        "test_two_cats_different_zones_one_drinking",
        "test_two_cats_different_zones_one_sleeping",
        "test_two_cats_different_zones_one_litter_box",
        "test_sustained_180_bpm_at_rest_is_risk",
        "test_sustained_5_bpm_is_risk",
        "test_calm_resting_cat_is_not_risk",
        "test_risk_is_independent_per_cat",
    }
    for py_file in oracle_dir.glob("test_*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in zone_activities
            ):
                # Ensure stationary(...) call does not pass raw numbers for x and y
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        fn_name = getattr(child.func, "id", "")
                        if fn_name == "stationary":
                            assert len(child.args) >= 2
                            assert not isinstance(child.args[0], ast.Constant), (
                                f"{node.name} passes literal x"
                            )
                            assert not isinstance(child.args[1], ast.Constant), (
                                f"{node.name} passes literal y"
                            )


def test_cat_cafe_manifest_description_pinned():
    case_yaml = CASE_DIR / "case.yaml"
    raw = yaml.safe_load(case_yaml.read_text(encoding="utf-8"))
    assert raw.get("description") == PINNED_DESCRIPTION


def test_reference_app_exists_and_does_not_import_oracle():
    ref_dir = CASE_DIR / "reference"
    app_py = ref_dir / "app.py"
    assert app_py.is_file(), "reference/app.py does not exist"

    for py_file in ref_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "oracle" not in alias.name, f"reference imports oracle in {py_file.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "oracle" not in node.module, (
                        f"reference imports from oracle in {py_file.name}"
                    )


@pytest.mark.slow
def test_real_offline_checks_on_cat_cafe():
    ref_res = run_reference_check(CASE_DIR)
    assert ref_res.passed is True, f"reference check failed: {ref_res.detail}"
    assert ref_res.tests_passed == 36
    assert ref_res.tests_total == 36

    floor_res = run_floor_check(CASE_DIR)
    assert floor_res.passed is True
    assert floor_res.tests_passed == 0
    assert floor_res.tests_passed < ref_res.tests_passed
