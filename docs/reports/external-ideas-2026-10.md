# External ideas — October 2026 increment

| | |
|---|---|
| Status | Input list — **not scope**. Nothing below is committed work until it gets a PRD line (same rule as the 2026-09 register). |
| Date | 2026-10-03 |
| Sources | 006 S-batch register proposals (B5, B6) — drafted by the exec run, adopted by the user for paste; full proposals live at [`../.workspace/tasks/2026-09-07-flaky-provider-import-test.md`](../.workspace/tasks/2026-09-07-flaky-provider-import-test.md) and [`../.workspace/tasks/2026-09-10-benchmark-lens-outcome-records.md`](../.workspace/tasks/2026-09-10-benchmark-lens-outcome-records.md) |
| Method | Same as the 2026-09 register: each candidate names where it lands, anchors cited. Section ids continue the September file's numbering (C9, D4). |
| Verification | Both rows' anchors re-read against main `c83dc2b` on 2026-10-03 (the 006 verification pass read the cited tests and functions directly). |

## C. Verification and quality

| # | Candidate | Source | Status | Where it lands |
|---|---|---|---|---|
| C9 | **The provider-import budget is wall-clock, so ambient load reads as a regression** — `test_provider_imports_fast_enough_for_the_promptfoo_worker` (`tests/test_promptfoo_provider.py`) wraps a spawned `python -c "import sdlc.eval.promptfoo.provider"` in `time.monotonic()` and asserts `elapsed < 8.0` over the whole subprocess — interpreter start, disk and imports — not the import cost itself. On a multi-agent workstation the budget is periodically blown by concurrent load, not by a heavy import: it fired the C3 plan's Step-7 stop-guard on 2026-09-06 even though causal isolation proved the diff innocent, and it will trip every future executor's guard the same way. Remedy, either half: measure import cost directly (import-time instrumentation, not subprocess wall-clock), or mark the test load-sensitive / move it to the slow tier. | *found in review* | Gap verified (2026-09-06 C3 isolation; premise re-read on 006 base `817f819`) | `tests/test_promptfoo_provider.py::test_provider_imports_fast_enough_for_the_promptfoo_worker`; the structural companion `test_provider_does_not_import_agents_roles` already pins the direct cause and stays as-is |

## D. Learning and the quality cycle

| # | Candidate | Source | Status | Where it lands |
|---|---|---|---|---|
| D4 | **Lens-outcome records in the benchmark corpus — a lens that did not run still leaves no row** — C8 shipped `LensOutcome` / `LensPresence` and the pure classifier `classify_lens` (`src/sdlc/stages/review/lenses.py`), and `TaskResult.lens_outcomes` is populated on both code-step return sites, but the benchmark corpus is unchanged: the reviewer record is emitted only when the lens actually ran (`step`'s record in `src/sdlc/stages/review/step.py`, guarded on a non-None report) and the adversary record only when `run_adversary` runs (same file) — flag off or agent missing means silence, so "ran and approved" and "never ran" stay indistinguishable to every downstream analysis. `render_agreement_matrix_html` (`src/sdlc/benchmarks/agreement_matrix.py`) already carries the symptom as its "No adversary records" empty state. Candidate: emit `LensOutcome`-derived benchmark records for **both** lenses — the reviewer's primary and the adversary backstop — with the presence state included (`PRESENT` / `DECLARED_ABSENT` / `UNDECLARED_ABSENT` / `NOT_REACHED`), so the corpus records absence as a fact instead of silence. Both lenses, not just the adversary the original question described (2026-09-10 gate, reviewer note P2). | *found in audit* (C8 residual, split at the 2026-09-10 user gate) | Extends (C8 shipped the mechanism; the corpus half is the gap) | `step` and `run_adversary` in `src/sdlc/stages/review/step.py`; `LensOutcome` / `LensPresence` / `classify_lens` in `src/sdlc/stages/review/lenses.py`; the empty state to retire in `render_agreement_matrix_html` (`src/sdlc/benchmarks/agreement_matrix.py`) |
