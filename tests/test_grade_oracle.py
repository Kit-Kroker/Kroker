"""grade_oracle end-to-end: a hidden suite grades produced code through the
adapter (E-31). This is the proof the increment exists to deliver."""

import subprocess
import textwrap

import pytest

from sdlc.benchmarks.oracle import OracleInput, grade_oracle

# A pure-stdlib ASGI app: importable with zero extra deps, drivable by
# httpx.ASGITransport. Returns 200 for any GET -- enough for a 1-pass/1-fail
# oracle.
FIXTURE_APP = textwrap.dedent("""
    async def app(scope, receive, send):
        assert scope["type"] == "http"
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"ok"})
""")

ORACLE_CONFTEST = textwrap.dedent("""
    import os, sys
    import httpx, pytest_asyncio
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    @pytest_asyncio.fixture
    async def client():
        import app as m
        transport = httpx.ASGITransport(app=m.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as c:
            yield c
""")

ORACLE_TEST = textwrap.dedent("""
    import pytest

    @pytest.mark.asyncio
    async def test_ok(client):
        r = await client.get("/")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_fail(client):
        r = await client.get("/")
        assert r.status_code == 404   # deliberately wrong -> one failure
""")


def _git(args, cwd):
    subprocess.run(
        ["git", "-c", "safe.directory=*", *args], cwd=cwd, check=True, capture_output=True
    )


