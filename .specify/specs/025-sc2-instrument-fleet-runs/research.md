# Research — round 025

**R1 `raised_at` needs no workflow change.** `GATE_AWAITED` is emitted by `_on_gate_awaited` (`S/workflows/run_host.py:50-51`) in the same workflow task as `gate_pending(... opened_at=workflow.now())` (`S/workflows/gates.py:237-244`); `RunEvent.at` is `workflow.now()` (`S/workflows/report_host.py:42`). OFF-policy and auto-approved SOFT gates never reach that branch (`gates.py:231-236`), and are never human. Decision: derive in the summary builder. Alternative rejected: a new event field (changes the event payload for no gain).

**R2 Merge gate double-emit.** `merge/step.py:569` emits a bare then enriched `GATE_DECIDED` on the same key; `_enrich` (`summary.py:74-87`) merges, and later always-present fields win, so `decided_by` can become a reviewer name (`merge/step.py:569-577`). Decision: human = not in {policy, timeout}. Consequence: SC-6 (`sc_rollup.py:179`) may undercount; logged as a backlog card, not changed.

**R3 Clarification batches.** ASKED events are emitted in one loop (`question_host.py:60-69`), one `wait_condition` covers the batch (`:79-82`), ANSWERED events follow in one loop (`:92-106`). Per-question answer times are not recorded (`:36-41`), and we do not add them. Decision: one interaction per `(stage, asked_at)` batch.

**R4 Judge and Anthropic spend.** `_build_judge_input` returns `None` without a rubric (`S/benchmarks/judge.py:89-91`), so `rubrics: {}` cases (readtime, lice, geotext) make no workflow judge calls. `check_smoke` requires rubric scores on `clarify` and `architecture` (`smoke.py:78-88`) so the stamp cannot be judge-free. `dispatch_smoke` calls `_run_matrix` with no `arm` (`cli.py`), so both todo-api arms run, and `oracle_all_pass` spans all cells. Adversary: `adversarial_review_enabled` defaults False (`core/models.py:465`) and `agents/adversary/agent.yaml:13` is Anthropic.

**R5 No benchmark run budget.** `PipelineConfig.run_budget_usd` defaults 0.0 (`core/models.py:484`); `CaseSpec` has no budget field; `_cell_config` does not set one. A budget gate would also be a human gate. Decision: no code; manual cancel at the announced per-run limit.

**R6 Floors.** `MIN_RUNS = MIN_OBSERVATIONS = 5` (`runs.py:38`). SC-2's n is shipped runs only (`deployed:`/`merged-not-deployed:`), narrower than SC-1's `REACHED_PREFIXES` (adds `rejected:merge`). SC-3 floors on loops.

**R7 Host state observed.** `/srv/scratch-repos` absent; no benchmark records or `SDLC_RUNS_ROOT` on this host; the shared tree is not clean-by-default (other agents work in it), and `_run_matrix` refuses a dirty tree for corpus cases. Decision: dedicated checkout of the fleet commit. **Unverified, pre-flight item:** whether the compose worker image runs the checkout's code or its own baked copy, since provenance is stamped from the CLI's tree.

**R8 Unverified, to be settled in T011:** whether `RunSummary`/`GateOutcomeSummary` forbid extras or any fixture dump pins serialized summaries (backlog `2026-09-24-dashboard-fixture-dump-drift`).

**R9 Rider.** ROADMAP's SC rows (`ROADMAP.md:477-488`) already cite `src/sdlc/benchmarks/sc_rollup.py`; stale paths remain only in historical `docs/superpowers/` files, left as written.
