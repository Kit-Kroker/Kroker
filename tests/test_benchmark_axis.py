"""Round 015: the measurement core (contract §1, data-model §3).

Expectations are the fixtures' hand-computed arithmetic, asserted
here, not derived from the tools at test time. The mass-split module
docstring carries the full hand count. The activity tests at the
bottom drive the REAL fail-safe paths against throwaway git repos.
"""

import shutil
import subprocess
from pathlib import Path

import sdlc.benchmarks.axis as axis_module
from sdlc.benchmarks.axis import (
    AXIS_EROSION_THRESHOLD,
    RULESET_VERSION,
    AxisInput,
    measure_code_axis,
    measure_files,
)

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


# --- the fail-safe activity against throwaway git repos (contract §2) ---


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path, branch_files: dict[str, str] | None) -> Path:
    """A scratch repo: a base commit on main, then (optionally) one commit
    on sdlc/r1/integration carrying branch_files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "axis@test")
    _git(repo, "config", "user.name", "axis test")
    (repo / "seed.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    if branch_files is not None:
        _git(repo, "checkout", "-b", "sdlc/r1/integration")
        for name, text in branch_files.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "produced")
        _git(repo, "checkout", "main")
    return repo


def _inp(repo: Path, **kw) -> AxisInput:
    base = dict(
        case_id="axis-case",
        repo_url=str(repo),
        run_id="r1",
        language="python",
        base_branch="main",
        code_finished=True,
    )
    base.update(kw)
    return AxisInput(**base)


def _measure(inp: AxisInput):
    # the activity is async like every other benchmark activity; the
    # unit tests drive it synchronously
    import asyncio

    return asyncio.run(measure_code_axis(inp))


_CLEAN_MODULE = '''"""Produced by the run under test."""


def twice(x):
    """Return double."""
    return x * 2
'''


def test_activity_measures_the_python_diff_at_the_branch_head(tmp_path):
    repo = _repo(tmp_path, {"mod.py": _CLEAN_MODULE, "notes.md": "docs\n"})
    bag = _measure(_inp(repo))
    assert bag.reason is None
    assert bag.erosion == 0.0  # one clean function, a real measured zero
    assert bag.files == 1  # only the *.py in the diff, never notes.md
    assert bag.head is not None and len(bag.head) == 40
    assert bag.tools["radon"] and bag.tools["ast-grep"]
    assert bag.ruleset_version == RULESET_VERSION


def test_activity_diff_without_python_files_is_not_measured(tmp_path):
    repo = _repo(tmp_path, {"notes.md": "docs\n"})
    bag = _measure(_inp(repo))
    assert bag.erosion is None
    assert bag.reason == "no python files in diff"


def test_activity_without_the_integration_branch_is_not_measured(tmp_path):
    repo = _repo(tmp_path, None)  # the branch was never created
    bag = _measure(_inp(repo))
    assert bag.erosion is None
    assert bag.reason == "integration branch absent"


def test_activity_preconditions_gate_before_any_checkout(tmp_path):
    # code not finished: reasons out even though the repo path is nonsense —
    # the checkout never runs (contract §2.3's order).
    lost = _measure(_inp(tmp_path, code_finished=False))
    assert lost.reason == "code stage did not finish"
    other = _measure(_inp(tmp_path, language="typescript"))
    assert other.reason == "language not python"
    unrecorded = _measure(_inp(tmp_path, language=None))
    assert unrecorded.reason == "language not python"  # covers not recorded


def test_activity_never_raises_on_a_broken_repo(tmp_path):
    bag = _measure(_inp(tmp_path / "does-not-exist"))
    assert bag.erosion is None
    assert bag.reason is not None
    assert bag.reason.startswith("integration branch absent") or bag.reason.startswith(
        "measurement failed:"
    )
