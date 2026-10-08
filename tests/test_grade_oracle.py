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

    # 2. a held-out oracle under a temp cases root
    cases = tmp_path / "cases"
    odir = cases / "case" / "oracle"
    odir.mkdir(parents=True)
    (odir / "conftest.py").write_text(ORACLE_CONFTEST)
    (odir / "test_crud.py").write_text(ORACLE_TEST)
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
    junit report the oracle then parses. Returns (grade, shell_calls)."""
    calls: list = []

    async def fake_shell(cmd, cwd, timeout_s):
        calls.append(cmd)
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

    async def fake_shell(cmd, cwd, timeout_s):
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
