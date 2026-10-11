"""Round 015: the measurement core (contract §1, data-model §3).

Expectations are the fixtures' hand-computed arithmetic, asserted
here, not derived from the tools at test time. The mass-split module
docstring carries the full hand count.
"""

import shutil
from pathlib import Path

from sdlc.benchmarks.axis import AXIS_EROSION_THRESHOLD, RULESET_VERSION, measure_files

FIXTURES = Path(__file__).parent / "fixtures" / "axis"


def _py(tree: Path) -> list[Path]:
    return sorted(tree.rglob("*.py"))


def test_threshold_and_ruleset_constants():
    assert AXIS_EROSION_THRESHOLD == 10
    assert RULESET_VERSION == "1"


def test_mass_split_erosion_is_exactly_half():
    # mass_split/mod.py docstring: 6 + 24 + 30 under, 60 over, 120 total.
    bag = measure_files(_py(FIXTURES / "mass_split"))
    assert bag.erosion == 0.5
    assert bag.reason is None
    assert bag.functions_total == 4
    assert bag.functions_over == 1
    assert bag.mass_over == 60.0
    assert bag.mass_total == 120.0
    assert bag.files == 1
    assert bag.head is None  # the activity fills it, not the pure core


def test_plain_tree_measures_a_real_zero():
    bag = measure_files(_py(FIXTURES / "plain"))
    assert bag.erosion == 0.0
    assert bag.reason is None
    assert bag.functions_total == 1
    assert bag.functions_over == 0
    assert bag.mass_over == 0.0
    assert bag.verbosity == 0.0


def test_tree_without_functions_is_not_measured():
    bag = measure_files(_py(FIXTURES / "nofuncs"))
    assert bag.erosion is None
    assert bag.verbosity is None
    assert bag.reason == "no functions"
    assert bag.files == 1


def test_measure_files_is_deterministic():
    paths = _py(FIXTURES / "mass_split")
    assert measure_files(paths) == measure_files(paths)


def test_path_order_does_not_change_figures(tmp_path):
    # Same content under a name that sorts differently must measure
    # equal: files are visited in sorted order, never glob order.
    src = _py(FIXTURES / "mass_split")
    renamed = tmp_path / "zzz_renamed"
    renamed.mkdir()
    for p in src:
        shutil.copy(p, renamed / ("zzz_" + p.name))
    assert measure_files(_py(renamed)) == measure_files(src)
