from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel

from sdlc.eval.fixtures import EvalFixture
from sdlc.eval.promptfoo.provider import call_api, resolve_instructions

AGENTS = Path(__file__).resolve().parents[1] / "agents"
ROOT = Path(__file__).resolve().parents[1]


def _fixture(tmp_path: Path) -> Path:
    fx = EvalFixture(role="clarify", case="c", prompt="build a login page",
                     model="anthropic:glm-5.2", source_run_id="_built")
    p = tmp_path / "c.json"
    p.write_text(fx.model_dump_json(), encoding="utf-8")
    return p


def _opts(tmp_path: Path, ref: str = "worktree") -> dict:
    return {"config": {"role": "clarify", "instructions_ref": ref,
                       "fixture_path": str(_fixture(tmp_path)),
                       "agents_dir": str(AGENTS), "repo_root": str(ROOT)}}


def test_returns_output_key_with_serialized_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr("sdlc.eval.promptfoo.provider._MODEL_OVERRIDE",
                        TestModel())
    res = call_api("ignored", _opts(tmp_path), {})
    assert "output" in res
    assert res.get("error") is None
    json.loads(res["output"])          # proposer output serializes to JSON


def test_always_returns_output_even_on_error(tmp_path):
    opts = _opts(tmp_path)
    opts["config"]["role"] = "no-such-role"
    res = call_api("ignored", opts, {})
    assert res["output"] == ""
    assert res["error"]


def test_never_raises_on_missing_fixture(tmp_path):
    opts = _opts(tmp_path)
    opts["config"]["fixture_path"] = str(tmp_path / "absent.json")
    res = call_api("ignored", opts, {})
    assert res["output"] == ""
    assert "absent.json" in res["error"]


def test_reports_latency(tmp_path, monkeypatch):
    monkeypatch.setattr("sdlc.eval.promptfoo.provider._MODEL_OVERRIDE",
                        TestModel())
    res = call_api("ignored", _opts(tmp_path), {})
    assert isinstance(res["latencyMs"], int)
    assert res["latencyMs"] >= 0


def test_reports_token_usage(tmp_path, monkeypatch):
    """The config's native `cost` assert is an ABSOLUTE gating check; it is
    vacuous unless the provider actually reports usage."""
    monkeypatch.setattr("sdlc.eval.promptfoo.provider._MODEL_OVERRIDE",
                        TestModel())
    res = call_api("ignored", _opts(tmp_path), {})
    assert set(res["tokenUsage"]) >= {"prompt", "completion", "total"}
    assert res["tokenUsage"]["total"] >= 0


def test_resolve_instructions_worktree_reads_the_file():
    text = resolve_instructions("clarify", "worktree", ROOT, AGENTS)
    assert text == (AGENTS / "clarify" / "instructions.md").read_text(
        encoding="utf-8")


def test_resolve_instructions_git_ref_reads_from_git():
    text = resolve_instructions("clarify", "HEAD", ROOT, AGENTS)
    assert isinstance(text, str) and text


def test_cost_resolves_for_the_shipped_role_models():
    """A permanently-None cost makes the config's ABSOLUTE `cost` gate
    vacuous. Delegating to pricing.compute_price is what makes the registry's
    routing prefix (anthropic:glm-5.2, priced under zhipuai) resolve."""
    from sdlc.eval.promptfoo.provider import _cost_usd

    class _U:
        input_tokens, output_tokens = 1000, 500
        cache_read_tokens = cache_write_tokens = 0

    assert _cost_usd(_U(), "anthropic:glm-5.2") is not None
    assert _cost_usd(_U(), "openai/gpt-5.2") is not None


def test_cost_is_none_for_an_unknown_model():
    from sdlc.eval.promptfoo.provider import _cost_usd

    class _U:
        input_tokens, output_tokens = 10, 10
        cache_read_tokens = cache_write_tokens = 0

    assert _cost_usd(_U(), "nonesuch:not-a-real-model") is None


def test_provider_imports_fast_enough_for_the_promptfoo_worker():
    """promptfoo spawns the Python provider in a worker with a readiness
    timeout. Importing sdlc.agents.roles eagerly builds every agent and wraps
    each in a TemporalAgent (~18s), which blew that timeout and made the gate
    unrunnable -- hence agents/settings.py. Guard against the import creeping
    back."""
    import os
    import subprocess
    import sys
    import time

    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-c", "import sdlc.eval.promptfoo.provider"],
        capture_output=True, text=True, env=os.environ)
    elapsed = time.monotonic() - started
    assert proc.returncode == 0, proc.stderr[-500:]
    assert elapsed < 8.0, (
        f"provider import took {elapsed:.1f}s; promptfoo's worker will time "
        f"out. Something re-introduced a heavy import (sdlc.agents.roles?).")


def test_provider_does_not_import_agents_roles():
    """The direct cause of the timeout, asserted structurally so the reason is
    obvious when this fails."""
    import subprocess
    import sys

    code = ("import sys; import sdlc.eval.promptfoo.provider; "
            "print('sdlc.agents.roles' in sys.modules)")
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True)
    assert proc.stdout.strip() == "False", (
        "sdlc.agents.roles got pulled into the provider's import graph again")


@pytest.mark.parametrize("module_name", ["provider", "absolute", "assertion"])
def test_loads_standalone_the_way_promptfoo_loads_it(module_name):
    """promptfoo loads these files with importlib.spec_from_file_location, so
    they have NO parent package and any relative import raises 'attempted
    relative import with no known parent package'. Exercise that exact load
    path -- a plain `import sdlc.eval.promptfoo.provider` would NOT catch it.
    """
    import importlib.util

    path = (Path(__file__).resolve().parents[1] / "src" / "sdlc" / "eval"
            / "promptfoo" / f"{module_name}.py")
    spec = importlib.util.spec_from_file_location(f"_standalone_{module_name}",
                                                  path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)          # must not raise


def test_standalone_call_api_has_no_deferred_relative_import(tmp_path):
    """Import-time loading is not enough: a relative import INSIDE a function
    fails the same way, just later. _cost_usd hid one, and the gate reported
    'ImportError: attempted relative import' at call time with the module
    having loaded cleanly. Drive a real call through the standalone module.
    """
    import importlib.util

    from pydantic_ai.models.test import TestModel

    path = (Path(__file__).resolve().parents[1] / "src" / "sdlc" / "eval"
            / "promptfoo" / "provider.py")
    spec = importlib.util.spec_from_file_location("_standalone_call", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._MODEL_OVERRIDE = TestModel()

    res = mod.call_api("ignored", _opts(tmp_path), {})
    assert res.get("error") is None, res["error"]
    assert res["cost"] is not None, "cost lookup silently failed standalone"
