# Bug Fix: Replay gate-timer pin — decision signals held until the remind timer is on record

- **Slug**: golden-tick-race
- **Fixed**: 2026-10-18
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Pinned the replay scenario drivers (`tests/replay/scenarios.py`) so a
gate-decision signal (and the first clarify answer) is sent only after
`fetch_history()` shows the pending gate's remind `TIMER_STARTED` —
closing the signal-beats-timer race whose losing side leaves no timer
event at all (core elides a one-task StartTimer+CancelTimer pair) and
drops a `timer` from the captured projection (the SG-3 golden flake).

## Changes

| File | Change | Notes |
|------|--------|-------|
| `tests/replay/scenarios.py` | modified | +64 lines: `GATE_TIMER_PIN_POLL_S`/`GATE_TIMER_PIN_TIMEOUT_S`, `_pending_remind_timer` (anchor = latest OPENED notify scheduling; qualifying = TIMER_STARTED after it with no later cancel/fire), bounded `_await_gate_timer_pin`; wired into `decide()` (notify anchor) and `answer_clarify()` (any-timer anchor) |
| `tests/replay/test_gate_timer_pin.py` | added (RED contract) | qa-happy; committed pre-fix RED at `942d92e9` |
| `tests/replay/test_gate_timer_pin_chaos.py` | added (RED contract) | qa-chaos; committed pre-fix RED at `942d92e9` (row 6 amended on lead review: stale pair carries TIMER_CANCELED — see commit message) |

No `src/` change; no golden or history file touched (`git status` clean
under `tests/replay/golden/` + `tests/replay/histories/`).

## Diff Highlights

```python
GATE_TIMER_PIN_POLL_S = 0.02
GATE_TIMER_PIN_TIMEOUT_S = 30.0


async def decide(handle, gate, round_, outcome, **kw):
    await wait_for(handle, f"awaiting:{gate}")
    await _await_gate_timer_pin(handle, gate, notify_anchor=True)
    await handle.signal(
        "submit_gate_decision",
        GateDecision(gate=gate, round=round_, outcome=outcome, decided_by="human", **kw),
    )
```

`_pending_remind_timer` walks the fetched events once: the anchor is the
latest `notify` `ACTIVITY_TASK_SCHEDULED` (every awaiting gate schedules
its OPENED notify in the same workflow task that sets `awaiting:<gate>`,
so the latest on record is the gate being decided); a `TIMER_STARTED`
qualifies when its event id exceeds the anchor and no later
`TIMER_CANCELED`/`TIMER_FIRED` resolves it — a previous gate's resolved
remind timer never qualifies, and a timer predating the gate's own
opening is invalidated when the anchor advances past it.

## Tests Added or Updated

- `tests/replay/test_gate_timer_pin.py::test_pin_constants_exist_at_the_pinned_values` — the two knobs exist at the contracted values.
- `tests/replay/test_gate_timer_pin.py::test_decide_waits_for_the_remind_timer_before_signalling` — D1: across a scripted race window the decision goes out only once a qualifying TIMER_STARTED is on record; payload/call shape unchanged (D3).
- `tests/replay/test_gate_timer_pin.py::test_signals_go_out_promptly_when_the_timer_is_already_up` — controls: the golden interleaving is not delayed (≤2 fetches).
- `tests/replay/test_gate_timer_pin.py::test_pin_wait_is_bounded_and_signals_nothing_on_expiry[decide|clarify]` — D2/A2: named AssertionError, zero signals on expiry.
- `tests/replay/test_gate_timer_pin.py::test_answer_clarify_pins_the_first_answer_on_a_started_timer` — A1: first answer waits for any TIMER_STARTED; all QUESTION_IDS answered with the exact production call shape.
- `tests/replay/test_gate_timer_pin.py::test_budget_arch_reject_capture_is_deterministic` — temporal tier: five consecutive sandboxed GraphWorkflow captures of budget_arch_reject each reproduce the committed golden projection and each other.
- `tests/replay/test_gate_timer_pin_chaos.py` (6 rows) — delayed-timer polling; withheld signal on expiry (decide + clarify); latest-notify anchoring against a stale resolved pair; payload integrity under pinning; stale-pair wait-out.

## Local Verification

Host has no runnable interpreter; everything ran in ephemeral containers
(`ghcr.io/kit-kroker/kroker-worker:latest`, primary checkout at `/app`,
`kroker-verify-venv` volume, `kroker_default` network), one pytest per
shell call:

- RED pre-fix (lead-verified): `pytest tests/replay/test_gate_timer_pin.py` → 5 failed / 1 control passed; `pytest tests/replay/test_gate_timer_pin_chaos.py` → 6 failed (re-verified after the row-6 amendment).
- Post-fix: both files → all passed (11 fast rows).
- `ruff check` + `ruff format --check` on the three touched files → clean; `scripts/check_file_size.py` → exit 0 (scenarios.py 970 lines).
- Scoped fast suite `pytest tests/replay tests/durability tests/research/test_research_durability_nested.py tests/graph_workflow tests/test_model_forwarding.py` (every module importing `tests.replay.scenarios`) → exit 0.
- `pytest -m temporal -k deterministic tests/replay/test_gate_timer_pin.py` → exit 0 (five pinned captures, golden-matching).
- Mechanism probe evidence: `.workspace/tmp/tickrace_probe2.py` (untracked diagnostics; 3/3 per variant).

The final empirical gate (five consecutive green `pytest -m temporal
tests/replay` runs in kroker-dev) executes under `/speckit.bug.test` and
is recorded in test.md.

## Deviations from Assessment

- The assessment sketched the pin as a TIMER_STARTED **count delta vs. an
  entry baseline**. Implementation anchors on event ids instead (latest
  notify scheduling; pending timer after it): a baseline count is racy
  at helper entry (the gate's whole open→notify→timer chain can complete
  before the entry fetch under load, which would dead-end the count-delta
  pin into its bounded error), and only the pending-timer rule also
  rejects a previous gate's resolved remind timer. Same contract, sounder
  mechanics; the RED contracts (written after the assessment, before the
  fix) already encode the event-id anchor shape.
- Chaos row 6 was amended at RED-review time (see commit `942d92e9`):
  the stale pair now carries TIMER_CANCELED, the only stale shape reality
  can produce. RED status preserved and re-verified.

## Follow-ups

- The 2026-10-02 card's second ask — un-hide the continue-on-error
  temporal step in CI so this class stops being invisible — is an
  orchestrator-level decision, recorded there.
- If a future scenario's decided gate legitimately schedules no remind
  timer, the pin fails loudly (named gate, anchor id); that scenario's
  driver would need an explicit opt-out with the reason on record.
