"""Offline acceptance checks: run_reference_check and run_floor_check (Phase 4).

D-3: runs the reference solution or an empty tree against the case's oracle
using the grader's own environment functions, sandboxed in a temporary tree.
D-4: floor compares tests passed against the reference.
016 D-7: a third mode grades an arbitrary tree (``run_tree_check``) the same
way, per test -- the ablation/free-choice driver's grading primitive.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import shutil
import tempfile
from pathlib import Path
from typing import Literal, cast

import yaml

from sdlc.benchmarks.acceptance import SuiteCheck
from sdlc.benchmarks.oracle import (
    TOOLCHAINS,
    _bounded_shell,
    _oracle_run_env,
    _provision_oracle_env,
    copy_case_tree,
    grade_from_junit,
    grade_testcases_from_junit,
)
from sdlc.toolchain.adapters import ToolchainKind


class TreeCheck(SuiteCheck):
    """016 D-7 (Names "Offline checks"): a graded arbitrary tree, with the
    per-test verdict map beside the suite totals."""

    per_test: dict[str, bool] = {}


async def _run_check_async(
    case_dir: Path,
    mode: Literal["reference", "floor", "tree"],
    timeout_s: int = 600,
    tree_dir: Path | None = None,
) -> SuiteCheck:
    case_path = Path(case_dir)
    oracle_dir = case_path / "oracle"
    if not oracle_dir.is_dir():
        if mode == "tree":
            return TreeCheck(passed=None, tests_passed=0, tests_total=0, detail="no oracle/ dir")
        return SuiteCheck(passed=None, tests_passed=0, tests_total=0, detail="no oracle/ dir")

    ref_dir = case_path / "reference"
    if mode == "reference" and not ref_dir.is_dir():
        return SuiteCheck(passed=None, tests_passed=0, tests_total=0, detail="no reference/")

    if mode == "tree":
        tree_path = Path(tree_dir) if tree_dir is not None else None
        if tree_path is None or not tree_path.is_dir():
            return TreeCheck(
                passed=None,
                tests_passed=0,
                tests_total=0,
                detail=f"no tree directory: {tree_dir}",
            )

    lang = "python"
    case_yaml = case_path / "case.yaml"
    if case_yaml.is_file():
        raw = yaml.safe_load(case_yaml.read_text(encoding="utf-8")) or {}
        lang = raw.get("language", "python")

    try:
        adapter = TOOLCHAINS[ToolchainKind(lang)]
    except (ValueError, KeyError):
        detail = f"no toolchain adapter for {lang!r}"
        if mode == "tree":
            return TreeCheck(passed=False, tests_passed=0, tests_total=0, detail=detail)
        return SuiteCheck(passed=False, tests_passed=0, tests_total=0, detail=detail)

    with tempfile.TemporaryDirectory(prefix="offline-check-") as td:
        wt = Path(td)
        if mode == "reference":
            shutil.copytree(ref_dir, wt, dirs_exist_ok=True)
            ref_env_req = case_path / "reference_env" / "requirements.txt"
            if ref_env_req.is_file() and not (wt / "requirements.txt").is_file():
                shutil.copy(ref_env_req, wt / "requirements.txt")
        elif mode == "tree" and tree_path is not None:
            # D-7: the tree is the code source; the environment calls are the
            # reference path's own, unchanged (reference_env included). The
            # None case returned at the guard above.
            shutil.copytree(tree_path, wt, dirs_exist_ok=True)
            ref_env_req = case_path / "reference_env" / "requirements.txt"
            if ref_env_req.is_file() and not (wt / "requirements.txt").is_file():
                shutil.copy(ref_env_req, wt / "requirements.txt")
        elif mode == "floor":
            # Floor check runs against an empty tree; nothing to copy to wt
            pass

        prov_env, prov_err = await _provision_oracle_env(str(wt), str(oracle_dir), timeout_s)
        if prov_env is None:
            detail = f"oracle environment failed: {prov_err}"
            if mode == "tree":
                return TreeCheck(passed=False, tests_passed=0, tests_total=0, detail=detail)
            return SuiteCheck(passed=False, tests_passed=0, tests_total=0, detail=detail)
        run_env = _oracle_run_env(prov_env)

        # D-B: the oracle copy drops bytecode caches (see oracle.py) -- the
        # offline reference/floor checks task-grade from the same junit, so
        # the same stale-pyc channel would corrupt their task attribution.
        copy_case_tree(oracle_dir, wt / "oracle")
        report_path = wt / "oracle-report.xml"
        cmd = adapter.oracle_test_cmd("oracle", str(report_path))
        await _bounded_shell(cmd, str(wt), timeout_s, env=run_env)

        try:
            xml_text = report_path.read_text(encoding="utf-8")
        except OSError:
            xml_text = ""
        score, passed, total, detail = grade_from_junit(xml_text)
        per_test: dict[str, bool] = {}
        if xml_text:
            try:
                per_test = dict(grade_testcases_from_junit(xml_text))
            except Exception:
                per_test = {}
            if passed < total:
                failing = [k for k, ok in per_test.items() if not ok]
                if failing:
                    detail = f"{passed}/{total} oracle tests passed; failed: {', '.join(failing)}"

        passed_val: bool | None = None
        if mode in ("reference", "tree"):
            passed_val = total > 0 and passed == total
        elif mode == "floor":
            passed_val = True

        if mode == "tree":
            return TreeCheck(
                passed=passed_val,
                tests_passed=passed,
                tests_total=total,
                detail=detail,
                per_test=per_test,
            )
        return SuiteCheck(
            passed=passed_val,
            tests_passed=passed,
            tests_total=total,
            detail=detail,
        )


def _run_sync(coro):
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


def run_tree_check(case_dir: Path | str, tree_dir: Path | str, timeout_s: int = 600) -> TreeCheck:
    """016 D-7: grades an arbitrary tree against the case's oracle in the
    per-grade environment, per test. The tree is the code source; the
    case's own reference/ is never consulted."""
    return cast(
        TreeCheck, _run_sync(_run_check_async(Path(case_dir), "tree", timeout_s, Path(tree_dir)))
    )
