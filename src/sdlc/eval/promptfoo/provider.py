"""promptfoo custom provider: one variant of one role on one fixture.

promptfoo's PROVIDER axis is the A/B axis -- the same file appears twice in
the config with different `instructions_ref`, so baseline vs working-tree
renders as a native side-by-side matrix and no custom compare loop exists.

Contract (promptfoo docs, providers/python): return a dict that ALWAYS
carries "output", even on failure. This function therefore never raises.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from ..fixtures import load_fixture
from ..runner import run_variant_detailed

# Tests inject a TestModel/FunctionModel here so no real model is called.
# Production leaves it None and the fixture's captured author model is used.
_MODEL_OVERRIDE: Any | None = None


def _token_usage(usage: Any) -> dict:
    """pydantic-ai Usage -> promptfoo's tokenUsage shape. Defensive about
    attribute names so a pydantic-ai bump degrades to zeros rather than
    crashing a gate run."""
    prompt = getattr(usage, "input_tokens", 0) or 0
    completion = getattr(usage, "output_tokens", 0) or 0
    return {"prompt": prompt, "completion": completion,
            "total": prompt + completion}


def _cost_usd(usage: Any, model: str) -> float | None:
    """USD for this run, via the SAME lookup the budget gate uses.

    Delegates to pricing.compute_price rather than calling genai-prices
    directly: that function already splits the registry's routing prefix
    ("anthropic:glm-5.2") from the pricing provider and retries unhinted,
    which a naive calc_price call gets wrong (glm is priced under zhipuai).
    Returns None for an unknown model -- a missing price must not fail a
    gate, and verdict.py treats None as not-measured.
    """
    from ...pricing import PriceUsageInput, compute_price
    return compute_price(PriceUsageInput(
        model=model,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_tokens", 0) or 0,
        cache_write_tokens=getattr(usage, "cache_write_tokens", 0) or 0))


def resolve_instructions(role: str, ref: str, repo_root: Path,
                         agents_dir: Path) -> str:
    """Instructions text at `ref`: the worktree file, or `git show`."""
    if ref == "worktree":
        return (agents_dir / role / "instructions.md").read_text(
            encoding="utf-8")
    rel = f"agents/{role}/instructions.md"
    proc = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=repo_root,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise FileNotFoundError(
            f"{rel} does not exist at ref '{ref}': {proc.stderr.strip()}")
    return proc.stdout


def call_api(prompt: str, options: dict, context: dict) -> dict:
    """`prompt` is ignored: the frozen input comes from the fixture, not from
    promptfoo's prompt axis, so both providers see byte-identical input."""
    started = time.monotonic()
    try:
        cfg = options["config"]
        agents_dir = Path(cfg["agents_dir"])
        instructions = resolve_instructions(
            cfg["role"], cfg["instructions_ref"], Path(cfg["repo_root"]),
            agents_dir)
        fixture = load_fixture(Path(cfg["fixture_path"]))
        out, usage = run_variant_detailed(
            cfg["role"], instructions, fixture, agents_dir,
            model_override=_MODEL_OVERRIDE)
        return {
            "output": out,
            "error": None,
            "tokenUsage": _token_usage(usage),
            "cost": _cost_usd(usage, fixture.model),
            "latencyMs": int((time.monotonic() - started) * 1000),
        }
    except Exception as exc:                      # never raise -- see docstring
        return {
            "output": "",
            "error": f"{type(exc).__name__}: {exc}",
            "latencyMs": int((time.monotonic() - started) * 1000),
        }
