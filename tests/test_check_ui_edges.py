"""Edge/pin companions to tests/test_check_ui.py for the wrapper timeout
(sbatch-2026-10-19 T2; task .workspace/tasks/2026-10-03-check-ui-wrapper-timeout-flake.md).

qa-happy's T2 section in tests/test_check_ui.py pins the flag's presence,
its value band and its only-vitest scope, end-to-end through a recorded
fake npm. This file is the chaos/edge margin around the same change:

- parse safety: exactly ONE bare ``--`` separator, the flag behind it, and
  the value a decimal integer in ``^--testTimeout=[0-9]+$`` form — an arg
  npm would swallow (flag before the separator, separator missing, or a
  malformed token) silently reverts vitest to the 5000 ms default, which is
  the original flake;
- parity: the reduction tests/test_verify.py applies to CI commands (first
  two non-flag tokens) must still see ``run test`` in each vitest argv —
  appended dash-prefixed args must not be able to move it;
- control flow: a failing step still names its label in the UI FAILED
  summary, still exits 1, and the loop still runs EVERY step (no early
  exit); an all-green run still prints the gate-passes line;
- value sanity: the timeout must actually raise the budget above the
  5000 ms default it replaces (else the change is a no-op) and stay within
  a hang-detector band, not a hang allowance.

Flag-presence tests are RED on main (the argv carries no flag yet); the
rest are PINs, labelled below.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from scripts.check_ui import STEPS, main

# The two steps the timeout contract is written against (same guard as
# qa-happy's file: if the step set moves, both files must say so).
_VITEST = tuple((label, args) for label, args in STEPS if label.startswith("vitest"))
_TIMEOUT_TOKEN = re.compile(r"^--testTimeout=[0-9]+$")


def _timeout_tokens(args: list[str]) -> list[str]:
    return [t for t in args if t.startswith("--testTimeout=")]


def test_vitest_timeout_flag_is_well_formed_and_behind_exactly_one_separator():
    """RED on main: each vitest step must forward exactly one
    ``--testTimeout=<decimal ms>`` behind exactly one bare ``--`` — npm
    eats anything before the separator, and a malformed token is not a
    vitest CLI option."""
    assert {label for label, _ in _VITEST} == {"vitest-dashboard", "vitest-ui"}, (
        f"expected exactly the two vitest steps, found {[name for name, _ in _VITEST]}"
    )
    for label, args in _VITEST:
        seps = [i for i, token in enumerate(args) if token == "--"]
        assert len(seps) == 1, (
            f"step {label!r} carries {len(seps)} bare '--' separators; npm "
            f"forwards through exactly one — a missing separator means npm "
            f"swallows the flag and vitest keeps its 5000 ms default: {args}"
        )
        flags = _timeout_tokens(args)
        assert len(flags) == 1, (
            f"step {label!r} carries {flags}; expected exactly one --testTimeout=<ms> token"
        )
        assert _TIMEOUT_TOKEN.fullmatch(flags[0]), (
            f"step {label!r} token {flags[0]!r} fails ^--testTimeout=[0-9]+$; "
            f"a two-token or non-decimal form does not reach vitest as a "
            f"CLI option"
        )
        assert args.index(flags[0]) > seps[0], (
            f"step {label!r} passes the timeout before the bare '--'; npm "
            f"consumes it there and vitest keeps its 5000 ms default — the "
            f"flake returns silently"
        )


def _parity_key(argv: list[str]) -> list[str]:
    """tests/test_verify.py's ``_gate_key`` reduction, replicated locally
    on a token list (the original reduces shell strings): drop
    dash-prefixed and launcher tokens (python, npm — 018 05aafb8e made
    STEPS entries full commands, so the npm launcher rides in argv),
    keep the first two."""
    parts = [t for t in argv if not t.startswith("-") and t not in ("python", "python3", "npm")]
    return parts[:2]


def test_vitest_argv_still_reduces_to_run_test_under_the_parity_key():
    """PIN (green now, must stay green): the parity reducer drops every
    dash-prefixed token, so the appended ``--`` and ``--testTimeout=...``
    cannot move what it sees — each vitest argv must still reduce to
    ``run test``, the npm semantics the wrapper's parity rests on."""
    for label, args in _VITEST:
        assert _parity_key(args) == ["run", "test"], (
            f"step {label!r} reduces to {_parity_key(args)!r}; appended "
            f"timeout args must not disturb the npm run-test semantics "
            f"(tests/test_verify.py reduction): {args}"
        )


