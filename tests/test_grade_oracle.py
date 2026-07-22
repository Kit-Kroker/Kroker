"""grade_oracle end-to-end: a hidden suite grades produced code through the
adapter (E-31). This is the proof the increment exists to deliver."""
import subprocess
import textwrap
from pathlib import Path

import pytest

from sdlc.benchmarks.oracle import OracleInput, grade_oracle

# A pure-stdlib ASGI app: importable with zero extra deps, drivable by
# httpx.ASGITransport. Returns 200 for any GET -- enough for a 1-pass/1-fail
# oracle.
FIXTURE_APP = textwrap.dedent('''
    async def app(scope, receive, send):
        assert scope["type"] == "http"
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": b"ok"})
''')

ORACLE_CONFTEST = textwrap.dedent('''
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
''')

ORACLE_TEST = textwrap.dedent('''
    import pytest

    @pytest.mark.asyncio
    async def test_ok(client):
        r = await client.get("/")
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_fail(client):
        r = await client.get("/")
        assert r.status_code == 404   # deliberately wrong -> one failure
''')


def _git(args, cwd):
    subprocess.run(["git", "-c", "safe.directory=*", *args], cwd=cwd,
                   check=True, capture_output=True)


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
        grade = await grade_oracle(OracleInput(
            case_id="case", repo_url=str(repo), run_id=run_id,
            language="python", base_branch="main"))
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
    wt = subprocess.run(["git", "worktree", "list"], cwd=repo,
                        capture_output=True, text=True).stdout
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
        grade = await grade_oracle(OracleInput(
            case_id="case", repo_url=str(repo),
            run_id="never/ran#h#m", language="python"))
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
        grade = await grade_oracle(OracleInput(
            case_id="case", repo_url=str(tmp_path), run_id="r#h#m",
            language="cobol"))
    finally:
        os.environ.pop("SDLC_CASES_ROOT", None)
    assert grade.score is None
    assert "no toolchain adapter" in grade.detail
