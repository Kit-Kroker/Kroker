"""F2 doctor: rendering and the CLI surface (spec sections 2, 4, 8)."""

import argparse
import json
import os
import subprocess
import sys

import pytest

from sdlc.doctor.cli import add_doctor_parser, render_json, render_table, run_doctor
from sdlc.doctor.models import CheckResult


def _parse(argv):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    add_doctor_parser(sub)
    return p.parse_args(argv)


def _results():
    return [
        CheckResult.ok("git", "git version 2.47.1"),
        CheckResult.warn("harness versions", "opencode is 1.19.0, pinned 1.18.4"),
        CheckResult.fail("gh", "gh is not on PATH"),
        CheckResult.skip("crew CLIs", "no crew/layouts in this checkout"),
    ]


def test_parser_defaults_are_off():
    args = _parse(["doctor"])
    assert args.cmd == "doctor"
    assert args.as_json is False
    assert args.strict is False


def test_parser_accepts_both_flags():
    args = _parse(["doctor", "--json", "--strict"])
    assert args.as_json is True
    assert args.strict is True


def test_table_shows_every_status_and_a_tally():
    out = render_table(_results())
    for token in ("[PASS]", "[WARN]", "[FAIL]", "[SKIP]"):
        assert token in out
    assert "1 passed" in out
    assert "1 warning" in out
    assert "1 failed" in out
    assert "1 skipped" in out


def test_table_prints_a_skip_reason_rather_than_omitting_the_line():
    """A SKIP whose line is dropped is indistinguishable from a check that
    does not exist (spec section 4)."""
    out = render_table(_results())
    assert "no crew/layouts" in out


def test_json_round_trips_every_result():
    parsed = json.loads(render_json(_results()))
    assert [r["name"] for r in parsed] == ["git", "harness versions", "gh", "crew CLIs"]
    assert [r["status"] for r in parsed] == ["PASS", "WARN", "FAIL", "SKIP"]
    assert parsed[2]["detail"] == "gh is not on PATH"


@pytest.mark.asyncio
async def test_run_doctor_returns_one_when_a_check_fails(monkeypatch, capsys):
    async def _fake():
        return [CheckResult.ok("a", ""), CheckResult.fail("b", "broken")]

    monkeypatch.setattr("sdlc.doctor.cli.run_checks", _fake)
    code = await run_doctor(_parse(["doctor"]))
    assert code == 1
    assert "[FAIL]" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_doctor_returns_zero_on_a_warn_unless_strict(monkeypatch, capsys):
    async def _fake():
        return [CheckResult.warn("b", "hazard")]

    monkeypatch.setattr("sdlc.doctor.cli.run_checks", _fake)
    assert await run_doctor(_parse(["doctor"])) == 0
    capsys.readouterr()
    assert await run_doctor(_parse(["doctor", "--strict"])) == 1


@pytest.mark.asyncio
async def test_run_doctor_json_mode_emits_only_json(monkeypatch, capsys):
    async def _fake():
        return [CheckResult.ok("a", "fine")]

    monkeypatch.setattr("sdlc.doctor.cli.run_checks", _fake)
    await run_doctor(_parse(["doctor", "--json"]))
    out = capsys.readouterr().out
    assert json.loads(out)[0]["name"] == "a"


def test_doctor_is_reachable_through_the_real_parser():
    """Not the local parser the other tests build -- sdlc.cli.build_parser,
    the one main() actually uses."""
    from sdlc.cli import build_parser

    args = build_parser().parse_args(["doctor", "--strict"])
    assert args.cmd == "doctor"
    assert args.strict is True
    assert args.as_json is False


def test_doctor_reports_instead_of_crashing_without_provider_keys():
    """The machine doctor exists for has no keys yet. sdlc.cli used to import
    the worker at module level, which builds the agent registry, which fails
    closed without EXA_API_KEY -- so doctor died on a traceback before it
    could report the missing key. A subprocess, because the failure was at
    import and this process already holds conftest's placeholder keys.

    Empty rather than removed: load_dotenv never overrides a variable that
    is set, so a developer's own .env cannot leak real keys into the child.
    """
    env = dict(os.environ)
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "EXA_API_KEY", "ZAI_API_KEY"):
        env[key] = ""
    env["TEMPORAL_HOST"] = "127.0.0.1:1"  # refused at once; no 3s probe timeout

    out = subprocess.run(
        [sys.executable, "-m", "sdlc.cli", "doctor", "--json"],
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=120,
    )

    assert "Traceback" not in out.stderr, out.stderr
    rows = {r["name"]: r for r in json.loads(out.stdout)}
    assert rows["agents registry"]["status"] == "FAIL"
    assert "EXA_API_KEY" in rows["agents registry"]["detail"]
    assert out.returncode == 1
