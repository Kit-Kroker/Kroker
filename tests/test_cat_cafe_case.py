"""Tests for cat-cafe-monitoring case structure, mapping, and reference (T012)."""

import ast
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

APPROVED_PRESENT_REQUIREMENTS = {
    "act_eating": "functional",
    "act_drinking": "functional",
    "act_sleeping": "functional",
    "act_litter_box": "functional",
    "act_playing_fighting": "functional",
    "mon_movement": "functional",
    "mon_detail": "functional",
    "mon_history_window": "data_integrity",
    "mon_unknown_cat": "error_handling",
    "risk_flag": "functional",
}

APPROVED_ZERO_REQUIREMENTS = {
    "act_vocabulary",
    "mon_floorplan",
    "mon_cats_shape",
    "telemetry_ingest",
    "import_no_autostart",
}


def test_task_suite_matches_approved_requirements():
    suite = load_task_suite("cat-cafe-monitoring")
    assert suite is not None, "tasks.yaml missing for cat-cafe-monitoring"
    suite_map = {t.id: t.error_class for t in suite.tasks}
    assert suite_map == APPROVED_PRESENT_REQUIREMENTS

    # The 5 requirements whose present count is 0 are not yet in the file (T013)
    for zero_id in APPROVED_ZERO_REQUIREMENTS:
        assert zero_id not in suite_map, f"{zero_id} unexpectedly in tasks.yaml"


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

    # Every test function in oracle/ is in exactly one requirement
    assert len(all_mapped_tests) == len(set(all_mapped_tests)), "Duplicate mapped test found"
    assert set(all_mapped_tests) == discovered_tests
    assert len(discovered_tests) == 12


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
    assert ref_res.tests_passed == 12
    assert ref_res.tests_total == 12

    floor_res = run_floor_check(CASE_DIR)
    assert floor_res.passed is True
    assert floor_res.tests_passed == 0
    assert floor_res.tests_passed < ref_res.tests_passed
