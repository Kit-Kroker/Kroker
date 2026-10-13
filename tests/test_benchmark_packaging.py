"""Packaging guards for runtime assets the worker resolves through the
installed package (not the repo checkout).

D-C: the pinned verbosity ruleset (rules/verbosity/*.yml) did not ship in
the worker image -- rules/ had no __init__.py, so setuptools' package find
never saw it and the live axis measurement read "empty rule set" on both
R0 runs. D-B's dockerignore half lives here too: the nested **/ patterns
are what keep host bytecode out of COPY benchmarks.
"""

from __future__ import annotations

from pathlib import Path, PurePath

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_verbosity_rules_ship_as_package_data():
    """The wheel's file list comes from setuptools' package find: a data
    dir without __init__.py never enters the wheel, and the worker image
    (uv sync --no-editable) installs the wheel -- that is how both R0 runs
    measured the axis with an "empty rule set" (D-C)."""
    import sdlc.benchmarks as bm

    rules = Path(bm.__file__).resolve().parent / "rules"
    assert (rules / "__init__.py").is_file(), "rules/ is not a package (missing __init__.py)"
    assert (rules / "verbosity" / "__init__.py").is_file(), (
        "rules/verbosity/ is not a package (missing __init__.py)"
    )
    yamls = [p.name for p in (rules / "verbosity").iterdir()]
    assert [n for n in yamls if n.endswith(".yml")], "ruleset .yml files vanished"


def test_package_data_patterns_cover_the_ruleset_extension():
    """The ruleset files are .yml, the historic package-data pattern only
    said **/*.yaml -- the wheel shipped the empty package and the worker
    measured with an empty rule set (D-C's second half; axis.py's own
    comment warned about it). The patterns must actually match a ruleset
    path, which is what the wheel build applies."""
    import tomllib

    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = data["tool"]["setuptools"]["package-data"]["sdlc"]
    sample = "sdlc/benchmarks/rules/verbosity/bare-except.yml"
    assert any(PurePath(sample).full_match(p) for p in patterns), (
        f"no package-data pattern matches {sample}: {patterns}"
    )


def test_dockerignore_blocks_nested_bytecode():
    """D-B: dockerignore patterns are root-anchored; without the **/ forms
    the worker image bakes host-compiled __pycache__ under
    benchmarks/cases/*/oracle/."""
    text = (_REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "**/__pycache__/" in text
    assert "**/*.pyc" in text
