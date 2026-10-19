# FR-041: pin the opencode session parser on the captured benchmark stream

Short spec for a single M-sized crew run (benchmark improvement plan task
2.8, round 016 follow-up #1). No full SDD round: the parser already exists
(`OpenCodeHarness.normalise_session`, tool_use support landed in 014,
c3f6319c) and the end-to-end wiring is live (013: capture → digest →
WasteBag; verified on run 1792335476 where code records carry populated
bags). What is missing is the proof: the REAL captured stream from the
passing round-016 R0 smoke is committed as a fixture but pinned by no test,
and the parser's behaviour on the full real event vocabulary (not the
hand-written 014 stream) is unrecorded.

## Fixture

`tests/fixtures/opencode/bench-todo-api-greenfield-1792335476-T-001-a1.jsonl`
— 24 lines, opencode 1.18.35 `--format json`, scrubbed (paths, user value
`"start"`→`"<user>"`, session ids `ses_…`→`"<session-id>"`). Orchestrator
probe (verify, do not trust): normalise+digest yields tool_calls=7,
files_written=3, model_turns=5, failed_commands=0, file_reads=0,
capture_rev=1, input_tokens=3652, output_tokens=875, cost_usd=0.0.

## Raw-capture vocabulary (from runs/ops/raw-stream/*, git-ignored, while
they last)

- `step_start` / `step_finish` (part.type `step-start`/`step-finish`,
  part.reason "tool-calls"|"stop", part.tokens{input,output,reasoning,cache},
  part.cost) — counted.
- `tool_use` (part.tool bash|read|write|edit|glob|todowrite, state.status
  "completed", state.metadata.exit for bash) — counted; unmapped tools fall
  to the generic tool_call bucket.
- `text` (part.text) — model_turn.
- `error` (TOP-LEVEL `error` object: name + data.message + data.ref; 30
  occurrences, all fatal "Unexpected server error" from the lost R0
  attempt-4 batch, each the only event of its stream) — currently dropped
  silently.

## Requirements

- FR-1: The captured fixture is pinned by unit tests: digest counters, the
  WasteBag projection (from_digest + waste_measured), token/cost summation
  (cost 0.0 is a MEASURED zero — saw_cost semantics — not None), and
  robustness against the scrubbed fields.
- FR-2: The parser's treatment of `type: error` events is decided, recorded
  in the parser's docstring, and pinned by a test built from the real shape
  (top-level error object, no part). Ruling (orchestrator, pre-approved):
  an error event advances no work and is NOT waste — keep dropping it from
  events, but it must not crash the parser nor be reported as parsed text.
- FR-3: No parser behaviour change is expected. If the executor finds a
  real gap (a counted event mis-parsed, a crash), that is a finding to
  report with a failing test FIRST — fix only what a RED test proves broken.
- FR-4: BENCHMARK.md §4.3 gains a short note that waste counters are
  populated end-to-end and that the pinned fixture is the provenance
  (round-016 R0 capture, todo-api T-001 attempt 1).

## Stop-guards (binding; clearance only from the orchestrator)

- SG-1: never edit the fixture. It is a capture; regeneration needs the
  user's raw-stream siblings and a scrub pass.
- SG-2: never edit golden replay files or re-record histories.
- SG-3: allowed paths: `tests/` (new/changed tests),
  `src/sdlc/harness/opencode.py` (docstring/comment or a RED-proven fix
  only), `docs/BENCHMARK.md` (§4.3 note), `.workspace/tasks/` (findings).
  Anything else → stop and report.
- SG-4: gates before every commit: fast tier pytest, `ruff check .`,
  `ruff format --check .`, mypy, `python scripts/check_file_size.py`; the
  replay tier is `pytest -m temporal tests/replay` (a full-dir run without
  `-m temporal` is NOT the gate).
- SG-5: all work on branch `fr041-waste-fixture`; no commits to main.
