"""Run the prompt gate: generate config, run promptfoo, decide, record.

Surfaced as a pytest marker rather than a CI workflow because this repo has
no CI yet (E-82 design doc 4.7). It becomes a one-line CI step unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .fixtures import validate_role
from .promptfoo import promptfoo_bin
from .promptfoo.config import build_config
from .promptfoo.provider import resolve_instructions
from .verdict import (GateVerdict, JudgeStatus, PromptGateResult, decide,
                      write_result)

_DEFAULT_OUT = Path("runs") / "prompt_evals"
# One agent call + one judge call, per provider, per repetition.
_CALLS_PER_REPEAT = 2 * 2


class GateUnavailable(Exception):
    """The gate was explicitly requested but cannot run."""


def prompt_sha(role: str, ref: str, repo_root: Path, agents_dir: Path) -> str:
    """sha256 over the instructions bytes -- the same hash agents/roles.py:108
    puts on BenchmarkRecord.prompt_sha, so the two instruments join."""
    text = resolve_instructions(role, ref, repo_root, agents_dir)
    return hashlib.sha256(text.encode()).hexdigest()


def _run_promptfoo(config_path: Path, out_path: Path) -> None:
    binary = promptfoo_bin()
    # Decode explicitly as UTF-8: `text=True` uses the locale encoding, which
    # is cp1252 on Windows, and promptfoo emits UTF-8 box-drawing in its
    # progress output -- the reader thread dies with UnicodeDecodeError before
    # any error text reaches us.
    proc = subprocess.run(
        [binary, "eval", "-c", str(config_path), "--output", str(out_path)],
        capture_output=True, cwd=config_path.parent, env=os.environ)
    if not out_path.is_file():
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        # The actionable message ("Python worker stderr: ...") goes to stdout,
        # not stderr, so surface both.
        detail = (err or out)[-800:]
        raise GateUnavailable(
            f"promptfoo produced no results.json (exit {proc.returncode}): "
            f"{detail}")


def run_gate(role: str, case: str, *, repo_root: Path, cases_root: Path,
             agents_dir: Path, judge_model: str, repeat: int = 3,
             delta_min: float = 0.05, baseline_ref: str = "HEAD",
             max_calls: int = 40,
             out_dir: Path | None = None) -> PromptGateResult:
    # Before any git/filesystem work: an unknown role must not surface as a
    # raw FileNotFoundError from `git show HEAD:agents/<role>/instructions.md`.
    validate_role(role)

    if promptfoo_bin() is None:
        raise GateUnavailable(
            "promptfoo is not installed. `pip install -e .[eval]` — the gate "
            "was explicitly requested, so this is a failure, not a skip.")

    sha_base = prompt_sha(role, baseline_ref, repo_root, agents_dir)
    sha_work = prompt_sha(role, "worktree", repo_root, agents_dir)

    if sha_base == sha_work:
        result = PromptGateResult(
            verdict=GateVerdict.PASS, judge_status=JudgeStatus.NO_BASELINE,
            role=role, case=case, prompt_sha_baseline=sha_base,
            prompt_sha_working=sha_work,
            reason=f"prompt unchanged vs {baseline_ref} — no model calls made")
    else:
        planned = repeat * _CALLS_PER_REPEAT
        if planned > max_calls:
            raise GateUnavailable(
                f"planned {planned} model calls (repeat={repeat} × 2 "
                f"providers × 2 calls) exceeds max_calls={max_calls}. "
                f"Lower --n or raise the ceiling deliberately.")
        # Scratch dir under the repo, NOT the system temp: promptfoo resolves
        # `file://` provider paths relative to the config's directory, so the
        # config must sit on the same drive as this package for a relative
        # path to exist at all (Windows: C:\Temp vs D:\repo). runs/ is
        # gitignored, so nothing generated here can be committed by accident.
        scratch_root = repo_root / "runs" / ".prompt_gate"
        scratch_root.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.mkdtemp(dir=scratch_root)
        try:
            tmp_path = Path(tmp)
            cfg = build_config(role, case, repo_root=repo_root,
                               cases_root=cases_root, agents_dir=agents_dir,
                               judge_model=judge_model, out_dir=tmp_path,
                               repeat=repeat, baseline_ref=baseline_ref)
            results_path = tmp_path / "results.json"
            _run_promptfoo(cfg, results_path)
            results = json.loads(results_path.read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        result = decide(results, delta_min=delta_min)
        result.role, result.case = role, case
        result.prompt_sha_baseline = sha_base
        result.prompt_sha_working = sha_work

    write_result(result, out_dir or (repo_root / _DEFAULT_OUT))
    return result
