# Bug Verification: Replay golden tier — gate-timer pin holds across the full temporal tier

- **Slug**: golden-tick-race
- **Tested**: 2026-10-18
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The assessed symptom no longer reproduces: five consecutive full
`pytest -m temporal tests/replay` runs in the kroker-dev container
environment are green (rc=0 each, one pytest per shell call), where the
pre-fix flake made the same command a per-window coin flip. The
deterministic RED contracts failed pre-fix exactly as designed and pass
post-fix; no golden or history byte changed; no regression appeared in
the import-surface suite.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Pre-fix RED (symptom reproduces as failing tests) | `pytest tests/replay/test_gate_timer_pin.py` / `..._chaos.py` (containers, pre-fix tree `942d92e9`) | pass | 5/6 happy rows failed (control row green by design), 6/6 chaos rows failed — lead-verified, clean mechanism-naming assertion failures |
| Reproduction (post-fix): the brief's final gate | `pytest -m temporal tests/replay` ×5 consecutive, one per shell call | pass | rc=0 on all five runs (GATE-1..GATE-5, 2026-10-18) |
| Determinism contract | `pytest -m temporal -k deterministic tests/replay/test_gate_timer_pin.py` | pass | five consecutive sandboxed budget_arch_reject captures, each equal to the committed golden and to each other |
| New / updated tests post-fix | `pytest tests/replay/test_gate_timer_pin.py tests/replay/test_gate_timer_pin_chaos.py` | pass | 11 fast rows green (12th row is the temporal one above) |
| Regression suite (import surface of `tests.replay.scenarios`) | `pytest tests/replay tests/durability tests/research/test_research_durability_nested.py tests/graph_workflow tests/test_model_forwarding.py` | pass | exit 0, post-fix tree |
| Golden byte-identity | `git diff main --stat -- tests/replay/golden tests/replay/histories` + `git status` on those paths | pass | empty — nothing re-recorded; in-test count-freeze rows green within the gate |
| Lint / format / file size | `ruff check` (3 files), `ruff format --check`, `scripts/check_file_size.py` | pass | scenarios.py at 970/1000 lines |
| mypy | config scope is `files = ["src"]` | not-run (out of scope) | no `src/` file changed by this bug |

All container runs: ephemeral `ghcr.io/kit-kroker/kroker-worker:latest`
with the primary checkout bound at `/app`, volume `kroker-verify-venv`,
network `kroker_default`, `PYTHONDONTWRITEBYTECODE=1` (the compose
kroker-dev container itself currently hosts the 016 worktree at /app
and was left untouched per the orchestrator note).

## Output Excerpts

- Pre-fix RED (lead-verified): `AssertionError: golden-tick-race: the
  decision was recorded before any TIMER_STARTED followed the gate's
  OPENED notify -- the timer pair is then elided and the capture lands
  one 'timer' short (SG-3)`; chaos: `assert 0 >= 5` / `Failed: DID NOT
  RAISE AssertionError`.
- Final gate: `GATE-1 rc=0` … `GATE-5 rc=0` (pytest exit codes; `-q`
  output, count line not captured through the container stream filter —
  exit 0 is unambiguous for the full selection).

## Residual Risks

- The pin adds one bounded history poll per gate decision; under extreme
  load a legitimate remind timer could exceed 30 s and fail loudly
  (named gate + anchor id) rather than silently — acceptable per the
  orchestrator's constraint (1), and no such timeout occurred across
  the five gate runs plus the determinism row (≈100 pinned gate
  decisions exercised).
- A future scenario whose decided gate schedules no remind timer would
  need an explicit driver opt-out with the reason on record (none
  today; every recorded decided gate carries one).
- CI visibility of the temporal tier (continue-on-error) remains as the
  2026-10-02 card recorded it — an orchestrator-level decision, outside
  this bug.

## Recommendation

Close the bug — verified end-to-end: mechanism probe-proven, RED →
GREEN contracts in place, goldens untouched, and the brief's five-run
gate green on the primary checkout. Branch `bug/golden-tick-race`
(e175bafd → 942d92e9 → 38379785 → 32d6a238 + this report) is ready for
orchestrator integration.
