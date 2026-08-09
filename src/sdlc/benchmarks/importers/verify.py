"""The import-time gate: an imported case's oracle must pass against the
reference implementation shipped with it (E-79, spec section 7).

Mirrors the worktree shape grade_oracle builds -- reference sources at the
root, oracle/ copied in beside them -- minus git, and runs the oracle through
the SAME ToolchainAdapter command grade_oracle uses.

Using the adapter command rather than `python -m pytest` is load-bearing:
`python -m pytest` prepends the working directory to sys.path, bare `pytest`
does not. A gate that ran the friendlier invocation would go green on a case
that scores zero under the real grader, which is precisely the failure this
gate exists to prevent.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel

from ...toolchain.adapters import TOOLCHAINS, ToolchainKind


class VerifyResult(BaseModel):
    case_id: str
    ok: bool
    returncode: int
    output: str


def verify_case(case_dir: Path, *, timeout_s: int = 600) -> VerifyResult:
    """Run <case>/oracle against <case>/reference in a throwaway worktree."""
    case_dir = Path(case_dir)
    case_id = case_dir.name
    ref = case_dir / "reference"
    oracle = case_dir / "oracle"
    if not ref.is_dir():
        return VerifyResult(case_id=case_id, ok=False, returncode=-1,
                            output=f"no reference/ dir in {case_dir}")
    if not oracle.is_dir():
        return VerifyResult(case_id=case_id, ok=False, returncode=-1,
                            output=f"no oracle/ dir in {case_dir}")

    parent = tempfile.mkdtemp(prefix=f"verify-{case_id}-")
    try:
        wt = Path(parent) / "wt"
        shutil.copytree(ref, wt)
        shutil.copytree(oracle, wt / "oracle")
        adapter = TOOLCHAINS[ToolchainKind.PYTHON]
        cmd = adapter.oracle_test_cmd("oracle", str(wt / "oracle-report.xml"))
        proc = subprocess.run(
            cmd, shell=True, cwd=wt, capture_output=True, text=True,
            timeout=timeout_s)
        return VerifyResult(case_id=case_id, ok=proc.returncode == 0,
                            returncode=proc.returncode,
                            output=proc.stdout + proc.stderr)
    except subprocess.TimeoutExpired:
        return VerifyResult(case_id=case_id, ok=False, returncode=-1,
                            output=f"oracle timed out after {timeout_s}s")
    finally:
        shutil.rmtree(parent, ignore_errors=True)
