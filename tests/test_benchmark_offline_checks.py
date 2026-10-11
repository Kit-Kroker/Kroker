"""Tests for benchmark offline checks: run_reference_check and run_floor_check (T006)."""

import os
import shutil
import sys
from pathlib import Path

import pytest

from sdlc.benchmarks.cli import dispatch_import_deveval
from sdlc.benchmarks.offline_checks import run_floor_check, run_reference_check
from sdlc.benchmarks.oracle import _ORACLE_ENV_ALLOW

FIXTURE_MINI_CALC = Path(__file__).resolve().parent / "fixtures" / "mini_calc"


def _build_mini_calc_case(tmp_path: Path) -> Path:
    src_root = tmp_path / "src" / "python"
    src_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE_MINI_CALC, src_root / "mini_calc")
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    dispatch_import_deveval(src=str(src_root), out=str(cases_dir))
    return cases_dir / "deveval-mini-calc"


@pytest.fixture
def stub_oracle_env(monkeypatch):
    """Stub _provision_oracle_env in offline_checks to return the current
    Python environment without building a real venv in fast tier tests."""
    captured_envs = []
    checked_roots = []

    async def _stub_prov(worktree: str, oracle_dir: str, timeout_s: int):
        wt_path = Path(worktree)
        # Capture requirements.txt presence at root of checked tree
        req_file = wt_path / "requirements.txt"
        checked_roots.append(
            {
                "worktree": worktree,
                "has_requirements": req_file.is_file(),
                "req_content": req_file.read_text(encoding="utf-8") if req_file.is_file() else None,
            }
        )
        # Base environment using current interpreter
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "VIRTUAL_ENV": sys.prefix,
        }
        return env, None

    # Intercept shell calls to inspect passed env
    from sdlc.benchmarks import offline_checks

    orig_shell = offline_checks._bounded_shell

    async def _spy_shell(cmd: str, cwd: str, timeout_s: int, env: dict[str, str] | None = None):
        if env is not None:
            captured_envs.append(dict(env))
        return await orig_shell(cmd, cwd, timeout_s, env=env)

    monkeypatch.setattr(offline_checks, "_provision_oracle_env", _stub_prov)
    monkeypatch.setattr(offline_checks, "_bounded_shell", _spy_shell)

    return {"captured_envs": captured_envs, "checked_roots": checked_roots}


def test_reference_check_passes_on_mini_calc(tmp_path: Path, stub_oracle_env):
    case_dir = _build_mini_calc_case(tmp_path)
    res = run_reference_check(case_dir)
    assert res.passed is True
    assert res.tests_passed == res.tests_total
    assert res.tests_total > 0


def test_reference_check_fails_when_reference_broken(tmp_path: Path, stub_oracle_env):
    case_dir = _build_mini_calc_case(tmp_path)
    # Break the reference solution so calc.add subtracts instead of adds
    calc_py = case_dir / "reference" / "calc.py"
    calc_py.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    res = run_reference_check(case_dir)
    assert res.passed is False
    assert "test_add" in res.detail


def test_reference_check_returns_none_when_no_reference_dir(tmp_path: Path, stub_oracle_env):
    case_dir = _build_mini_calc_case(tmp_path)
    shutil.rmtree(case_dir / "reference")

    res = run_reference_check(case_dir)
    assert res.passed is None


def test_floor_check_returns_fewer_tests_passed_than_reference(tmp_path: Path, stub_oracle_env):
    case_dir = _build_mini_calc_case(tmp_path)
    ref_res = run_reference_check(case_dir)
    floor_res = run_floor_check(case_dir)

    assert floor_res.tests_passed < ref_res.tests_passed
    assert floor_res.tests_passed == 0


def test_reference_env_requirements_copied_to_reference_root_and_absent_from_floor(
    tmp_path: Path, stub_oracle_env
):
    case_dir = _build_mini_calc_case(tmp_path)
    # Ensure reference has no requirements.txt
    ref_req = case_dir / "reference" / "requirements.txt"
    if ref_req.is_file():
        ref_req.unlink()

    # Create reference_env/requirements.txt
    ref_env_dir = case_dir / "reference_env"
    ref_env_dir.mkdir(parents=True, exist_ok=True)
    (ref_env_dir / "requirements.txt").write_text("dummy-req==1.0.0\n", encoding="utf-8")

    # Run reference check
    run_reference_check(case_dir)
    # Run floor check
    run_floor_check(case_dir)

    roots = stub_oracle_env["checked_roots"]
    assert len(roots) >= 2
    ref_root = roots[0]
    floor_root = roots[1]

    # Present at root of checked tree for reference check
    assert ref_root["has_requirements"] is True
    assert "dummy-req==1.0.0" in ref_root["req_content"]

    # Absent from root of checked tree for floor check
    assert floor_root["has_requirements"] is False


def test_neither_check_leaves_file_under_case_directory(tmp_path: Path, stub_oracle_env):
    case_dir = _build_mini_calc_case(tmp_path)
    before_files = sorted(p.relative_to(case_dir) for p in case_dir.rglob("*"))

    run_reference_check(case_dir)
    run_floor_check(case_dir)

    after_files = sorted(p.relative_to(case_dir) for p in case_dir.rglob("*"))
    assert before_files == after_files


def test_checks_drop_worker_env_outside_allowlist(tmp_path: Path, stub_oracle_env, monkeypatch):
    monkeypatch.setenv("SDLC_FORBIDDEN_WORKER_SECRET", "super-secret-token")
    monkeypatch.setenv("PYTHONPATH", "/forbidden/path")

    case_dir = _build_mini_calc_case(tmp_path)
    run_reference_check(case_dir)

    envs = stub_oracle_env["captured_envs"]
    assert envs, "expected at least one shell env captured"
    for env in envs:
        assert "SDLC_FORBIDDEN_WORKER_SECRET" not in env
        assert "PYTHONPATH" not in env
        for key in env:
            assert key in _ORACLE_ENV_ALLOW or key in ("VIRTUAL_ENV", "PYTHONNOUSERSITE")


@pytest.mark.slow
def test_real_offline_checks_on_mini_calc_case(tmp_path: Path):
    """Slow tier test running both checks for real without stubbing _provision_oracle_env."""
    case_dir = _build_mini_calc_case(tmp_path)
    ref_res = run_reference_check(case_dir)
    assert ref_res.passed is True
    assert ref_res.tests_passed == ref_res.tests_total
    assert ref_res.tests_total > 0

    floor_res = run_floor_check(case_dir)
    assert floor_res.tests_passed == 0
    assert floor_res.tests_passed < ref_res.tests_passed
