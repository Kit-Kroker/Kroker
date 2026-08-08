"""FR-902 dependency health (E-41a)."""
from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.advisories import Advisory, AdvisoryResult
from sdlc.triage.models import FixClass
from sdlc.triage.signals import dependencies as dep

PYPROJECT = """\
[project]
name = "app"
dependencies = ["requests>=2.0", "pydantic==2.9.0", "pillow"]

[project.optional-dependencies]
dev = ["pytest>=8"]
"""

REQUIREMENTS = """\
# a comment
requests==2.31.0
flask
-r other.txt
uvicorn[standard]>=0.30
"""


def _rules(result):
    return {f.rule for f in result.findings}


def _no_advisories():
    return AdvisoryResult(
        collected=Measurement.not_collected("no advisory source configured"))


# ---- manifest parsing -------------------------------------------------

def test_pyproject_parses_required_and_optional_dependencies():
    got = {d.name: d.constraint
           for d in dep.parse_pyproject("pyproject.toml", PYPROJECT)}
    assert got == {"requests": ">=2.0", "pydantic": "==2.9.0",
                   "pillow": "", "pytest": ">=8"}


def test_requirements_skips_comments_and_include_directives():
    got = {d.name: d.constraint
           for d in dep.parse_requirements("requirements.txt", REQUIREMENTS)}
    assert got == {"requests": "==2.31.0", "flask": "",
                   "uvicorn": ">=0.30"}


def test_names_are_normalized_pep503():
    text = '[project]\ndependencies = ["Python_Dateutil>=2"]\n'
    assert dep.parse_pyproject("pyproject.toml", text)[0].name \
        == "python-dateutil"


def test_poetry_dependencies_are_parsed():
    text = ('[tool.poetry.dependencies]\n'
            'python = "^3.10"\n'
            'requests = "^2.0"\n'
            'pytest = {version = ">=7.0", extras = ["test"]}\n')
    got = {d.name: d.constraint
           for d in dep.parse_pyproject("pyproject.toml", text)}
    assert "python" not in got              # version constraint, not a dep
    assert got["requests"] == "^2.0"
    assert got["pytest"] == ">=7.0"


def test_poetry_group_dependencies_are_parsed():
    text = ('[tool.poetry.group.dev.dependencies]\n'
            'ruff = "*"\n')
    got = {d.name: d.constraint
           for d in dep.parse_pyproject("pyproject.toml", text)}
    assert got["ruff"] == "*"


def test_pep621_and_poetry_deps_are_both_read():
    text = ('[project]\n'
            'dependencies = ["flask"]\n\n'
            '[tool.poetry.dependencies]\n'
            'requests = "^2.0"\n')
    names = {d.name for d in dep.parse_pyproject("pyproject.toml", text)}
    assert names == {"flask", "requests"}


# ---- rules ------------------------------------------------------------

def test_unpinned_fires_for_floating_and_absent_constraints():
    declared = dep.parse_pyproject("pyproject.toml", PYPROJECT)
    r = dep.evaluate(declared, lockfile_present=False,
                     imported={"requests", "pydantic", "PIL", "pytest"},
                     advisories=_no_advisories())
    unpinned = {f.path + ":" + f.detail.split()[0]
                for f in r.findings if f.rule == "unpinned_dependency"}
    assert len(unpinned) == 3        # requests, pillow, pytest; not pydantic


def test_unpinned_detail_records_whether_a_lockfile_mitigates():
    declared = dep.parse_pyproject("pyproject.toml",
                                   '[project]\ndependencies = ["requests"]\n')
    with_lock = dep.evaluate(declared, True, {"requests"}, _no_advisories())
    without = dep.evaluate(declared, False, {"requests"}, _no_advisories())
    assert "lockfile" in with_lock.findings[0].detail
    assert "no lockfile" in without.findings[0].detail


def test_duplicate_fires_only_on_conflicting_constraints():
    same = [dep.Declared(name="requests", raw="requests==2.0",
                         manifest="pyproject.toml", constraint="==2.0"),
            dep.Declared(name="requests", raw="requests==2.0",
                         manifest="requirements.txt", constraint="==2.0")]
    conflicting = [same[0],
                   dep.Declared(name="requests", raw="requests==3.0",
                                manifest="requirements.txt",
                                constraint="==3.0")]
    assert "duplicate_dependency" not in _rules(
        dep.evaluate(same, True, {"requests"}, _no_advisories()))
    assert "duplicate_dependency" in _rules(
        dep.evaluate(conflicting, True, {"requests"}, _no_advisories()))


def test_known_vulnerable_is_judgement_not_mechanical():
    declared = [dep.Declared(name="requests", raw="requests==2.0",
                             manifest="requirements.txt", constraint="==2.0")]
    adv = AdvisoryResult(
        collected=Measurement.measured(1.0),
        advisories=[Advisory(package="requests", advisory_id="GHSA-1",
                             severity="critical", summary="bad")])
    r = dep.evaluate(declared, True, {"requests"}, adv)
    f = next(f for f in r.findings if f.rule == "known_vulnerable")
    assert f.fix_class is FixClass.JUDGEMENT
    assert f.severity == "critical"
    assert "GHSA-1" in f.detail


