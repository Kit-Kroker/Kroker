"""The Node gate's contract (spec C §9)."""

from pathlib import Path

from scripts.check_ui import STEPS, main


def test_skips_cleanly_when_npm_is_absent(monkeypatch):
    monkeypatch.setattr("scripts.check_ui.shutil.which", lambda _: None)
    assert main([]) == 0


def test_says_so_loudly_when_it_skips(monkeypatch, capsys):
    monkeypatch.setattr("scripts.check_ui.shutil.which", lambda _: None)
    main([])
    assert "SKIPPED" in capsys.readouterr().out


def test_every_step_is_a_workspace_aware_npm_invocation():
    for _, args in STEPS:
        assert args[0] in {"ci", "run", "exec"}


def test_ci_invokes_this_script_and_never_npm_directly():
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    runs = [ln.split("run:", 1)[1].strip() for ln in ci.splitlines() if "run:" in ln]
    assert any("check_ui.py" in r for r in runs), "ci.yml must invoke the wrapper"
    assert not any(r.startswith(("npm", "npx")) for r in runs), (
        "a bare npm/npx run: line breaks tests/test_verify.py parity"
    )
