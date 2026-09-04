import json

from sdlc.core.models import (
    HarnessKind,
)
from sdlc.harness.base import HarnessRequest
from sdlc.harness.cursor import CursorHarness
from sdlc.harness.registry import HARNESSES, check_harness_versions
from sdlc.harness.session import digest_of


def test_cursor_parse_extracts_tokens_and_cost():
    payload = {
        "type": "result",
        "session_id": "cur1",
        "total_cost_usd": 0.07,
        "result": "done",
        "usage": {"input_tokens": 900, "output_tokens": 42},
    }
    res = CursorHarness().parse(json.dumps(payload), 0)
    assert res.session_id == "cur1"
    assert res.cost_usd == 0.07
    assert res.input_tokens == 900
    assert res.output_tokens == 42
    assert res.harness == HarnessKind.CURSOR


def test_cursor_parse_raw_fallback_on_non_json():
    res = CursorHarness().parse("not json at all", 1)
    assert res.summary == "not json at all"


def test_cursor_normalise_session_yields_canonical_events():
    stream = "\n".join(
        [
            json.dumps({"type": "system", "session_id": "cur1", "model": "sonnet-4.5"}),
            json.dumps(
                {
                    "type": "assistant",
                    "session_id": "cur1",
                    "message": {
                        "content": [
                            {"type": "text", "text": "let me edit"},
                            {"type": "tool_use", "name": "edit_file", "input": {"path": "app.py"}},
                            {
                                "type": "tool_use",
                                "name": "run_terminal_cmd",
                                "input": {"command": "pytest"},
                            },
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "session_id": "cur1",
                    "result": "ok",
                    "usage": {"input_tokens": 5, "output_tokens": 1},
                }
            ),
        ]
    )
    sess = CursorHarness().normalise_session(stream)
    assert sess.model == "sonnet-4.5"
    kinds = [e.kind for e in sess.events]
    assert "model_turn" in kinds
    assert "file_write" in kinds
    assert "command" in kinds
    dig = digest_of(sess)
    assert dig.files_written == 1
    assert dig.model_turns == 1


def test_cursor_build_cmd_headless_flags():
    cmd = CursorHarness().build_cmd(
        HarnessRequest(
            prompt="do stuff",
            cwd="/tmp/wt",
            model="sonnet-4.5",
            session_id="cur1",
            extra_args=["--x"],
        )
    )
    assert cmd[0] == "cursor-agent"
    assert "-p" in cmd and "do stuff" in cmd
    assert "--output-format" in cmd and "stream-json" in cmd
    assert "--model" in cmd and "sonnet-4.5" in cmd
    assert "--resume" in cmd and "cur1" in cmd
    assert "--force" in cmd
    assert "--x" in cmd


def test_cursor_registered_in_harnesses():
    assert isinstance(HARNESSES[HarnessKind.CURSOR], CursorHarness)


import logging


def test_version_check_warns_on_drift(monkeypatch, caplog):
    from sdlc.harness import registry

    monkeypatch.setattr(registry.shutil, "which", lambda c: "/usr/bin/" + c)

    class _Res:
        stdout = "9.9.9 (drifted)"

    monkeypatch.setattr(registry.subprocess, "run", lambda *a, **k: _Res())
    caplog.set_level(logging.WARNING, logger="sdlc.harness.registry")
    check_harness_versions()  # claude pinned 2.1.218 vs 9.9.9 -> drift
    assert any("version drift" in r.message for r in caplog.records)


def test_version_check_skips_when_cli_absent(monkeypatch, caplog):
    from sdlc.harness import registry

    monkeypatch.setattr(registry.shutil, "which", lambda c: None)
    caplog.set_level(logging.WARNING, logger="sdlc.harness.registry")
    check_harness_versions()
    assert not any("version drift" in r.message for r in caplog.records)


def test_version_check_silent_on_match(monkeypatch, caplog):
    from sdlc.harness import registry

    monkeypatch.setattr(registry.shutil, "which", lambda c: "/usr/bin/" + c)
    versions = {"claude": "2.1.218 (Claude Code)", "opencode": "1.18.4", "cursor-agent": "0.0.0"}

    def _run(cmd, *a, **k):
        class _R:
            stdout = versions.get(cmd[0], "0.0.0")

        return _R()

    monkeypatch.setattr(registry.subprocess, "run", _run)
    caplog.set_level(logging.WARNING, logger="sdlc.harness.registry")
    check_harness_versions()  # claude+opencode match pins; cursor unpinned
    assert not any("version drift" in r.message for r in caplog.records)
