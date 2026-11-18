# 026 triage — every 025 failure and fix loop, classified (FR-020/FR-023)

Rows: the 5 scored case failures (runs 1–5; the smoke and the
operator-stopped run 6 are not failures) plus the 13 fix loops the
records carry. Sources, all read-only on the 025 root:
`fleet-report.md`, `.specify/specs/025-sc2-instrument-fleet-runs/preflight.md`
(the per-run sections), `benchmarks/bench-*/<cell>.jsonl` (records) and
`pipeline/bench-*/<uuid>/events.jsonl` (per-attempt stage outcomes,
`fix_attempt` events, gate decisions). Per-task session transcripts
were not retained in-root for any run (lice#6 and readtime#1 have no
events file either); where a row would want one, the record and event
lines are the evidence.

Loop reconciliation: the records carry exactly 13 (run, task) loop
groups with `fix_attempts > 0` — cat-cafe 2, geotext 2, lice run-2 4,
lice run-6 4, readtime run-5 1 — matching the report's total 13 and
"resolved 5" (cat-cafe T7, T8; lice-2 T-006, T-007; readtime-5 T-02).
The report's per-case split (readtime 4 / lice 5 / geotext 2 /
cat-cafe 2) groups runs coarser than (run, task); the records are the
row-level authority, and the table below follows them.

No 025 loop was lint-driven — per-task lint did not exist in 025;
`lint_clean` struck only at merge. SC-3-lint is therefore n/a (0 loops)
on the 025 baseline by construction (legacy `failure is None` loops
count non-lint), which is exactly the before-half of this round's
T013–T016 change.

## A. The five scored failures

| # | Run (bench) | Task | Failing check(s) | Class | Evidence | Remedy |
|---|---|---|---|---|---|---|
| F1 | readtime `1794957781-bccb20` | architecture (no code task) | architect activity death after `run_code` exhausted 3 retries on the model's own bad code (`TypeError: unsupported operand for +: 'Result' and 'Result'`), `UnexpectedModelBehavior` uncaught | **agent-tool defect** | 025 preflight "Scored run 1"; cell record `child_result="ChildWorkflowError: Child Workflow execution failed"`, `last_stage=clarify`; R6's library chain | **fixed by T022** (narrow degrade to a gap brief) |
| F2 | lice `1794958404-f74c98` | whole run | merge: `lint_clean`, `review_severity`, `traceability`, `plan_drift`; 5/7 QA | **case difficulty** (multiple substantive defects the checks correctly caught) with a `lint_clean` component that was a feedback gap | report runs table; `benchmarks/bench-…f74c98/*.jsonl` merge records | lint component **fixed by T013–T016**; the rest is the case |
| F3 | geotext `1794967369-ea94f8` | whole run | merge: `lint_clean`, `review_severity`, `traceability`; 7/9 QA | **case difficulty** (same shape as F2) | report; geotext records | lint component **fixed by T013–T016** |
| F4 | cat-cafe `1794967369-e94f43` | whole run | merge: `lint_clean` ONLY; 11/11 tasks QA-passed; oracle 0.861 | **harness defect** — the checks were right and the code was 22 findings dirty (T018 read: 22→4 under autofix alone), but the pipeline taught the dev nothing about lint until merge: the feedback loop did not exist | report; T018's read of the archived integration branch; cat-cafe records | **fixed by T013–T016** (autofix floor + per-task scoped lint in the loop) |
| F5 | readtime `1794980735-948597` | whole run | deploy PASS, merge `revise`, 9/9 QA — oracle graded 0.250 | **case difficulty** (the delivered work passed every gate and still missed the oracle's bar) | report; readtime-5 records | none this round |

## B. The thirteen fix loops

Failing checks per attempt from each run's `events.jsonl` (`stage_ended`
outcomes between `fix_attempt` events); attempt counts from the code
records. "tests" = the qa stage's tests verdict; "review" = blocking
findings.

| # | Run | Task | Attempts | Failing check(s) | Resolved | Class | Evidence |
|---|---|---|---|---|---|---|---|
| L1 | cat-cafe-4 | T7 | 2 | tests + review | yes | case difficulty | events.jsonl seq (T7 attempt-2 prior: `review:fail code:fail qa:fail`) |
| L2 | cat-cafe-4 | T8 | 2 | tests + review | yes | case difficulty | events.jsonl (T8 attempt-2 prior: same triple) |
| L3 | geotext-3 | T-02 | 3 | tests + review | no | case difficulty | events.jsonl (both retries preceded by the triple) |
| L4 | geotext-3 | T-09 | 3 | tests + review | no | case difficulty | events.jsonl (same) |
| L5 | lice-2 | T-002 | 3 | tests + review | no (attendant approve-to-proceed at gate `task:T-002`) | case difficulty | events.jsonl seq 67–69 (gate_decided, human, "procedural approve") |
| L6 | lice-2 | T-004 | 3 | tests + review | no (same attendant pattern) | case difficulty | events.jsonl seq 100+ (`task:T-004` gate) |
| L7 | lice-2 | T-006 | 3 | tests + review | yes | case difficulty | events.jsonl |
| L8 | lice-2 | T-007 | 2 | tests (review passed) | yes | case difficulty | events.jsonl (attempt-2 prior: `review:pass code:fail qa:fail`) |
| L9 | lice-6 | T-02 | 3 | tests (records only — no events retained) | no (run operator-stopped) | case difficulty | `benchmarks/bench-…e87339/*.jsonl` code records |
| L10 | lice-6 | T-03 | 3 | tests (records only) | no (run stopped) | case difficulty | records |
| L11 | lice-6 | T-04 | 3 | tests (records only) | no (run stopped) | case difficulty | records |
| L12 | lice-6 | T-06 | 2 | tests (records only) | no (run stopped mid-escalation) | case difficulty | records; report's run-6 row (stopped at $0.9613 past the $0.70 line) |
| L13 | readtime-5 | T-02 | 3 | tests (review passed both failed attempts) | yes | case difficulty | events.jsonl (`review:pass code:fail qa:fail` twice) |

No loop classed harness or agent-tool defect — FR-023's remedy column is
therefore empty for section B: the loops are the agent genuinely
struggling with the cases (first-pass rates in the report: cat-cafe
9/11, geotext 7/9, lice-2 3/7, readtime-5 8/9), not the harness
misfiring. The one 025 behavior that MADE loops worse — the agent never
seeing lint until merge — never appears inside a loop (it appears as
F4's merge block), which is the gap T013–T016 closes for 026.
