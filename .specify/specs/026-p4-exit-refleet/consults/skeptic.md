# Round 026 Skeptic Pressure-Test

**Target**: `.specify/specs/026-p4-exit-refleet/spec.md` (GATE 1 cleared: Q1-A, Q2-A, Q3-A)  
**Evidence checked**: `src/sdlc/` codebase, `PRD.md`, and `../kroker-fleet-runs-025/` (read-only)

---

## Findings (Ranked by Severity)

### 1. [CRITICAL] Part 0 H1, SC-A1, and the 025 `SC-2-all` baseline are factually wrong (4 scored summaries, not 5; `SC-2-all` is `n/a`, not `0.85 min`)
- **Claimed**:
  - `spec.md:19` (Part 0 H1): *"That covers 5 of the 6 scored runs plus the smoke."*
  - `spec.md:29,214`: *"SC-2-all 0.85 min (n=5)"* as the 025 baseline.
  - `spec.md:43,195` (User Story A1 / SC-A1): re-scoring 025 with smoke excluded (`FR-004`) yields `summary_runs = 5` and an `SC-2-all` row.
- **Evidence**:
  - In `../kroker-fleet-runs-025/pipeline/*/*/summary.json`, there are 6 `summary.json` files total: **4** scored runs (`cat-cafe` `1794967369-e94f43`, `geotext` `1794967369-ea94f8`, `lice` `1794958404-f74c98`, `readtime` `1794980735-948597`), **1** scored-fleet smoke (`todo-api-greenfield-1794953137-1ba84e`), and **1** orphaned Nov-16 pre-smoke (`todo-api-greenfield-1794852280-ff756a`) with no `benchmarks/` records. Runs 1 (`readtime-bccb20`) and 6 (`lice-e87339`) have no summary.
  - The `summary_runs = 5` and `SC-2-all (n=5)` numbers in Part 0 were obtained **only because the smoke run was counted in the 5**.
  - Once `FR-004` (`spec.md:107`) excludes smoke-role cases, 025 has `summary_runs = 4` (`< MIN_RUNS = 5` at `src/sdlc/benchmarks/sc_rollup.py:28,204`), so **`SC-2-all` on 025 renders `n/a` (`rate: None`), not `0.85 min`**.
- **Concrete Spec Amendment**:
  1. Update `spec.md:19` (H1) to state **4 of the 6 scored runs** plus the smoke have `summary.json` (plus 1 orphaned pre-smoke in `pipeline/`).
  2. Update `spec.md:29,214` (025 baseline) to record `SC-2-all: n/a (n=4 < MIN_RUNS=5)` (noting `0.85 min` only as the unexcluded `n=5` with-smoke figure, not the FR-004 baseline).
  3. Update `spec.md:43,195` (A1 test & SC-A1) to assert `summary_runs = 4`, `selection_runs = 6` (smoke excluded), 2 named unsummarized runs, and `SC-2-all` at `n=4` (`n/a`, with `sc2_extra` populated).

---

### 2. [HIGH] Q1-A ("configured gate" carve-out) has no anti-gaming guard in `RunSummary` or `sc_rollup.py`
- **Question (1)**: Is PRD-aligned SC-1 under `HARD` a goalpost move, is the carve-out honest, and what guard keeps it from being gamed?
- **Analysis & Evidence**:
  - `PRD.md:666-667` genuinely defines SC-1 as *"≥ 80% of runs reach the merge gate without human intervention beyond configured gates (no unplanned escalations)."* So aligning `sc_rollup.py:160-182` to `PRD.md` is contractually legitimate, **but** switching from `SOFT` (025) to `HARD` + PRD-aligned SC-1 **does** make SC-1 materially easier to pass than 025's read:
    1. Under `sc_rollup.py:36`, `REACHED_PREFIXES` includes `"rejected:merge"` — a run that fails `lint_clean` at merge still counts as an SC-1 **hit** if it had no `task:<id>` escalation.
    2. Under `HARD`, `auto_decision_for` (`src/sdlc/workflows/graph_nodes/gate.py:66`) is never called, and `MergeVerdict` (`src/sdlc/stages/merge/step.py:583`) is skipped. Meanwhile, the attendant answers every stage gate (`research`, `clarify`, `architecture`, `plan`, `merge`, `deploy`), meaning SC-1 no longer tests unattended gate calibration at all — it only tests "no pre-merge crash and no `task:<id>` / `tool_approval` escalation."
  - **The gaming hole**: `GateOutcomeSummary` (`src/sdlc/core/models.py:544-562`) only stores `gate: str` and `policy: str` (`"hard"` / `"soft"` / `"off"`). It does **not** record whether a gate came from `cfg.gates` vs `default_gate_policy`. Worse, `src/sdlc/benchmarks/workflow.py:163-164` sets **both** `cfg.gates` and `cfg.default_gate_policy = spec.gate_policy`, so `task:T-02` and `tool_approval` carry `policy="hard"` on the wire — identical to `architecture` or `plan`. Without an explicit allowlist in `sc_rollup.py`, any `task:*` or `tool_approval` gate could be misclassified as a "configured hard gate", or the attendant could send `REVISE` with guidance on `architecture`/`plan` to rescue a failing run while still counting it as an SC-1 hit.
