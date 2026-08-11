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