def _fake_npm(monkeypatch, calls: list[list[str]], fail_when) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "unused")  # keep main() hermetic
    monkeypatch.setattr("scripts.check_ui.shutil.which", lambda _: r"C:\fake\npm.cmd")

    def _run(argv, *a, **k):
        calls.append(list(argv))
        return SimpleNamespace(returncode=1 if fail_when(list(argv)) else 0)

    monkeypatch.setattr("scripts.check_ui.subprocess.run", _run)


def test_step_failure_names_the_label_and_the_loop_runs_every_step(monkeypatch, capsys):
    """PIN (control flow is untouched on main; adding argv must not change
    it): a failing vitest step exits 1, the UI FAILED summary names the
    step's label, and every later step still runs — a gate that stops at
    the first failure hides how much of the UI is actually broken."""
    calls: list[list[str]] = []

    def _is_vitest_dashboard(argv: list[str]) -> bool:
        # Matches pre- and post-fix argv shapes alike: the vitest-dashboard
        # test invocation is `run test ... --workspace sdlc-dashboard`.
        return argv[1:3] == ["run", "test"] and "sdlc-dashboard" in argv

    _fake_npm(monkeypatch, calls, _is_vitest_dashboard)

    assert main([]) == 1
    err = capsys.readouterr().err
    assert "UI FAILED" in err and "vitest-dashboard" in err, (
        f"the failure summary must name the failed step label; stderr was: {err!r}"
    )
    assert len(calls) == len(STEPS), (
        f"a step failure must not short-circuit the loop: {len(calls)} of {len(STEPS)} steps ran"
    )


def test_all_steps_passing_returns_zero_and_prints_the_gate_line(monkeypatch, capsys):
    """PIN: the all-green shape is unchanged — exit 0 and the
    'ui gate passes' line verify.py's callers grep for."""
    calls: list[list[str]] = []
    _fake_npm(monkeypatch, calls, lambda argv: False)

    assert main([]) == 0
    assert "ui gate passes" in capsys.readouterr().out
    assert len(calls) == len(STEPS)


def test_timeout_value_raises_the_budget_without_retiring_the_hang_detector():
    """RED on main (no flag to read yet): the value must beat vitest's
    5000 ms default — a value at or below it makes the whole change a
    no-op while looking like a fix — and stay <= 300000 ms: the worst
    observed jsdom env setup under wrapper + container load was ~30 s
    (006 SG-2 matrix, .workspace/tmp/executor-006-SG2-report.md), so 10x
    that headroom keeps the flag a hang detector, not a hang allowance."""
    for label, args in _VITEST:
        flags = _timeout_tokens(args)
        assert flags, (
            f"step {label!r} forwards no --testTimeout=<ms>; the vitest "
            f"default 5000 ms stays live and times jsdom-heavy files out "
            f"under load (006 SG-2 fire)"
        )
        value = int(flags[0].split("=", 1)[1])
        assert value > 5_000, (
            f"step {label!r} forwards --testTimeout={value}: at or below "
            f"vitest's own 5000 ms default the flag changes nothing"
        )
        assert value <= 300_000, (
            f"step {label!r} forwards --testTimeout={value}: above 300000 ms "
            f"a wedged test parks the whole gate for minutes per test — "
            f"the worst observed env setup was ~30 s, not ~300 s"
        )