- **Concrete Spec Amendment**:
  - Amend `FR-006` / `B.4` (`spec.md:109,152`) to hardcode a static allowlist in `src/sdlc/benchmarks/sc_rollup.py`:
    `CONFIGURED_STAGE_GATES = frozenset({"research", "clarify", "architecture", "plan", "merge", "deploy"})`.
  - Any gate outside `CONFIGURED_STAGE_GATES` (including `task:*`, `tool_approval`, `deploy_failed`, or `clarify` `ask_and_wait` human interventions) **must** count as an unplanned escalation regardless of its `policy` field.
  - Explicitly forbid attendant `REVISE` guidance on stage gates in `B.4` (attendant may only `APPROVE` planned gates; any `REVISE` disqualifies the run from SC-1 or must be disclosed as operator steering).

---

### 3. [HIGH] `HARD` in benchmark mode alters `merge` behavior (`MergeVerdict` and `merge` gate skipped on clean runs) and strips `TimeoutAction.HOLD`
- **Question (4)**: Does `HARD` in benchmark mode change anything else (timeouts, deploy, 24h auto-continue) that could make runs park or time out?
- **Evidence**:
  1. **`merge` gate and `MergeVerdict` are skipped on clean runs (`src/sdlc/stages/merge/step.py:530,583,679`)**:
     In `merge/step.py:583`, `MergeVerdict` + `ctx.gate("merge", ...)` only run when `policy == GatePolicy.SOFT`. When `gate_report.passed` is `True` (5d) and `policy == GatePolicy.HARD`, neither `5c` (`if not gate_report.passed`) nor `5d` (`if policy == GatePolicy.SOFT`) executes. The stage returns `"skipped:benchmark-run-has-no-remote"` (`merge/step.py:680`) **without opening `merge` gate or running `MergeVerdict`**. That silently eliminates `MergeVerdict` (which caught bad implementations in 025) and removes `merge` from SC-2's interaction count on clean runs.
  2. **No "24h soft auto-continue" exists**: `src/sdlc/workflows/gates.py:245-266` and `src/sdlc/core/models.py:69,431` use `gate_timeout_hours = 48` and `on_timeout = TimeoutAction.REJECT` by default. Moreover, `src/sdlc/benchmarks/workflow.py:163` (`{name: GateConfig(policy=spec.gate_policy) for name in cfg.gates}`) overwrites `merge`'s `TimeoutAction.HOLD` (`core/models.py:389`) with `TimeoutAction.REJECT`. If the attendant drops or misses any `HARD` gate (`research` at `research/step.py:382`, `deploy` at `deploy/step.py:165`, `tool_approval` at `code/step.py:635`, or `clarify` `ask_and_wait` at `clarify/step.py:314`), the run **parks for 48 hours** and then rejects/fails.
  3. **`clarify` `ask_and_wait` (`src/sdlc/stages/clarify/step.py:293-318`)**: Under `OFF`, `clarify` auto-fills `suggested_answer`. Under `HARD` (and `SOFT`), non-empty `open_questions` call `ctx.ask_and_wait(..., timeout_hours=cfg.gate_timeout_hours)` (48h wait) — which is a clarification wait, not a `ctx.gate`, so an attendant polling only pending gates will miss it and park the run for 48h.
- **Concrete Spec Amendment**:
  - Amend `B.1`/`B.4` (`spec.md:126,152`) to require:
    1. Attendant must handle **both** pending gates **and** pending `clarify` `ask_and_wait` requests (or `clarify` must be verified empty/handled), with an attendant watchdog timeout (< 48h, e.g. 30 min idle alert) so a missed wait never parks a run for 48h.
    2. Explicitly disclose in `B.4` and `FR-053` that under `HARD`, `merge/step.py:583` skips `MergeVerdict` (and skips `ctx.gate("merge")` on clean `DeterministicQualityGate` runs), so `026` clean-merge runs are not exercising `MergeVerdict` as `025` did.

---

