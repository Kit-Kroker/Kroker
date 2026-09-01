"""Generate promptfooconfig.yaml for one (role, case) pair.

Generated into a scratch dir and never committed: a hand-maintained config
would drift from agents/<role>/agent.yaml. The two providers differ ONLY in
instructions_ref -- that is the A/B axis (E-82 design doc 4.3).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from ..fixtures import build_fixture

_HERE = Path(__file__).resolve().parent


def _rel_file_url(target: Path, out_dir: Path) -> str:
    """A `file://` URL promptfoo can actually resolve.

    promptfoo joins the config's directory onto the path in a `file://`
    provider/assertion URL. An absolute Windows path therefore becomes
    nonsense -- `C:\\...\\tmp\\D:\\own\\Kroker\\...` -- and the worker dies with
    OSError 22. So the path must be RELATIVE to the config's own directory,
    which in turn requires out_dir to sit on the same drive as this package
    (run_gate puts its scratch dir under the repo for exactly that reason).
    Forward slashes: promptfoo parses the URL, and backslashes are escapes.
    """
    return "file://" + os.path.relpath(target, out_dir).replace("\\", "/")


def build_config(
    role: str,
    case: str,
    *,
    repo_root: Path,
    cases_root: Path,
    agents_dir: Path,
    judge_model: str,
    out_dir: Path,
    repeat: int = 3,
    baseline_ref: str = "HEAD",
    max_cost_usd: float = 0.50,
    max_latency_ms: int = 120_000,
    mutation: str | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture = build_fixture(role, case, cases_root, agents_dir)
    fixture_path = out_dir / "fixture.json"
    fixture_path.write_text(fixture.model_dump_json(indent=2), encoding="utf-8")

    provider_cfg = {
        "role": role,
        "fixture_path": str(fixture_path),
        "agents_dir": str(agents_dir),
        "repo_root": str(repo_root),
    }
    provider_id = f"{_rel_file_url(_HERE / 'provider.py', out_dir)}:call_api"

    # E-83: a mutation is the working side's literal instructions body. It
    # rides provider config as `instructions_text`, which call_api prefers
    # over the git ref -- so a degraded prompt is injected without touching
    # agents/<role>/instructions.md (the baseline is `git show`-resolved, so
    # a worktree edit would move BOTH sides and measure nothing).
    working_cfg = {**provider_cfg, "instructions_ref": "worktree"}
    if mutation is not None:
        working_cfg["instructions_text"] = mutation

    cfg = {
        "description": f"prompt gate: {role} on {case}",
        "prompts": ["{{input}}"],  # unused: the fixture is the input
        "providers": [
            {
                "id": provider_id,
                "label": "baseline",
                "config": {**provider_cfg, "instructions_ref": baseline_ref},
            },
            {"id": provider_id, "label": "working", "config": working_cfg},
        ],
        "defaultTest": {
            "vars": {
                "role": role,
                "case": case,
                "author_model": fixture.model,
                "judge_model": judge_model,
                "cases_root": str(cases_root),
                "agents_dir": str(agents_dir),
            },
            # ABSOLUTE first (they gate), advisory judge last. Order is
            # cosmetic to promptfoo but keeps results.json readable.
            "assert": [
                {"type": "python", "value": _rel_file_url(_HERE / "absolute.py", out_dir)},
                {"type": "cost", "threshold": max_cost_usd},
                {"type": "latency", "threshold": max_latency_ms},
                {"type": "python", "value": _rel_file_url(_HERE / "assertion.py", out_dir)},
            ],
        },
        "tests": [{"vars": {"input": fixture.prompt}}],
        "repeat": repeat,
    }
    path = out_dir / "promptfooconfig.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path
