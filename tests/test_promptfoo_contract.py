"""Does the INSTALLED promptfoo still accept our config shape?

Needs promptfoo on PATH but no API keys: the provider is canned. This is the
test that catches a promptfoo version bump changing the schema.
"""
from __future__ import annotations

import json
import subprocess

import pytest
import yaml

from sdlc.eval.promptfoo import promptfoo_bin

pytestmark = pytest.mark.skipif(
    promptfoo_bin() is None,
    reason="promptfoo not installed (pip install -e .[eval])")

CANNED = '''
def call_api(prompt, options, context):
    return {"output": "canned-" + options["config"]["tag"], "error": None}
'''


def test_config_shape_is_accepted(tmp_path):
    (tmp_path / "canned.py").write_text(CANNED, encoding="utf-8")
    cfg = {
        "description": "contract",
        "prompts": ["{{input}}"],
        "providers": [
            {"id": f"file://{tmp_path / 'canned.py'}:call_api",
             "label": "baseline", "config": {"tag": "a"}},
            {"id": f"file://{tmp_path / 'canned.py'}:call_api",
             "label": "working", "config": {"tag": "b"}},
        ],
        "defaultTest": {"assert": [{"type": "contains", "value": "canned-"}]},
        "tests": [{"vars": {"input": "x"}}],
    }
    (tmp_path / "promptfooconfig.yaml").write_text(
        yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    out = tmp_path / "results.json"
    proc = subprocess.run(
        [promptfoo_bin(), "eval",
         "-c", str(tmp_path / "promptfooconfig.yaml"),
         "--output", str(out)],
        capture_output=True, text=True, cwd=tmp_path)
    assert out.is_file(), f"promptfoo produced no output.\n{proc.stderr}"

    data = json.loads(out.read_text(encoding="utf-8"))
    rows = data["results"]["results"]
    labels = {r["provider"]["label"] for r in rows}
    assert labels == {"baseline", "working"}, (
        f"provider labels moved in results.json: {labels}")
    assert all("gradingResult" in r for r in rows), (
        "gradingResult key moved — eval/verdict.py reads it")


def test_assertion_score_survives_into_results_json(tmp_path):
    """verdict.py reads componentResults[].score to compute the regression.
    promptfoo reports score=1 for passing native assertions (cost, latency),
    so it is not obvious that a custom assertion's own number survives rather
    than being normalised to 1. It does -- and if that ever changes, every
    regression verdict silently becomes 'no change'.
    """
    (tmp_path / "p.py").write_text(
        'def call_api(prompt, options, context):\n'
        '    return {"output": "hello", "error": None}\n', encoding="utf-8")
    (tmp_path / "a.py").write_text(
        'def get_assert(output, context):\n'
        '    return {"pass": True, "score": 0.42, "reason": "canned"}\n',
        encoding="utf-8")
    cfg = {
        "description": "score-fidelity",
        "prompts": ["{{input}}"],
        "providers": [{"id": "file://p.py:call_api", "label": "baseline",
                       "config": {}}],
        "defaultTest": {"assert": [{"type": "python", "value": "file://a.py"}]},
        "tests": [{"vars": {"input": "x"}}],
    }
    (tmp_path / "promptfooconfig.yaml").write_text(
        yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    out = tmp_path / "results.json"
    subprocess.run(
        [promptfoo_bin(), "eval", "-c",
         str(tmp_path / "promptfooconfig.yaml"), "--output", str(out)],
        capture_output=True, cwd=tmp_path)
    data = json.loads(out.read_text(encoding="utf-8"))
    scores = [c["score"]
              for r in data["results"]["results"]
              for c in r["gradingResult"]["componentResults"]
              if "a.py" in str(c["assertion"].get("value"))]
    assert scores == [0.42], (
        f"custom assertion score was not preserved: {scores}")
