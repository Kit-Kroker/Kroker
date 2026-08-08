"""Baseline practice over the tracked tree at a pinned commit."""
import subprocess

import pytest

from sdlc.measurement import CollectionState
from sdlc.toolchain.adapters import PythonToolchain
from sdlc.triage.activities import (
    TriageSignalInput, read_blob, tracked_paths, triage_baseline,
)
from sdlc.triage.models import (
    FixClass, M_TESTS_PRESENT,
)
from sdlc.triage.signals import baseline


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
                          check=True).stdout.strip()


def _rules(result):
    return {f.rule for f in result.findings}


# ---- pure logic -------------------------------------------------------

def test_find_test_files_matches_all_three_python_conventions():
    paths = ["test_a.py", "b_test.py", "tests/unit/test_c.py",
             "src/app.py", "docs/test_notes.md"]
    found = baseline.find_test_files(paths, PythonToolchain().test_globs)
    assert set(found) == {"test_a.py", "b_test.py", "tests/unit/test_c.py"}


def test_clean_repo_yields_no_findings():
    paths = ["pyproject.toml", "uv.lock", "README.md", "src/app.py",
             "tests/test_app.py", ".github/workflows/ci.yml", ".gitignore"]
    r = baseline.evaluate(paths, ".env\n__pycache__/\n", PythonToolchain())
    assert r.findings == []
    assert r.collected.state is CollectionState.MEASURED
    assert r.metrics[M_TESTS_PRESENT].value == 1.0


def test_vibe_repo_yields_the_expected_rule_set():
    # No toolchain resolved (no JS adapter until E-30b), so no_lockfile is
    # deliberately absent: we cannot name a lockfile for a stack we do not
    # recognize, and inventing one would be a finding we cannot justify.
    paths = ["package.json", "src/App.jsx", ".env"]
    r = baseline.evaluate(paths, "", None)
    assert _rules(r) == {"no_ci", "gitignore_missing", "no_readme",
                         "no_tests", "no_env_example"}


def test_no_lockfile_fires_only_when_a_toolchain_declares_lockfiles():
    paths = ["pyproject.toml", "README.md", "src/a.py", "tests/test_a.py",
             ".github/workflows/ci.yml", ".gitignore"]
    r = baseline.evaluate(paths, ".env\n", PythonToolchain())
    assert _rules(r) == {"no_lockfile"}


def test_gitignore_present_but_not_covering_env():
    paths = ["pyproject.toml", "uv.lock", "README.md", "src/a.py",
             "tests/test_a.py", ".github/workflows/ci.yml", ".gitignore"]
    r = baseline.evaluate(paths, "__pycache__/\n*.log\n", PythonToolchain())
    assert _rules(r) == {"gitignore_missing_env"}
    assert next(f for f in r.findings).fix_class is FixClass.MECHANICAL


def test_no_tests_is_structural_not_mechanical():
    r = baseline.evaluate(["pyproject.toml", "src/a.py"], "", PythonToolchain())
    f = next(f for f in r.findings if f.rule == "no_tests")
    assert f.fix_class is FixClass.STRUCTURAL
    assert r.metrics[M_TESTS_PRESENT].value == 0.0


def test_env_example_present_suppresses_the_finding():
    r = baseline.evaluate([".env", ".env.example", "pyproject.toml"], "",
                          PythonToolchain())
    assert "no_env_example" not in _rules(r)


@pytest.mark.parametrize("ci_path", [
    ".github/workflows/ci.yml", ".github/workflows/ci.yaml",
    ".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml",
])
def test_each_ci_convention_is_recognized(ci_path):
    r = baseline.evaluate(["pyproject.toml", ci_path], "", PythonToolchain())
    assert "no_ci" not in _rules(r)


# ---- git seam + activity ---------------------------------------------

def test_tracked_paths_excludes_untracked_and_ignored(tmp_path):
    sha = _commit_repo(tmp_path, {
        "pyproject.toml": "[project]\n", ".gitignore": ".env\n"})
    (tmp_path / ".env").write_text("SECRET=x\n", encoding="utf-8")
    (tmp_path / "scratch.py").write_text("x = 1\n", encoding="utf-8")
    paths = tracked_paths(str(tmp_path), sha)
    assert set(paths) == {"pyproject.toml", ".gitignore"}


def test_read_blob_returns_none_for_a_missing_path(tmp_path):
    sha = _commit_repo(tmp_path, {"pyproject.toml": "[project]\n"})
    assert read_blob(str(tmp_path), sha, "nope.py") is None
    assert read_blob(str(tmp_path), sha, "pyproject.toml") == "[project]\n"


@pytest.mark.asyncio
async def test_activity_reports_on_a_vibe_repo(tmp_path):
    sha = _commit_repo(tmp_path, {
        "package.json": '{"name":"app"}\n', "src/App.jsx": "export default 1\n"})
    r = await triage_baseline(
        TriageSignalInput(repo_dir=str(tmp_path), commit_sha=sha))
    assert r.signal == "baseline"
    assert r.collected.state is CollectionState.MEASURED
    assert "no_tests" in _rules(r)


@pytest.mark.asyncio
async def test_activity_reports_not_collected_on_a_bad_sha(tmp_path):
    _commit_repo(tmp_path, {"pyproject.toml": "[project]\n"})
    r = await triage_baseline(TriageSignalInput(
        repo_dir=str(tmp_path), commit_sha="0" * 40))
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.findings == []


@pytest.mark.asyncio
async def test_activity_resolves_toolchain_from_pinned_commit_not_worktree(tmp_path):
    # D6: the toolchain is resolved from the pinned commit's tracked tree,
    # never the operator's live working checkout. A clean, tested repo whose
    # checkout merely lost the marker file must still resolve Python and count
    # its tests -- resolving from the worktree would drop the toolchain,
    # fabricate a no_tests finding and force INDETERMINATE readiness.
    sha = _commit_repo(tmp_path, {
        "pyproject.toml": "[project]\n",
        "uv.lock": "",
        "README.md": "x\n",
        ".gitignore": ".env\n",
        ".github/workflows/ci.yml": "",
        "tests/test_app.py": "def test():\n    pass\n",
    })
    (tmp_path / "pyproject.toml").unlink()      # gone from the checkout, not the commit
    r = await triage_baseline(
        TriageSignalInput(repo_dir=str(tmp_path), commit_sha=sha))
    assert r.collected.state is CollectionState.MEASURED
    assert "no_tests" not in _rules(r)
    assert r.metrics[M_TESTS_PRESENT].value == 1.0
