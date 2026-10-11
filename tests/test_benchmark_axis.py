"""Round 015: the measurement core (contract §1, data-model §3).

Expectations are the fixtures' hand-computed arithmetic, asserted
here, not derived from the tools at test time. The mass-split module
docstring carries the full hand count.
"""

import shutil
from pathlib import Path

import sdlc.benchmarks.axis as axis_module
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


def test_slop_fixture_verbosity_is_the_hand_count():
    # slop/mod.py docstring: 9 flagged lines (one marker per rule, no
    # overlaps) over 28 non-blank lines.
    bag = measure_files(_py(FIXTURES / "slop"))
    assert bag.flagged_lines == 9
    assert bag.loc == 28
    assert bag.verbosity == 9 / 28
    assert bag.reason is None
    assert bag.ruleset_version == RULESET_VERSION


def test_plain_tree_flags_no_lines():
    bag = measure_files(_py(FIXTURES / "plain"))
    assert bag.flagged_lines == 0
    assert bag.verbosity == 0.0


def test_broken_rule_fails_the_measurement_not_the_run(tmp_path, monkeypatch):
    # A rule that cannot compile must fail the whole measurement with its
    # id in the reason -- never silently flag nothing (data-model §4).
    (tmp_path / "broken-rule.yml").write_text(
        # an unknown rule key: ast-grep refuses to compile the rule
        # (an unknown kind would match nothing and stay silent)
        "id: broken-rule\nlanguage: python\nrule:\n  kindZ: call\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(axis_module, "RULES_DIR", tmp_path)
    bag = measure_files(_py(FIXTURES / "slop"))
    assert bag.erosion is None
    assert bag.verbosity is None
    assert bag.reason == "measurement failed: rule broken-rule"
