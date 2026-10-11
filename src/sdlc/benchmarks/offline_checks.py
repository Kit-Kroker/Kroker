"""Offline acceptance checks: run_reference_check and run_floor_check (Phase 4).

D-3: runs the reference solution or an empty tree against the case's oracle
using the grader's own environment functions, sandboxed in a temporary tree.
D-4: floor compares tests passed against the reference.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import shutil
import tempfile
from pathlib import Path
from typing import Literal

import yaml

from sdlc.benchmarks.acceptance import SuiteCheck
from sdlc.benchmarks.oracle import (
    TOOLCHAINS,
    _bounded_shell,
    _oracle_run_env,
    _provision_oracle_env,
    grade_from_junit,
    grade_testcases_from_junit,
)
from sdlc.toolchain.adapters import ToolchainKind


async def _run_check_async(
    case_dir: Path,
    mode: Literal["reference", "floor"],
    timeout_s: int = 600,
) -> SuiteCheck:
    case_path = Path(case_dir)
    oracle_dir = case_path / "oracle"
    if not oracle_dir.is_dir():
        return SuiteCheck(passed=None, tests_passed=0, tests_total=0, detail="no oracle/ dir")

    ref_dir = case_path / "reference"
    if mode == "reference" and not ref_dir.is_dir():
        return SuiteCheck(passed=None, tests_passed=0, tests_total=0, detail="no reference/")

    lang = "python"
    case_yaml = case_path / "case.yaml"
    if case_yaml.is_file():
        raw = yaml.safe_load(case_yaml.read_text(encoding="utf-8")) or {}
        lang = raw.get("language", "python")

    try:
        adapter = TOOLCHAINS[ToolchainKind(lang)]
    except (ValueError, KeyError):
        return SuiteCheck(
            passed=False,
            tests_passed=0,
            tests_total=0,
            detail=f"no toolchain adapter for {lang!r}",
        )

    with tempfile.TemporaryDirectory(prefix="offline-check-") as td:
        wt = Path(td)
        if mode == "reference":
            shutil.copytree(ref_dir, wt, dirs_exist_ok=True)
            ref_env_req = case_path / "reference_env" / "requirements.txt"
            if ref_env_req.is_file() and not (wt / "requirements.txt").is_file():
                shutil.copy(ref_env_req, wt / "requirements.txt")
        elif mode == "floor":
            # Floor check runs against an empty tree; nothing to copy to wt
            pass

        prov_env, prov_err = await _provision_oracle_env(str(wt), str(oracle_dir), timeout_s)
        if prov_env is None:
            return SuiteCheck(
                passed=False,
                tests_passed=0,
                tests_total=0,
                detail=f"oracle environment failed: {prov_err}",
            )
        run_env = _oracle_run_env(prov_env)

        shutil.copytree(oracle_dir, wt / "oracle")
        report_path = wt / "oracle-report.xml"
        cmd = adapter.oracle_test_cmd("oracle", str(report_path))
        await _bounded_shell(cmd, str(wt), timeout_s, env=run_env)

        try:
            xml_text = report_path.read_text(encoding="utf-8")
        except OSError:
            xml_text = ""
        score, passed, total, detail = grade_from_junit(xml_text)
        if xml_text and passed < total:
            try:
                tc = grade_testcases_from_junit(xml_text)
                failing = [k for k, ok in tc.items() if not ok]
                if failing:
                    detail = f"{passed}/{total} oracle tests passed; failed: {', '.join(failing)}"
            except Exception:
                pass

        passed_val: bool | None = None
        if mode == "reference":
            passed_val = total > 0 and passed == total
        elif mode == "floor":
            passed_val = True

        return SuiteCheck(
            passed=passed_val,
            tests_passed=passed,
            tests_total=total,
            detail=detail,
        )


def _run_sync(coro) -> SuiteCheck:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as ex:
            return ex.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def run_reference_check(case_dir: Path | str, timeout_s: int = 600) -> SuiteCheck:
    """Runs the reference solution against the case's oracle."""
    return _run_sync(_run_check_async(Path(case_dir), "reference", timeout_s))


def run_floor_check(case_dir: Path | str, timeout_s: int = 600) -> SuiteCheck:
    """Runs the oracle against an empty tree and records tests passed."""
    return _run_sync(_run_check_async(Path(case_dir), "floor", timeout_s))
