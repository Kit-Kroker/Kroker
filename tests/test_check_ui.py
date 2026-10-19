"""The Node gate's contract (spec C §9)."""

from pathlib import Path
from types import SimpleNamespace

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


# --- T2 (sbatch-2026-10-19): explicit vitest --testTimeout under load -------
#
# vitest's default per-test budget is 5000 ms. Under the npm wrapper in
# kroker-dev the 006 SG-2 fire timed the same static import-graph test out
# 3/3 while a direct `npx vitest run` passed 374/374 twice — jsdom
# environment setup alone took ~30 s there (matrix:
# .workspace/tmp/executor-006-SG2-report.md), so the wrapper must forward
# an explicit per-test timeout instead of relying on the default. The flag
# rides AFTER the bare `--` separator (npm consumes flags before it; only
# what follows reaches the vitest CLI — the same forwarding
# playwright-browser already uses). The timeout is a wrapper concern: the
# vitest configs and test files stay untouched.


def _timeout_flags(args: list[str]) -> list[str]:
    """The explicit ``--testTimeout=<ms>`` tokens in a step's npm argv."""
    return [t for t in args if t.startswith("--testTimeout=")]


def test_both_vitest_steps_carry_an_explicit_per_test_timeout():
    # >= 30000 clears the worst observed jsdom setup; <= 300000 keeps the
    # flag a hang detector rather than a hang allowance.
    vitest = [(label, args) for label, args in STEPS if label.startswith("vitest")]
    assert {label for label, _ in vitest} == {"vitest-dashboard", "vitest-ui"}, (
        "expected exactly the two vitest steps; the timeout contract below "
        f"is written against them, found {[name for name, _ in vitest]}"
    )
    for label, args in vitest:
        flags = _timeout_flags(args)
        assert flags, (
            f"step {label!r} forwards no --testTimeout=<ms>: the vitest default "
            "5000 ms times jsdom-heavy files out under wrapper + container load "
            "(006 SG-2 fire, 3/3 vs 374/374 direct)"
        )
        assert len(flags) == 1, f"step {label!r} carries {flags}; expected exactly one"
        value = int(flags[0].split("=", 1)[1])
        assert 30_000 <= value <= 300_000, (
            f"step {label!r} forwards --testTimeout={value}: outside "
            "[30000, 300000] — below the worst observed env setup or no "
            "longer a hang detector"
        )


def test_only_the_two_vitest_steps_carry_the_timeout_flag():
    # The flag is a load mitigation for the two vitest steps; no other
    # gate's shape changes with it.
    carrying = {label for label, args in STEPS if _timeout_flags(args)}
    assert carrying == {"vitest-dashboard", "vitest-ui"}, (
        f"steps carrying --testTimeout: {sorted(carrying)}; expected exactly "
        "the two vitest steps and no others"
    )
    for label, args in STEPS:
        assert args[0] in {"ci", "run", "exec"}, f"step {label!r} lost its npm verb"
        if label.startswith("vitest"):
            # tests/test_verify.py reduces a command to its first two
            # non-flag tokens — these must stay [run, test] or the wrapper
            # parity check breaks.
            assert args[:2] == ["run", "test"], (
                f"step {label!r} starts {args[:2]}; must stay ['run', 'test']"
            )


def test_forwarded_timeout_sits_after_the_npm_separator(monkeypatch):
    # End-to-end invocation shape: with npm resolved to a fake path and
    # subprocess.run recorded, the vitest invocations must carry the flag
    # BEHIND the bare `--` — before it npm would consume the flag itself
    # and vitest would keep its 5000 ms default.
    calls: list[list[str]] = []

    def _record(argv, *a, **k):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "unused")  # keep main() hermetic
    monkeypatch.setattr("scripts.check_ui.shutil.which", lambda _: r"C:\fake\npm.cmd")
    monkeypatch.setattr("scripts.check_ui.subprocess.run", _record)

    assert main([]) == 0
    assert len(calls) == len(STEPS), "expected one recorded invocation per step"
    for (label, _args), argv in zip(STEPS, calls, strict=True):
        if not label.startswith("vitest"):
            continue
        assert argv[:1] == [r"C:\fake\npm.cmd"], "steps run through the resolved npm path"
        flags = _timeout_flags(argv)
        assert flags, (
            f"the recorded {label!r} invocation forwards no --testTimeout=<ms>; "
            f"vitest never sees the wrapper's timeout: {argv}"
        )
        assert "--" in argv, (
            f"the recorded {label!r} invocation has no bare -- separator for "
            f"npm to forward through: {argv}"
        )
        assert argv.index(flags[0]) > argv.index("--"), (
            f"step {label!r} passes {flags[0]!r} before the bare -- separator; "
            "npm consumes it there and vitest keeps its 5000 ms default"
        )
