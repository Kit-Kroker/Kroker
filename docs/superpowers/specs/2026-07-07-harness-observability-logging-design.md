# Harness observability logging

## Problem

`src/sdlc/harness/adapters.py` runs `claude` and `opencode` as subprocesses inside
`CodingHarness.run()`. Today this is a black box:

- `stderr=asyncio.subprocess.PIPE` is set but the pipe is never read — nothing surfaces
  child stderr, and a child that writes enough of it can deadlock on a full OS pipe
  buffer.
- `_pump()` buffers all of stdout silently until the process exits; `parse()` only
  looks at it after the fact. While a task is running there is no way to tell "it's
  still working" from "it's stalled" — no output either way.
- Parse failures fail silently: `OpenCodeHarness.parse` skips lines that don't
  `json.loads` with a bare `continue`, and falls back to raw stdout if `parsed_any`
  stays `False`; `ClaudeCodeHarness.parse` has the same silent fallback on
  `JSONDecodeError`/`IndexError`. If either harness's output format changes, this
  fails invisibly.

Goal: make harness runs diagnosable (why did this run fail / hang) and give enough
structured signal per run (duration, tokens, cost, exit code) to reason about
cost/performance over time — without building new persistence infrastructure.

## Scope

`src/sdlc/harness/adapters.py` only, covering both `ClaudeCodeHarness` and
`OpenCodeHarness` via the shared `CodingHarness.run()` and each adapter's `parse()`.

Out of scope:
- No new storage (no jsonl/db). Structured log lines only, consistent with this
  codebase's existing `logging.getLogger(__name__)` convention (see
  `src/sdlc/benchmarks/drift.py`). Whatever handler the Temporal worker process
  already has is the sink — Python's logging "handler of last resort" writes
  WARNING+ to stderr even with zero config, so failures are visible out of the box.
- No changes to `activities.py`, `models.py`, or worker logging configuration.
- No tool-call-level hooks. Claude Code supports `PreToolUse`/`PostToolUse` hooks;
  opencode supports plugin hooks (`tool.execute.before`/`tool.execute.after`), but
  `OpenCodeHarness.build_cmd` deliberately runs with `--pure` to disable all plugins
  (see the existing comment at adapters.py:183-192 — needed to stop the user's
  globally-installed superpowers plugin from auto-activating brainstorming and
  stalling headless runs). Wiring a plugin-based hook would require relaxing
  `--pure`, which is a separate, riskier change not undertaken here.
- No change to Claude Code's output mode. `claude -p ... --output-format json`
  emits a single final payload, not an event stream, so there is no intermediate
  data to log live for that harness. Switching it to `--output-format stream-json`
  for parity is a possible follow-up, not part of this design.

## Design

### 1. Fix the dead stderr pipe

Add a `_pump_stderr()` coroutine parallel to the existing `_pump()`, gathered
together in `run()` so both stdout and stderr drain concurrently. This removes the
deadlock risk (a child that writes enough stderr to fill the pipe buffer would
otherwise block forever with stdout still being read). Cap the collected buffer at
`SUMMARY_MAX` (4000 chars) — not for correctness, just to bound memory on a runaway
process.

### 2. Live event-stream logging

`_pump()` currently appends each stdout chunk to a list and returns the joined
result only once the process exits. Change it to also log as chunks/lines arrive,
at the same point that already calls `heartbeat()`:

- For opencode's `--format json` stream (one JSON object per line): log `step_start`
  and `step_finish` events at INFO (session id, and for `step_finish`, tokens/cost
  if present), and `text` events at DEBUG (length only, not content — avoid dumping
  arbitrary repo/model output into logs).
- Lines that don't parse as JSON at this stage are left to the existing parse-time
  handling (piece 4) — the live pump does a best-effort per-line `json.loads` purely
  for logging and must not raise or otherwise change control flow if a line doesn't
  parse.

This is a side channel for observability only. `parse()` remains the single source
of truth for the returned `HarnessRunResult` — it still walks the full buffered
stdout after the process exits, unchanged in behavior.

Effect: tailing worker output while a task runs shows a live trail (`step_start` →
several `text` chunks → `step_finish` with tokens/cost) instead of nothing until
the process exits — a long gap between lines is now visible as a stall, whereas
today a stalled run and a quietly-working run look identical from outside.

### 3. Lifecycle logging in `run()`

- DEBUG at start: harness kind, model, session_id, cwd. Never the prompt body
  (may be large, may contain repo content).
- WARNING on `asyncio.TimeoutError`, including cmd and cwd, before re-raising —
  today a killed/timed-out run leaves no trace of what was running.
- INFO one structured summary line after `parse()` returns, before `run()` returns:
  `harness=%s exit_code=%s session_id=%s duration_s=%.1f input_tokens=%s output_tokens=%s cost_usd=%s`.
  Duration is measured via `time.monotonic()` bracketing the subprocess call inside
  `run()`; it is logged only, not added to `HarnessRunResult` (no model change).
- WARNING with the captured stderr tail (from piece 1) whenever `exit_code != 0` or
  stderr is non-empty — today this data is captured nowhere.

### 4. Parse-failure logging in both adapters

- `OpenCodeHarness.parse`: DEBUG-log each line that fails `json.loads` (currently a
  bare `continue`). WARNING if the loop finishes with `parsed_any == False` (every
  line failed to parse — signals the CLI's output format changed or broke, distinct
  from a normal empty-output case).
- `ClaudeCodeHarness.parse`: WARNING in the existing
  `except (json.JSONDecodeError, IndexError)` branch, which today silently falls
  back to treating raw stdout as the summary.

## Testing

Unit tests for `src/sdlc/harness/adapters.py` (extending the existing test file for
this module, if one exists, or a new `tests/test_harness_adapters.py`) covering:

- `_pump_stderr` actually drains stderr and the combined stdout+stderr gather
  doesn't deadlock on a subprocess that writes a large amount of stderr.
- A `caplog`-based assertion that the INFO summary line is emitted with the
  expected fields after a successful parse.
- A `caplog`-based assertion that the WARNING stderr-tail line is emitted when
  exit_code != 0.
- `OpenCodeHarness.parse` logs at DEBUG for a malformed line and at WARNING when no
  line in the stream parses.
- `ClaudeCodeHarness.parse` logs at WARNING on the JSON-decode fallback path.
- Live pump logging: feed `_pump()` a sequence of `step_start`/`text`/`step_finish`
  lines (via a fake subprocess or by testing the pump logic directly) and assert
  the corresponding log lines are emitted incrementally, not only after exit.

No changes to `tests/test_harness_parse.py`'s existing coverage of `parse()`
correctness are needed — this design only adds logging around/inside the existing
logic, not new parsing behavior.