### 4. [HIGH] Q2-A (per-task lint) creates a direct SC-1/SC-3 trade-off and risks `test-freeze` containment violations if `ruff --fix` touches test files
- **Question (2)**: Does per-task lint plausibly lower SC-3 and SC-1? Should SC-3 be reported with and without lint-triggered loops?
- **Analysis & Evidence**:
  - **Net effect on P4 exit**: Yes, Q2-A directly trades **merge-gate `lint_clean` conversion** against **per-task `SC-3` and `SC-1`**.
    - In 025, `cat-cafe` had 0 task escalations (an SC-1 hit under PRD-aligned SC-1!) and 11/11 QA pass, yet left 4 non-autofixable findings (2 `PERF102`, 1 `PLW1510`, 1 `TRY004`) plus 5 `RUF100` (`noqa`) violations (`spec.md:23`).
    - Under Q2-A, any task introducing those findings now fails its attempt and enters the 3-attempt fix loop. If `glm-5.3` fails to resolve a subtle rule within 3 attempts (e.g., writes another `noqa` -> `RUF100`, or breaks tests refactoring `TRY004`), it raises `task:<id>` — **simultaneously lowering SC-3 (unresolved loop) and disqualifying the run from SC-1 (unplanned escalation)**.
    - Conversely, if `glm-5.3` fixes easy lint findings on attempt 2, those become *new* resolved loops that inflate SC-3's numerator and denominator, masking whether test/review loops actually improved.
  - **Containment / test-freeze hazard (`src/sdlc/stages/code/step.py:683-700`)**: On repair attempts (`_is_repair_attempt`), `code/step.py` checks test-freeze containment. If `ruff check --fix .` (`FR-011`) runs across the entire worktree and modifies a frozen test file, it can trigger a false-positive test-freeze drift failure!
- **Concrete Spec Amendment**:
  - Amend `FR-053` / `SC-B2` (`spec.md:186,203`) to require reporting **three SC-3 rows** in the fleet report (using `FR-021`'s `failing_checks`): (a) SC-3 overall, (b) SC-3 for **non-lint** loops (comparable to 025's 0.385), and (c) SC-3 for **lint-triggered** loops.
  - Amend `FR-011` (`spec.md:111`) to scope `ruff --fix` away from frozen test paths on repair attempts (or run autofix only on files modified by the dev attempt outside frozen test globs).

---

### 5. [MEDIUM] `n=5` (4/5 = 0.80) has weak statistical power, and the `$13.95` ceiling + gate-only cost polling has a blind spot
- **Question (3)**: Is `n=5` with `4/5` meaningful, and is the `1.5×` ceiling derivation sound?
- **Analysis & Evidence**:
  - **`n=5`, `4/5 = 0.80`**: At `n=5`, a single run flip moves SC-1 from `0.80` (pass) to `0.60` (fail); the 95% exact binomial CI for 4/5 is `[0.284, 0.995]`. Given 025's case outcomes (`lice` 2/2 task-escalation cascades, `geotext` 1/1 with 2 task escalations, `readtime` 1/2 architecture crash), hitting 4/5 requires `lice` OR `geotext` to flip cleanly while `cat-cafe × 2` and `readtime` hold. `n=5` is literally `MIN_RUNS` (`sc_rollup.py:28`) — adequate as a smoke-plus-fleet sanity check, **not** strong statistical proof of ≥ 0.80 reliability.
  - **Ceiling & polling blind spot (`spec.md:175,177`)**:
    1. Verified against 025 records: per-run judge+stage `cost.usd` in 025 matches B.5 (`cat-cafe` $2.0025, `geotext` $1.2700, `lice` $0.9326, `readtime` $1.1531, `smoke` $1.9396), and QA/review per-attempt cost is `$0.0005–$0.0118` (so extra loops add little judge spend).
    2. **However**, `spec.md:177` states *"the attendant polls cost at each gate"*. Between `plan` and `merge`, **zero stage gates fire** unless `task:<id>` escalates. A run that burns past its 1.5× per-run stop during `code` will not be caught until `merge` (repeating 025 run 3).
    3. If optional run 6 (`$1.15–$1.73`) is triggered after an operator-stopped run (up to `$1.40–$3.00` already spent), the `$13.95` ceiling holds **only** if the remaining runs stay near `1.0×` (not `1.5×`).
- **Concrete Spec Amendment**:
  - Amend `B.5` (`spec.md:177`) so the attendant polls cumulative run cost **on a wall-clock interval (e.g., every 60s) or per-record**, not only at gates.
  - Clarify in `B.5` (`spec.md:175`) that optional run 6 is authorized **only if** projected remaining headroom (`$13.95 - cumulative_spend`) ≥ `$1.73` (1.5× `readtime`).

---

### 6. [LOW] Part 0 H4 & Assumptions misstate that 025 session transcripts may be pruned
- **Claimed**:
  - `spec.md:24` (H4): *"Their causes must come from retained session transcripts or Temporal histories, if those still exist."*
  - `spec.md:219` (Assumptions): *"025's per-run session transcripts or Temporal histories may have been pruned."*
- **Evidence**:
  - In `../kroker-fleet-runs-025/pipeline/`, six UUID run directories (`01a1e588-...`, `01a1eb8b-...`, `01a1ebdb-...`, `01a1ec64-...`, `01a1ed30-6b66-...`, `01a1ed30-6b80-...`) contain full `sessions/T*-a*.jsonl` transcripts on disk. They are **not** pruned.
- **Concrete Spec Amendment**:
  - Update `spec.md:24,219` to note that `../kroker-fleet-runs-025/pipeline/<uuid>/sessions/` transcripts are present on disk and are the primary source for A.3's 13-loop triage (reducing expected `"cause not recoverable"` rows).
