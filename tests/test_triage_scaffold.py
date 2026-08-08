"""FR-902 generator scaffolding and dead code (E-41b), and the new owner of
structure_discernible (spec D12)."""
from sdlc.measurement import CollectionState
from sdlc.toolchain.adapters import PythonToolchain
from sdlc.triage.models import (
    FixClass, M_STRUCTURE, SignalResult, compute_readiness,
)
from sdlc.triage.signals import baseline, scaffold

CRA_APP = ("function App() {\n"
           "  return <p>Edit <code>src/App.js</code> and save to reload.</p>;\n"
           "}\n")
NEXT_README = ("# app\n\nThis is a [Next.js](https://nextjs.org) project "
               "bootstrapped with [`create-next-app`](https://x).\n")
DJANGO_MANAGE = ('"""Django\'s command-line utility for administrative '
                 'tasks."""\nimport os\n')


def _rules(result):
    return {f.rule for f in result.findings}


# ---- fingerprints -----------------------------------------------------

def test_fingerprints_match_known_generator_output():
    got = scaffold.scaffolded_paths({
        "src/App.js": CRA_APP,
        "README.md": NEXT_README,
        "manage.py": DJANGO_MANAGE,
    })
    assert got == {"src/App.js": "create-react-app",
                   "README.md": "create-next-app",
                   "manage.py": "django-admin"}


def test_a_hand_edited_file_is_not_scaffolding():
    edited = "function App() {\n  return <p>My real app</p>;\n}\n"
    assert scaffold.scaffolded_paths({"src/App.js": edited}) == {}


def test_a_matching_path_with_no_marker_is_not_scaffolding():
    assert scaffold.scaffolded_paths({"README.md": "# My project\n"}) == {}


def test_django_settings_fingerprint_does_not_overlap_misconfig():
    # The scaffold fingerprint uses Django's comment marker, not the
    # SECRET_KEY line, so the same file does not yield two findings from two
    # signals (scaffold + misconfig) on one line.
    settings = ('# SECURITY WARNING: keep the secret key used in production secret!\n'
                "SECRET_KEY = 'django-insecure-abc123'\n")
    assert scaffold.scaffolded_paths({"myapp/settings.py": settings}) == \
        {"myapp/settings.py": "django-admin"}


# ---- history corroboration (D13) --------------------------------------

def test_history_escalates_an_untouched_scaffold_file():
    touched = scaffold.evaluate(
        ["src/App.js"], {"src/App.js": CRA_APP}, {"src/App.js": 4}, None)
    untouched = scaffold.evaluate(
        ["src/App.js"], {"src/App.js": CRA_APP}, {"src/App.js": 1}, None)
    assert touched.findings[0].severity == "low"
    assert untouched.findings[0].severity == "medium"
    assert "untouched since import" in untouched.findings[0].detail


def test_no_history_leaves_severity_at_the_fingerprint_level():
    r = scaffold.evaluate(["src/App.js"], {"src/App.js": CRA_APP}, None, None)
    assert r.findings[0].severity == "low"
    assert r.metrics[scaffold.M_HISTORY_BASIS].state \
        is CollectionState.NOT_COLLECTED
    # The SIGNAL still collected -- the fingerprints ran.
    assert r.collected.state is CollectionState.MEASURED


def test_a_path_absent_from_touch_counts_does_not_escalate():
    # A path missing from touch_counts (beyond max_commits, or an unmatchable
    # quoting artifact) must NOT escalate to medium — the safe direction is
    # to stay at the fingerprint-level severity.
    r = scaffold.evaluate(
        ["src/App.js"], {"src/App.js": CRA_APP}, {"other.py": 5}, None)
    assert r.findings[0].severity == "low"


def test_scaffolding_is_judgement_not_mechanical():
    r = scaffold.evaluate(["src/App.js"], {"src/App.js": CRA_APP}, None, None)
    assert r.findings[0].fix_class is FixClass.JUDGEMENT


# ---- dead code --------------------------------------------------------

def test_an_unimported_module_is_reported_unreferenced():
    r = scaffold.evaluate(
        ["src/app.py", "src/orphan.py"],
        {"src/app.py": "import os\n", "src/orphan.py": "x = 1\n"},
        None, PythonToolchain())
    assert "unreferenced_module" in _rules(r)
    assert [f.path for f in r.findings
            if f.rule == "unreferenced_module"] == ["src/orphan.py"]


def test_entrypoint_conventions_are_never_unreferenced():
    paths = ["main.py", "__init__.py", "conftest.py", "manage.py",
             "tests/test_a.py", "__main__.py"]
    r = scaffold.evaluate(paths, {p: "x = 1\n" for p in paths}, None,
                          PythonToolchain())
    assert "unreferenced_module" not in _rules(r)


def test_an_imported_module_is_not_unreferenced():
    r = scaffold.evaluate(
        ["src/app.py", "src/helper.py"],
        {"src/app.py": "from helper import go\n", "src/helper.py": "def go():\n    pass\n"},
        None, PythonToolchain())
    assert "unreferenced_module" not in _rules(r)