@pytest.mark.asyncio
@pytest.mark.slow
async def test_grade_oracle_grades_produced_code(tmp_path):
    # 1. a repo with a main commit, then produced code on the integration branch
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    run_id = "bench-x/case#opencode#m"
    branch = f"sdlc/{run_id}/integration"
    _git(["checkout", "-b", branch], repo)
    (repo / "app.py").write_text(FIXTURE_APP)
    _git(["add", "."], repo)
    _git(["commit", "-m", "produced"], repo)
    _git(["checkout", "main"], repo)

    # 2. a held-out oracle under a temp cases root. 012 T016: the case now
    # DECLARES its oracle's test dependencies — under base this fixture
    # silently imported httpx/pytest-asyncio from the worker's environment,
    # the exact leak T016 closes.
    cases = tmp_path / "cases"
    odir = cases / "case" / "oracle"
    odir.mkdir(parents=True)
    (odir / "conftest.py").write_text(ORACLE_CONFTEST)
    (odir / "test_crud.py").write_text(ORACLE_TEST)
    (odir / "requirements.txt").write_text("httpx\npytest\npytest-asyncio\n")
    monkeypatch_env = {"SDLC_CASES_ROOT": str(cases)}

    import os

    old = os.environ.get("SDLC_CASES_ROOT")
    os.environ.update(monkeypatch_env)
    try:
        grade = await grade_oracle(
            OracleInput(
                case_id="case",
                repo_url=str(repo),
                run_id=run_id,
                language="python",
                base_branch="main",
            )
        )
    finally:
        if old is None:
            os.environ.pop("SDLC_CASES_ROOT", None)
        else:
            os.environ["SDLC_CASES_ROOT"] = old

    assert grade.total == 2
    assert grade.passed == 1
    assert grade.score == 0.5
    assert grade.held_out_ok is True
    assert grade.language_match is True
    assert grade.language_detected == "python"
    # throwaway worktree cleaned up: only the original repo worktree remains
    wt = subprocess.run(
        ["git", "worktree", "list"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert "oracle-" not in wt


@pytest.mark.asyncio
async def test_grade_oracle_missing_branch_returns_none(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "f").write_text("x")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    cases = tmp_path / "cases"
    (cases / "case" / "oracle").mkdir(parents=True)
    (cases / "case" / "oracle" / "test_x.py").write_text("def test_x():\n    assert True\n")

    import os

    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(
            OracleInput(
                case_id="case", repo_url=str(repo), run_id="never/ran#h#m", language="python"
            )
        )
    finally:
        os.environ.pop("SDLC_CASES_ROOT", None)
    assert grade.score is None
    assert "no produced code" in grade.detail


@pytest.mark.asyncio
async def test_grade_oracle_unknown_language_returns_none(tmp_path):
    cases = tmp_path / "cases"
    (cases / "case" / "oracle").mkdir(parents=True)
    import os

    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(
            OracleInput(case_id="case", repo_url=str(tmp_path), run_id="r#h#m", language="cobol")
        )
    finally:
        os.environ.pop("SDLC_CASES_ROOT", None)
    assert grade.score is None
    assert "no toolchain adapter" in grade.detail


from sdlc.benchmarks import judge as judge_mod


@pytest.mark.asyncio
async def test_grade_oracle_populates_oracle_mapped_task_grades(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    run_id = "bench-x/case#opencode#m"
    branch = f"sdlc/{run_id}/integration"
    _git(["checkout", "-b", branch], repo)
    (repo / "app.py").write_text(FIXTURE_APP)
    _git(["add", "."], repo)
    _git(["commit", "-m", "produced"], repo)
    _git(["checkout", "main"], repo)

    cases = tmp_path / "cases"
    odir = cases / "case" / "oracle"
    odir.mkdir(parents=True)
    (odir / "conftest.py").write_text(ORACLE_CONFTEST)
    (odir / "test_crud.py").write_text(ORACLE_TEST)
    (cases / "case" / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: t01\n"
        "    error_class: functional\n"
        '    oracle_tests: ["test_crud.py::test_ok"]\n'
        "  - id: t02\n"
        "    error_class: functional\n"
        '    oracle_tests: ["test_crud.py::test_fail"]\n',
        encoding="utf-8",
    )

    import os

    old = os.environ.get("SDLC_CASES_ROOT")
    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(
            OracleInput(
                case_id="case",
                repo_url=str(repo),
                run_id=run_id,
                language="python",
                base_branch="main",
            )
        )
    finally:
        if old is None:
            os.environ.pop("SDLC_CASES_ROOT", None)
        else:
            os.environ["SDLC_CASES_ROOT"] = old

    by_id = {g.task_id: g for g in grade.task_grades}
    assert by_id["t01"].score == 1.0 and by_id["t01"].judge == "oracle"
    assert by_id["t02"].score == 0.0 and by_id["t02"].judge == "oracle"


@pytest.mark.asyncio
async def test_grade_oracle_populates_rubric_mapped_task_grades(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    run_id = "bench-x/case#opencode#m"
    branch = f"sdlc/{run_id}/integration"
    _git(["checkout", "-b", branch], repo)
    (repo / "app.py").write_text(FIXTURE_APP)
    _git(["add", "."], repo)
    _git(["commit", "-m", "produced"], repo)
    _git(["checkout", "main"], repo)

    cases = tmp_path / "cases"
    odir = cases / "case" / "oracle"
    odir.mkdir(parents=True)
    (odir / "conftest.py").write_text(ORACLE_CONFTEST)
    (odir / "test_crud.py").write_text(ORACLE_TEST)
    (cases / "case" / "tasks.yaml").write_text(
        'tasks:\n  - id: t01\n    error_class: security\n    rubric: "Uses a secure default."\n',
        encoding="utf-8",
    )

    judge_mod._set_judge_fn(lambda inp: '{"score": 0.75, "components": {}}')

    import os

    old = os.environ.get("SDLC_CASES_ROOT")
    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(
            OracleInput(
                case_id="case",
                repo_url=str(repo),
                run_id=run_id,
                language="python",
                base_branch="main",
                author_model="anthropic:claude-sonnet-4-6",
                judge_model="openai/gpt-5.2",
            )
        )
    finally:
        if old is None:
            os.environ.pop("SDLC_CASES_ROOT", None)
        else:
            os.environ["SDLC_CASES_ROOT"] = old
        judge_mod._set_judge_fn(None)

    assert len(grade.task_grades) == 1
    assert grade.task_grades[0].score == 0.75
    assert grade.task_grades[0].judge == "llm_judge"


@pytest.mark.asyncio
async def test_grade_oracle_no_tasks_yaml_gives_empty_task_grades(tmp_path):
    # test_grade_oracle_missing_branch_returns_none's fixture has no
    # tasks.yaml at all -- task_grades must default to [], never raise.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "f").write_text("x")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    cases = tmp_path / "cases"
    (cases / "case" / "oracle").mkdir(parents=True)
    (cases / "case" / "oracle" / "test_x.py").write_text("def test_x():\n    assert True\n")

    import os

    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(
            OracleInput(
                case_id="case", repo_url=str(repo), run_id="never/ran#h#m", language="python"
            )
        )
    finally:
        os.environ.pop("SDLC_CASES_ROOT", None)
    assert grade.task_grades == []


@pytest.mark.asyncio
async def test_grade_oracle_malformed_tasks_yaml_never_fails_case_grade(tmp_path):
    # A malformed tasks.yaml raises inside load_task_suite; grade_oracle's
    # try/except must swallow it and still return the case-level grade.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)

    run_id = "bench-x/case#opencode#m"
    branch = f"sdlc/{run_id}/integration"
    _git(["checkout", "-b", branch], repo)
    (repo / "app.py").write_text(FIXTURE_APP)
    _git(["add", "."], repo)
    _git(["commit", "-m", "produced"], repo)
    _git(["checkout", "main"], repo)

    cases = tmp_path / "cases"
    odir = cases / "case" / "oracle"
    odir.mkdir(parents=True)
    (odir / "conftest.py").write_text(ORACLE_CONFTEST)
    (odir / "test_crud.py").write_text(ORACLE_TEST)
    # malformed: unknown error_class
    (cases / "case" / "tasks.yaml").write_text(
        'tasks:\n  - id: t01\n    error_class: bogus\n    oracle_tests: ["x::y"]\n',
        encoding="utf-8",
    )

    import os

    old = os.environ.get("SDLC_CASES_ROOT")
    os.environ["SDLC_CASES_ROOT"] = str(cases)
    try:
        grade = await grade_oracle(
            OracleInput(
                case_id="case",
                repo_url=str(repo),
                run_id=run_id,
                language="python",
                base_branch="main",
            )
        )
    finally:
        if old is None:
            os.environ.pop("SDLC_CASES_ROOT", None)
        else:
            os.environ["SDLC_CASES_ROOT"] = old

    # case-level grade unaffected; task grading just contributed nothing
    assert grade.total == 2
    assert grade.task_grades == []


# --- 012 T015 (RED): the empty-diff guard (contract §4.5, data-model §1.6) ---
# Fast tier: _bounded_shell is stubbed to record its calls and drop a junit
# report into the worktree, so no real test run ever happens.

from pathlib import Path

import sdlc.benchmarks.oracle as oracle_mod

_PASS_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuite tests="2" failures="1">
  <testcase classname="oracle.test_x" name="test_ok"/>
  <testcase classname="oracle.test_x" name="test_bad"><failure message="boom"/></testcase>
</testsuite>
"""


def _fast_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    (repo / "base.txt").write_text("v1\n")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)
    return repo


def _integration_branch(repo, run_id, files):
    """Create sdlc/<run_id>/integration. With files=None the branch is cut at
    the base commit and nothing is committed -- an empty diff vs base."""
    branch = f"sdlc/{run_id}/integration"
    _git(["checkout", "-b", branch], repo)
    for name, content in (files or {}).items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        _git(["add", "."], repo)
    if files:
        _git(["commit", "-m", "produced"], repo)
    _git(["checkout", "main"], repo)
    return branch


async def _grade_with_stub(monkeypatch, tmp_path, repo, run_id, junit=_PASS_JUNIT):
    """grade_oracle with a recorded _bounded_shell stub: the stub writes the
    junit report the oracle then parses. Returns (grade, shell_calls); each
    call is recorded as (cmd, env) — the env kwarg the oracle hands the
    shell (None today, the filtered environment after 012 T016)."""
    calls: list = []

    async def fake_shell(cmd, cwd, timeout_s, env=None):
        calls.append((cmd, env))
        Path(cwd, "oracle-report.xml").write_text(junit, encoding="utf-8")

    monkeypatch.setattr(oracle_mod, "_bounded_shell", fake_shell)
    cases = tmp_path / f"cases-{run_id.replace('/', '_').replace('#', '_')}"
    (cases / "case" / "oracle").mkdir(parents=True)
    (cases / "case" / "oracle" / "test_x.py").write_text("def test_x():\n    assert True\n")
    monkeypatch.setenv("SDLC_CASES_ROOT", str(cases))
    grade = await grade_oracle(
        OracleInput(
            case_id="case", repo_url=str(repo), run_id=run_id, language="python", base_branch="main"
        )
    )
    return grade, calls


@pytest.mark.asyncio
async def test_empty_diff_vs_base_scores_zero_without_running_the_suite(monkeypatch, tmp_path):
    """contract §4.5: an integration branch with NO change against the base
    returns the zero grade -- score 0.0, passed 0, changed_files 0, detail
    exactly 'empty diff vs base' -- and the test command never runs."""
    repo = _fast_repo(tmp_path)
    run_id = "bench-x/case#opencode#m"
    _integration_branch(repo, run_id, files=None)
    grade, calls = await _grade_with_stub(monkeypatch, tmp_path, repo, run_id)
    assert grade.score == 0.0
    assert grade.passed == 0
    assert grade.changed_files == 0
    assert grade.detail == "empty diff vs base"
    assert calls == [], "the test command must never run on an empty diff"


@pytest.mark.asyncio
async def test_changed_files_counts_the_diff_against_base(monkeypatch, tmp_path):
    """data-model §1.6: the grade carries the number of files changed
    against the base branch; the grade itself follows the stubbed junit."""
    repo = _fast_repo(tmp_path)
    run_id = "bench-y/case#opencode#m"
    _integration_branch(
        repo,
        run_id,
        files={
            "base.txt": "v2\n",  # modified
            "added.py": "x = 1\n",  # added
            "pkg/second.py": "y = 2\n",  # added in a subdir
        },
    )
    grade, calls = await _grade_with_stub(monkeypatch, tmp_path, repo, run_id)
    assert grade.changed_files == 3
    assert grade.passed == 1 and grade.total == 2 and grade.score == 0.5
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_passing_grade_then_empty_branch_in_one_process_scores_zero(monkeypatch, tmp_path):
    """SC-005, fast: grade a passing branch, then an empty branch of the
    SAME repository, in one process. The second is 0 passed with the
    empty-diff detail, and the stubbed suite ran only for the first."""
    repo = _fast_repo(tmp_path)
    run_a = "bench-z/case#opencode#m"
    _integration_branch(repo, run_a, files={"app.py": "x = 1\n"})

    first_calls: list = []

    async def fake_shell(cmd, cwd, timeout_s, env=None):  # 012 T016: env kwarg
        first_calls.append(cmd)
        Path(cwd, "oracle-report.xml").write_text(_PASS_JUNIT, encoding="utf-8")

    monkeypatch.setattr(oracle_mod, "_bounded_shell", fake_shell)
    cases = tmp_path / "cases"
    (cases / "case" / "oracle").mkdir(parents=True)
    (cases / "case" / "oracle" / "test_x.py").write_text("def test_x():\n    assert True\n")
    monkeypatch.setenv("SDLC_CASES_ROOT", str(cases))

    first = await grade_oracle(
        OracleInput(
            case_id="case", repo_url=str(repo), run_id=run_a, language="python", base_branch="main"
        )
    )
    assert first.passed > 0
    assert len(first_calls) == 1

    run_b = "bench-z/empty#opencode#m"
    _integration_branch(repo, run_b, files=None)
    second = await grade_oracle(
        OracleInput(
            case_id="case", repo_url=str(repo), run_id=run_b, language="python", base_branch="main"
        )
    )
    assert second.passed == 0
    assert second.score == 0.0
    assert second.changed_files == 0
    assert second.detail == "empty diff vs base"
    assert len(first_calls) == 1, "the empty branch must not run the suite"


# --- 012 T016a (RED): the per-grade environment (contract §4.2-4.4) ----------
# Fast tier. Every test in this file runs against the provisioner seam via
# the autouse stub below; the REAL provisioner (_provision_oracle_env's
# venv build, installs, cleanup) is exercised by the slow tests added
# separately. raising=False: the seam does not exist yet, and existing
# tests make no _provision call, so they pass unchanged today.

import os

from sdlc.toolchain.adapters import TOOLCHAINS, ToolchainKind


@pytest.fixture(autouse=True)
def _stub_provision_oracle_env(monkeypatch, request):
    # Slow-marked tests exercise the REAL _provision_oracle_env (real venv,
    # real pip) — the stub would blind them to the seam.
    if request.node.get_closest_marker("slow") is not None:
        return

    async def _current_env(worktree, oracle_dir, timeout_s):
        return os.environ.copy(), None

    monkeypatch.setattr(oracle_mod, "_provision_oracle_env", _current_env, raising=False)


def _venv_env(tmp_path):
    """A worker-shaped environment: a fake venv first on PATH, plus vars
    that must NOT survive the filter (contract §4.2)."""
    venv = tmp_path / "venv"
    venv_bin = str(venv / "bin")
    return (
        str(venv),
        venv_bin,
        {
            "PATH": venv_bin + os.pathsep + "/usr/bin",
            "VIRTUAL_ENV": str(venv),
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": "/somewhere",
            "PYTHONHOME": "/elsewhere",
            "KROKER_SECRET": "1",
        },
    )


@pytest.mark.asyncio
async def test_test_command_receives_only_the_filtered_environment(monkeypatch, tmp_path):
    """contract §4.2: the environment handed to the test command contains
    only the allowlisted names plus PATH (venv bin dir first), VIRTUAL_ENV
    and PYTHONNOUSERSITE=1 — PYTHONPATH and PYTHONHOME absent even though
    the worker env carries them, and no worker secret rides along."""
    venv, venv_bin, worker_env = _venv_env(tmp_path)

    async def provision(worktree, oracle_dir, timeout_s):
        return dict(worker_env), None

    monkeypatch.setattr(oracle_mod, "_provision_oracle_env", provision)
    repo = _fast_repo(tmp_path)
    run_id = "t016a/env#opencode#m"
    _integration_branch(repo, run_id, files={"app.py": "x = 1\n"})
    grade, calls = await _grade_with_stub(monkeypatch, tmp_path, repo, run_id)
    assert calls, "the test command must run"
    env = calls[0][1]
    from sdlc.benchmarks.oracle import _ORACLE_ENV_ALLOW

    assert set(env) <= set(_ORACLE_ENV_ALLOW) | {"PATH", "VIRTUAL_ENV", "PYTHONNOUSERSITE"}
    assert env["VIRTUAL_ENV"] == venv
    assert env["PATH"].split(os.pathsep)[0] == venv_bin
    assert env["PYTHONNOUSERSITE"] == "1"
    for banned in ("PYTHONPATH", "PYTHONHOME", "KROKER_SECRET"):
        assert banned not in env


@pytest.mark.asyncio
async def test_provisioning_failure_yields_no_score_with_the_prefix(monkeypatch, tmp_path):
    """contract §4.4: a provisioning failure returns score None with detail
    starting 'oracle environment failed:' — and the test command never
    runs."""

    async def broken(worktree, oracle_dir, timeout_s):
        return None, "pip exploded"

    monkeypatch.setattr(oracle_mod, "_provision_oracle_env", broken)
    repo = _fast_repo(tmp_path)
    run_id = "t016a/broken#opencode#m"
    _integration_branch(repo, run_id, files={"app.py": "x = 1\n"})
    grade, calls = await _grade_with_stub(monkeypatch, tmp_path, repo, run_id)
    assert grade.score is None
    assert grade.detail.startswith("oracle environment failed:")
    assert calls == []


@pytest.mark.asyncio
async def test_provision_seam_called_once_with_the_case_oracle_dir(monkeypatch, tmp_path):
    """grade_oracle consults the seam exactly once per grade, handed the
    fresh worktree, the case's oracle directory and its timeout; the test
    command itself stays the adapter's oracle_test_cmd."""
    prov_calls: list = []

    async def recording(worktree, oracle_dir, timeout_s):
        prov_calls.append((worktree, oracle_dir, timeout_s))
        return os.environ.copy(), None

    monkeypatch.setattr(oracle_mod, "_provision_oracle_env", recording)
    repo = _fast_repo(tmp_path)
    run_id = "t016a/seam#opencode#m"
    _integration_branch(repo, run_id, files={"app.py": "x = 1\n"})
    grade, calls = await _grade_with_stub(monkeypatch, tmp_path, repo, run_id)
    assert len(prov_calls) == 1
    worktree, oracle_dir, timeout_s = prov_calls[0]
    assert Path(oracle_dir).name == "oracle"
    assert Path(oracle_dir).parent.name == "case"
    assert timeout_s == 600
    cmd = calls[0][0]
    # the junit path is the real per-grade worktree path — assert the shape
    # around it rather than guessing the tempfile prefix
    prefix = (
        TOOLCHAINS[ToolchainKind.PYTHON]
        .oracle_test_cmd("oracle", "oracle-report.xml")
        .split("oracle-report.xml")[0]
    )
    assert cmd.startswith(prefix)
    assert cmd.endswith("oracle-report.xml -p no:cacheprovider -o junit_family=legacy")


@pytest.mark.asyncio
async def test_grade_detail_notes_the_isolated_environment(monkeypatch, tmp_path):
    """A graded path states the isolation in its detail."""
    repo = _fast_repo(tmp_path)
    run_id = "t016a/detail#opencode#m"
    _integration_branch(repo, run_id, files={"app.py": "x = 1\n"})
    grade, calls = await _grade_with_stub(monkeypatch, tmp_path, repo, run_id)
    assert grade.detail.endswith("; oracle env: isolated")


# --- 012 T016b (chaos seat, SLOW): the REAL provisioner (contract §4.1/4.3/4.6/4.7)
# Real venv, real pip, real produced project. 'tabulate' is verified absent
# from the worker venv (importlib.util.find_spec -> None), so the produced
# project's test can only pass if the provision installed its declared
# dependency into a per-grade environment.

_THIRD_PARTY = "tabulate"  # verified absent from /app/.venv (find_spec None)

PRODUCED_APP = (
    "from tabulate import tabulate\n\n\n"
    "def table():\n    return tabulate([['a', 1]], headers=['h'])\n"
)

_SMOKE_CONFTEST = (
    "import os, sys\n"
    "ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
    "if ROOT not in sys.path:\n"
    "    sys.path.insert(0, ROOT)\n"
)

ORACLE_SMOKE = "def test_third_party_import():\n    import app\n    assert app.table()\n"


def _produced_repo(tmp_path):
    """A repo whose base declares one tiny pure-Python third-party dep the
    worker venv does not have, so only a real provision can pass the suite."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'produced-x'\n"
        "version = '0'\n"
        f"dependencies = ['{_THIRD_PARTY}']\n"
        "[build-system]\n"
        "requires = ['setuptools']\n"
        "build-backend = 'setuptools.build_meta'\n",
        encoding="utf-8",
    )
    (repo / "base.txt").write_text("v1\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-m", "base"], repo)
    return repo


def _smoke_cases_root(tmp_path):
    cases = tmp_path / "cases"
    odir = cases / "case" / "oracle"
    odir.mkdir(parents=True)
    (odir / "conftest.py").write_text(_SMOKE_CONFTEST, encoding="utf-8")
    (odir / "test_smoke.py").write_text(ORACLE_SMOKE, encoding="utf-8")
    return cases


async def _grade(repo, run_id):
    return await grade_oracle(
        OracleInput(
            case_id="case", repo_url=str(repo), run_id=run_id, language="python", base_branch="main"
        )
    )


@pytest.mark.asyncio
@pytest.mark.slow
async def test_slow_real_env_same_counts_back_to_back(tmp_path, monkeypatch):
    """contract §4.6, real environment: grading the same passing branch
    twice in one process returns identical score/passed/total both times."""
    repo = _produced_repo(tmp_path)
    run_id = "bench-x/case#opencode#m"
    _integration_branch(repo, run_id, files={"app.py": PRODUCED_APP})
    monkeypatch.setenv("SDLC_CASES_ROOT", str(_smoke_cases_root(tmp_path)))

    first = await _grade(repo, run_id)
    second = await _grade(repo, run_id)
    assert first.passed > 0, (
        f"the declared dep must install into the per-grade environment (detail: {first.detail!r})"
    )
    assert (first.score, first.passed, first.total) == (
        second.score,
        second.passed,
        second.total,
    )


@pytest.mark.asyncio
@pytest.mark.slow
async def test_slow_real_env_no_venv_left_behind_and_no_worker_leak(tmp_path, monkeypatch):
    """contract §4.1/§4.7, real environment: after one grade returns, no
    .sdlc-venv remains anywhere under the repo's tmp tree (the grade
    worktree is torn down with its venv) and the third-party package the
    provision installed is NOT importable in the worker process."""
    import importlib.util

    repo = _produced_repo(tmp_path)
    run_id = "bench-y/case#opencode#m"
    _integration_branch(repo, run_id, files={"app.py": PRODUCED_APP})
    monkeypatch.setenv("SDLC_CASES_ROOT", str(_smoke_cases_root(tmp_path)))

    grade = await _grade(repo, run_id)
    assert grade.passed > 0, (
        f"the leak check is only meaningful after a real provision (detail: {grade.detail!r})"
    )
    leftovers = [str(p) for p in tmp_path.rglob(".sdlc-venv")]
    assert leftovers == [], f"the grade's venv survived the worktree teardown: {leftovers}"
    assert importlib.util.find_spec(_THIRD_PARTY) is None, (
        f"the provision leaked {_THIRD_PARTY} into the worker process"
    )


@pytest.mark.asyncio
@pytest.mark.slow
async def test_slow_real_env_passing_branch_then_empty_branch_scores_zero(tmp_path, monkeypatch):
    """SC-005 slow (contract §4.5 with the real environment): a passing
    branch, then the EMPTY branch of the same repo, in one process — the
    second returns the guard's zero grade before any provisioning."""
    repo = _produced_repo(tmp_path)
    run_a = "bench-z/case#opencode#m"
    _integration_branch(repo, run_a, files={"app.py": PRODUCED_APP})
    monkeypatch.setenv("SDLC_CASES_ROOT", str(_smoke_cases_root(tmp_path)))

    first = await _grade(repo, run_a)
    assert first.passed > 0, f"first branch must really pass (detail: {first.detail!r})"

    run_b = "bench-z/empty#opencode#m"
    _integration_branch(repo, run_b, files=None)
    second = await _grade(repo, run_b)
    assert second.passed == 0
    assert second.score == 0.0
    assert second.changed_files == 0
    assert second.detail == "empty diff vs base"
