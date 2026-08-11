"""Generate promptfooconfig.yaml for one (role, case) pair.

Generated into a scratch dir and never committed: a hand-maintained config
would drift from agents/<role>/agent.yaml. The two providers differ ONLY in
instructions_ref -- that is the A/B axis (E-82 design doc 4.3).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..fixtures import build_fixture

_HERE = Path(__file__).resolve().parent


def build_config(role: str, case: str, *, repo_root: Path, cases_root: Path,
                 agents_dir: Path, judge_model: str, out_dir: Path,
                 repeat: int = 3, baseline_ref: str = "HEAD",
                 max_cost_usd: float = 0.50,
                 max_latency_ms: int = 120_000) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture = build_fixture(role, case, cases_root, agents_dir)
    fixture_path = out_dir / "fixture.json"
    fixture_path.write_text(fixture.model_dump_json(indent=2),
                            encoding="utf-8")

    provider_cfg = {
        "role": role,
        "fixture_path": str(fixture_path),
        "agents_dir": str(agents_dir),
        "repo_root": str(repo_root),
    }
    provider_id = f"file://{_HERE / 'provider.py'}:call_api"

    cfg = {
        "description": f"prompt gate: {role} on {case}",
        "prompts": ["{{input}}"],       # unused: the fixture is the input
        "providers": [
            {"id": provider_id, "label": "baseline",
             "config": {**provider_cfg, "instructions_ref": baseline_ref}},
            {"id": provider_id, "label": "working",
             "config": {**provider_cfg, "instructions_ref": "worktree"}},
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
                {"type": "python",
                 "value": f"file://{_HERE / 'absolute.py'}"},
                {"type": "cost", "threshold": max_cost_usd},
                {"type": "latency", "threshold": max_latency_ms},
                {"type": "python",
                 "value": f"file://{_HERE / 'assertion.py'}"},
            ],
        },
        "tests": [{"vars": {"input": fixture.prompt}}],
        "repeat": repeat,
    }
    path = out_dir / "promptfooconfig.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path