# ---- M_STRUCTURE, the migrated dimension (D12) ------------------------

def test_structure_is_measured_without_a_toolchain():
    # Structure is language-agnostic: a repo with source files has structure
    # even without a resolved adapter. This was a regression from baseline v1,
    # which used a broad extension list and scored 1.0 for the same input.
    r = scaffold.evaluate(["src/a.py"], {"src/a.py": "x = 1\n"}, None, None)
    m = r.metrics[M_STRUCTURE]
    assert m.state is CollectionState.MEASURED
    assert m.value == 1.0


def test_structure_is_measured_for_a_js_only_repo_with_no_adapter():
    # The repos most FINGERPRINTS target (create-next-app, create-react-app)
    # resolve no adapter. Structure must still be assessable there.
    r = scaffold.evaluate(["src/App.jsx"], {"src/App.jsx": "export default 1\n"},
                          None, None)
    assert r.metrics[M_STRUCTURE].value == 1.0


def test_structure_is_zero_when_a_toolchain_resolves_but_no_source_exists():
    r = scaffold.evaluate(["README.md"], {"README.md": "x\n"}, None,
                          PythonToolchain())
    assert r.metrics[M_STRUCTURE].value == 0.0


def test_structure_is_one_for_real_source():
    r = scaffold.evaluate(["src/a.py"], {"src/a.py": "x = 1\n"}, None,
                          PythonToolchain())
    assert r.metrics[M_STRUCTURE].value == 1.0


def test_structure_is_zero_when_source_is_almost_all_scaffolding():
    paths = ["manage.py"]
    r = scaffold.evaluate(paths, {"manage.py": DJANGO_MANAGE}, None,
                          PythonToolchain())
    assert r.metrics[M_STRUCTURE].value == 0.0


# ---- the migration regression guard (D12) -----------------------------

def test_baseline_no_longer_reports_structure():
    r = baseline.evaluate(["pyproject.toml", "src/a.py"], "",
                          PythonToolchain())
    assert M_STRUCTURE not in r.metrics
    assert baseline.VERSION == 2


def test_two_signals_reporting_structure_still_raises():
    # The invariant the migration must not break: exactly one owner per
    # readiness key. If a future edit re-adds M_STRUCTURE to baseline, this
    # fails loudly instead of silently preferring a producer.
    import pytest
    from sdlc.measurement import Measurement
    a = SignalResult(signal="a", version=1,
                     collected=Measurement.measured(0.0),
                     metrics={M_STRUCTURE: Measurement.measured(1.0)})
    b = SignalResult(signal="b", version=1,
                     collected=Measurement.measured(0.0),
                     metrics={M_STRUCTURE: Measurement.measured(0.0)})
    with pytest.raises(ValueError, match="more than one signal"):
        compute_readiness([a, b])


# ---- activity ---------------------------------------------------------

import subprocess

import pytest

from sdlc.triage.activities import (
    TriageSignalInput, commit_touch_counts, triage_scaffold,
)


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True,
                          encoding="utf-8", check=True,
                          stdin=subprocess.DEVNULL)


def _init(root):
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "t@example.com"], root)
    _run(["git", "config", "user.name", "T"], root)


def _commit(root, files: dict[str, str], message: str) -> str:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-q", "-m", message], root)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, encoding="utf-8",
                          check=True, stdin=subprocess.DEVNULL).stdout.strip()


def test_touch_counts_is_none_for_a_single_commit_repo(tmp_path):
    _init(tmp_path)
    sha = _commit(tmp_path, {"a.py": "x = 1\n"}, "one")
    assert commit_touch_counts(str(tmp_path), sha) is None


def test_touch_counts_counts_commits_per_path(tmp_path):
    _init(tmp_path)
    _commit(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 1\n"}, "one")
    sha = _commit(tmp_path, {"a.py": "x = 2\n"}, "two")
    counts = commit_touch_counts(str(tmp_path), sha)
    assert counts["a.py"] == 2
    assert counts["b.py"] == 1


@pytest.mark.asyncio
async def test_activity_escalates_untouched_scaffolding(tmp_path):
    _init(tmp_path)
    _commit(tmp_path, {"pyproject.toml": "[project]\n",
                       "manage.py": DJANGO_MANAGE,
                       "src/app.py": "import os\n"}, "one")
    sha = _commit(tmp_path, {"src/app.py": "import os\nimport sys\n"}, "two")
    r = await triage_scaffold(TriageSignalInput(
        repo_dir=str(tmp_path), commit_sha=sha))
    assert r.collected.state is CollectionState.MEASURED
    f = next(f for f in r.findings if f.rule == "generator_scaffold")
    assert f.severity == "medium"
    assert r.metrics[scaffold.M_HISTORY_BASIS].state \
        is CollectionState.MEASURED


@pytest.mark.asyncio
async def test_activity_reports_not_collected_on_a_bad_sha(tmp_path):
    _init(tmp_path)
    _commit(tmp_path, {"a.py": "x = 1\n"}, "one")
    r = await triage_scaffold(TriageSignalInput(
        repo_dir=str(tmp_path), commit_sha="0" * 40))
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.findings == []