def test_known_vulnerable_metric_is_not_collected_under_the_default_source():
    r = dep.evaluate([], True, set(), _no_advisories())
    assert r.metrics["known_vulnerable"].state is CollectionState.NOT_COLLECTED
    # The SIGNAL still collected -- it read the manifests.
    assert r.collected.state is CollectionState.MEASURED


# ---- the unused-dependency false-positive guards ----------------------

def test_an_aliased_distribution_is_not_reported_unused():
    declared = [dep.Declared(name="pillow", raw="pillow", manifest="m",
                             constraint="")]
    r = dep.evaluate(declared, True, {"PIL"}, _no_advisories())
    assert "unused_dependency" not in _rules(r)


def test_tooling_is_never_reported_unused():
    declared = [dep.Declared(name=n, raw=n, manifest="m", constraint="")
                for n in ("pytest", "ruff", "pytest-asyncio", "types-requests")]
    r = dep.evaluate(declared, True, set(), _no_advisories())
    assert "unused_dependency" not in _rules(r)


def test_a_genuinely_unimported_dependency_is_reported_low():
    declared = [dep.Declared(name="tensorflow", raw="tensorflow",
                             manifest="m", constraint="")]
    r = dep.evaluate(declared, True, {"os"}, _no_advisories())
    f = next(f for f in r.findings if f.rule == "unused_dependency")
    assert f.severity == "low"
    assert f.fix_class is FixClass.MECHANICAL


def test_underscore_and_dash_forms_both_count_as_imported():
    declared = [dep.Declared(name="typing-extensions", raw="typing-extensions",
                             manifest="m", constraint="")]
    r = dep.evaluate(declared, True, {"typing_extensions"}, _no_advisories())
    assert "unused_dependency" not in _rules(r)


# ---- import extraction ------------------------------------------------

def test_imported_modules_reads_both_import_forms():
    src = ("import os, sys\n"
           "from pathlib import Path\n"
           "from sdlc.triage import models\n"
           "    import json\n")
    result = dep.imported_modules([src])
    # All path segments AND from-import names are captured, not just roots:
    # "from sdlc.triage import models" yields sdlc, triage, AND models.
    assert result == {"os", "sys", "pathlib", "Path", "sdlc", "triage",
                      "models", "json"}


def test_imported_modules_captures_aliased_and_dotted_names():
    src = ("import numpy as np\n"
           "from sdlc.signals import dependencies as dep\n"
           "from .helpers import util\n")
    result = dep.imported_modules([src])
    assert "numpy" in result
    assert "sdlc" in result and "signals" in result
    assert "dependencies" in result     # from-import name, not just path
    assert "helpers" in result          # relative import segment
    assert "util" in result             # from-import name from relative


def test_direct_dependencies_metric_counts_distinct_names():
    declared = dep.parse_pyproject("pyproject.toml", PYPROJECT)
    r = dep.evaluate(declared, True, set(), _no_advisories())
    assert r.metrics["direct_dependencies"].value == 4.0


# ---- activity ---------------------------------------------------------

import subprocess

import pytest

from sdlc.triage.activities import TriageDependencyInput, triage_dependencies


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True,
                          encoding="utf-8", check=True,
                          stdin=subprocess.DEVNULL)


def _commit_repo(root, files: dict[str, str]) -> str:
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "t@example.com"], root)
    _run(["git", "config", "user.name", "T"], root)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-q", "-m", "one"], root)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, encoding="utf-8",
                          check=True, stdin=subprocess.DEVNULL).stdout.strip()


@pytest.mark.asyncio
async def test_activity_reads_manifests_at_the_pinned_commit(tmp_path):
    sha = _commit_repo(tmp_path, {
        "pyproject.toml": PYPROJECT,
        "src/app.py": "import requests\nimport pydantic\nfrom PIL import Image\n",
    })
    r = await triage_dependencies(TriageDependencyInput(
        repo_dir=str(tmp_path), commit_sha=sha))
    assert r.signal == "dependencies"
    assert r.collected.state is CollectionState.MEASURED
    assert "unpinned_dependency" in _rules(r)
    # pillow is imported as PIL, and pytest is tooling.
    assert "unused_dependency" not in _rules(r)
    assert r.metrics["known_vulnerable"].state is CollectionState.NOT_COLLECTED


@pytest.mark.asyncio
async def test_activity_reports_not_collected_on_a_bad_sha(tmp_path):
    _commit_repo(tmp_path, {"pyproject.toml": PYPROJECT})
    r = await triage_dependencies(TriageDependencyInput(
        repo_dir=str(tmp_path), commit_sha="0" * 40))
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.findings == []


@pytest.mark.asyncio
async def test_activity_reports_not_collected_when_no_adapter_resolves(tmp_path):
    # No recognized marker → no manifests identifiable → not_collected, not
    # a silent MEASURED 0.0 for direct_dependencies.
    sha = _commit_repo(tmp_path, {"package.json": '{"name": "app"}\n'})
    r = await triage_dependencies(TriageDependencyInput(
        repo_dir=str(tmp_path), commit_sha=sha))
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.findings == []
