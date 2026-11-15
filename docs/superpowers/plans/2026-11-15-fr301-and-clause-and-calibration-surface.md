# FR-301 AND-clause + Calibration Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close FR-301 — the SOFT auto-approve gains its per-artifact deterministic AND-clause (`plan_valid` computed in code over the current plan, ADR-24's direction), the plan validators move ahead of the plan gate so failures revise the planner instead of halting after an approval, and the C7 calibration ledger gets its operator surface plus SC-6 measurement.

**Owner rulings (2026-11-15, this plan's Task 0 input):**

1. **Integration shape: BOTH.** Validators reorder ahead of `gate.plan` (failure → revise feedback to the planner) AND the computed verdict is a required conjunct inside `auto_decision_for`. The conjunct is not made redundant by the reorder: every graph variant that reaches `gate.plan` without passing `plan_check` (seeded, research, constitution — Task 3 inventories them) keeps an evidence-backed decision point.
2. **Closure scope.** Plan AND-clause + calibration monitoring close FR-301. Architecture's deterministic checks (delta-check-as-validator, `requirement_coverage`) stay under **AP-4.4**; architecture SOFT remains confidence + calibrated bucket until then. Merge needs nothing — it already has the shape and stays effectively HARD (ruling OQ2, no post-merge outcome signal).

**Architecture:** One new pure module (`validators/verdicts.py`) composes the FR-205 checks into an ADR-24 verdict — the first consumer of the evidence schemas that FR-205 shipped deliberately consumer-free. The auto-approve rule (`calibration/decision.py`) gains a required `verdict` parameter under the same no-default discipline as `calibration`. The default graph reorders `planner → plan_check → gate.plan` with `plan_check`'s failure routing back as revise guidance, mirroring `gate_node`'s own revise topology. A `sdlc calibration` CLI verb reads the ledger that retro already populates.

**Tech Stack:** Python 3.13, Pydantic, Temporal (workflow sandbox + activities), pytest, click-style CLI.

**Spec:** none yet — this plan encodes the investigation (session 2026-11-15) and the two rulings above. If the owner wants the house two-artifact flow, split a design doc from §"Decisions recorded" first.

## Global Constraints

- Build: `uv sync --frozen --extra dev`. Tests: `pytest` (fast tier default; this work needs no `slow`/`temporal`/`live` markers). Lint/type: `ruff check .`, `ruff format .`, `mypy` — all must pass before close.
- 1000-line physical file ceiling (root AGENTS.md); every file here starts far below.
- **No-default discipline** (`src/sdlc/calibration/AGENTS.md`): every new parameter to `auto_decision_for` is required. "No evidence was fetched" must never deserialize as "the evidence passed."
- **Vacuous-pass precedent** (FR-205 `covers_all` without requirements): a gate with no deterministic provider passes the conjunct vacuously — this is how architecture stays confidence+calibration-only without freezing. What is forbidden is a *provider that failed or was skipped* reading as a pass.
- **Halt strings are wire contracts:** `failed:plan-validation:<reason>` texts keep their exact wording — they become revise guidance verbatim.
- **Graph changes are input-pinned, not disk-read** (`graph.py:166-167`: `inp.graph.content_sha()` at run start) — in-flight runs carry their own graph bytes, so reordering the default graph affects new runs only. No `workflow.patched` marker is introduced by Task 3; the handler branches on port connectivity (`nc.connected(...)`, the `gate_node` pattern) so old pinned graphs keep the halt behavior.
- **Determinism:** `plan_valid` is a pure workflow-sandbox call over the stored artifact — no activity, no command, replay-identical.
- **Cross-stage imports are types only** (root AGENTS.md). `validators` importing `ImplementationPlan`/`DevTask` types and `calibration` importing the `Verdict` type are legal; no stage-to-stage calls.
- The conjunct changes decisions only where it should: a SOFT plan auto-approve of a plan that fails validators becomes impossible. HARD/OFF runs and every currently-valid plan keep byte-identical gate decisions.

## Decisions recorded (D1–D4)

- **D1 — `Verdict` shape.** `Verdict(checks_run: bool, ok: bool, findings: list[Finding])` in `validators/verdicts.py`. `checks_run=False` → vacuous pass (architecture today, merge's is pre-computed). A provider that ran and failed, or errored, is `checks_run=True, ok=False`. `auto_decision_for` requires `verdict.ok`.
- **D2 — conjunct computed independently in the gate node.** `gate_node` calls the provider registry directly rather than trusting upstream `plan_check`. Belt-and-suspenders is the point (ruling 1); the call is pure and costs no command.
- **D3 — plan_check failure = auto-revise, not a human gate.** Rounds bounded by `max_traversals` on the revise edge (mirroring the gate's own `max_traversals: 2`); exhaustion keeps today's terminal halt. No human gate opens for a validator failure — deterministic checks decide in code (ADR-24), humans decide maybes.
- **D4 — calibration surface is CLI-first.** The dashboard card is deferred (noted in ROADMAP at close-out); the ledger lives in the board's SQLite (ADR-19) and the CLI reads it directly. SC-6 rides the same verb.

## Review Focus

1. **A SOFT plan gate cannot auto-approve an invalid plan** even with confidence ≥ threshold and a `calibrated` bucket. (Task 2 test: `test_conjunct_blocks_invalid_plan`.)
2. **An invalid plan revises the planner before the gate ever opens** — guidance carries the validator text verbatim; exhaustion halts with today's `failed:plan-validation:*` strings. (Task 3 wiring tests.)
3. **Old pinned graphs keep the halt** — the reorder must not change behavior of in-flight runs. (Task 3 characterization against a pre-reorder graph literal.)
4. **Architecture SOFT is unchanged** — vacuous verdict, auto-approve still possible on confidence+calibration. (Task 2 characterization.)
5. **The operator can see why nothing auto-approves** — `sdlc calibration` lists every bucket with verdict/n/agreement and flags sub-`MIN_SAMPLES` gates as effectively HARD; SC-6 override rate prints beside it. (Tasks 5–6.)

---

### Task 1: `plan_valid` verdict function (first consumer of the ADR-24 evidence schemas)

**Files:**
- Create: `src/sdlc/validators/verdicts.py`
- Modify: `src/sdlc/validators/__init__.py` (re-exports)
- Test: `tests/validators/test_verdicts.py` (new)

**Interfaces:**
- Produces (later tasks rely on exactly these):
  - `Verdict(checks_run: bool = True, ok: bool = True, findings: list[Finding] = [])` — `Finding` from `evidence.py`; `checks_run=False, ok=True` is the vacuous constructor `Verdict.vacuous()`.
  - `plan_valid(plan: ImplementationPlan, requirements: Requirements | None) -> Verdict` — composes the FR-205 ordered family `ids_unique → deps_resolve → dag_acyclic → covers_all (only when `requirements` is not None) → task_size`, first failure wins, `Finding.evidence` carrying the failing check's text verbatim (the halt strings).
  - `GATE_PROVIDERS: Mapping[str, Callable[[Any, Any], Verdict]]` — `{"plan": ...}`. Lookup by gate node id; unknown gate → `Verdict.vacuous()`.

**Steps:**

- [ ] **Step 1: Write failing tests** — `tests/validators/test_verdicts.py`: one pass case (valid plan → `ok=True`, empty findings); one per check family (duplicate ids / unknown dep / cycle / uncovered FR id with requirements / oversized task) asserting `ok=False` and the exact failure text inside `findings[0].evidence.evidence`; vacuous case (`Verdict.vacuous()`); `requirements is None` skips coverage (vacuous-coverage pin, FR-205 precedent).
- [ ] **Step 2: Implement** `verdicts.py` pure — no I/O, no `temporalio`, composition only; re-export from `__init__.py` beside the existing names.
- [ ] **Step 3: Verify** — `pytest tests/validators/ -q`; `ruff check src/sdlc/validators`; `mypy`.
- [ ] **Step 4: Commit** — `git commit -m "feat(validators): plan_valid verdict — first consumer of the ADR-24 evidence schemas (FR-301)"`

**Estimated scope:** Small (2 files + tests).

---

### Task 2: the deterministic conjunct in `auto_decision_for`

**Files:**
- Modify: `src/sdlc/calibration/decision.py` (signature + rule)
- Modify: `src/sdlc/workflows/graph_nodes/gate.py` (provider lookup, conjunct pass)
- Modify: `src/sdlc/workflows/role_host.py` (`_revisable_stage` call site)
- Modify: `src/sdlc/stages/merge/step.py` (call site — passes `Verdict(checks_run=True, ok=True)`; the deterministic gate already passed clean there by construction)
- Modify: `src/sdlc/calibration/AGENTS.md` (document the second required parameter under the existing no-default rule)
- Test: extend `tests/calibration/` decision tests; characterization for architecture unchanged.

**Steps:**

- [ ] **Step 1: Write failing tests** — extend the decision test module: conjunct blocks (`ok=False` → `None` even with `calibrated` bucket and confidence ≥ threshold); vacuous passes (D1/architecture pin); `comments` of a conjunct-blocked auto-approve never exists (returns `None` → human wait). Then update the three call-site suites.
- [ ] **Step 2: Implement** — `auto_decision_for(name, cfg, confidence, calibration, verdict: Verdict)`; require `verdict.ok` beside the existing conjuncts; update `gate.py` to `GATE_PROVIDERS.get(name, vacuous)` and pass through; `role_host`/`merge` per the interfaces above.
- [ ] **Step 3: Update the local contract** — `calibration/AGENTS.md` gains: the `verdict` parameter is required and has no default; absent-provider gates pass vacuously, failed providers never do.
- [ ] **Step 4: Verify** — `pytest tests/calibration/ tests/workflows/ -q` (fast tier); `ruff`; `mypy`.
- [ ] **Step 5: Commit** — `git commit -m "feat(calibration): deterministic verdict conjunct in SOFT auto-approve (FR-301, ADR-24)"`

**Estimated scope:** Medium (4 source files + tests + local AGENTS.md).

---

### Task 3: graph reorder — validators feed the gate, failures revise the planner

**Files:**
- Modify: `src/sdlc/workflows/graphs/default.graph.yaml` (+ every variant containing `gate.plan`: `default-requirements`, `seeded`, `default-research`, `default-constitution` — inventory in Step 1)
- Modify: `src/sdlc/workflows/graph_nodes/postplan.py` (plan_check: route failure to `revise` when connected, halt when not or exhausted)
- Modify: `src/sdlc/graph/node_types.py` (plan_check ports: add `revise` out + note the guidance input reuse)
- Test: `tests/graph/` wiring tests; characterization with a pre-reorder graph literal.

**Mechanics (D2/D3):**

- New order on every affected graph: `planner → plan_check (ok) → gate.plan`. `plan_check.halt` disappears from new graphs; its failure port becomes `revise` targeting `planner.guidance` with `max_traversals: 2`, payload a synthesized `GateDecision(outcome=REVISE, guidance=<validator text verbatim>)` — the planner's existing `guidance: GateDecision` input port needs no schema change.
- `plan_check_node` branches on `nc.connected("revise")`: connected and traversals remain → revise; else → today's terminal halt with the exact `failed:plan-validation:<reason>` strings. Old pinned graphs (halt port, no revise edge) keep today's behavior by construction.
- `gate_node` (Task 2) recomputes `plan_valid` itself — variants that reach `gate.plan` without `plan_check` stay protected.

**Steps:**

- [ ] **Step 1: Inventory** — grep every `*.graph.yaml` containing `gate.plan` or `plan_check`; record the edge lists to change. Default-research/constitution may lack plan stages — verify before editing.
- [ ] **Step 2: Write failing tests** — reorder wiring (ok-port feeds gate.artifact); invalid plan → planner receives guidance with the validator text, round increments; two invalid rounds → terminal halt with today's strings; characterization: run the OLD graph literal through the dispatcher and assert the halt still fires (in-flight-run pin).
- [ ] **Step 3: Implement** — node types, `postplan.py` branch, graph yaml edits. Do not touch the seeded graph's documented park-at-merge behavior beyond the reorder if it has no plan stage.
- [ ] **Step 4: Verify** — `pytest tests/graph/ -q` plus the fast tier; confirm default graph sha change is expected and recorded (it shifts — new runs only).
- [ ] **Step 5: Commit** — `git commit -m "feat(graph): plan validators precede gate.plan; failures revise the planner (FR-301, D3)"`

**Estimated scope:** Medium (3 source + several yaml + tests).

---

### Task 4: merge call-site + stage contracts in the same diff

**Files:**
- Modify: `src/sdlc/stages/merge/step.py` (already touched in Task 2; verify the `Verdict` it passes states `checks_run=True`)
- Modify: `src/sdlc/stages/merge/merge.md` (C7 clause sentence gains the verdict-conjunct mention)
- Modify: `src/sdlc/stages/plan/plan.md` (gate wiring sentences: validators precede the gate; SOFT requires the conjunct)

**Steps:**

- [ ] **Step 1:** Update both stage contracts — behavior and clause in one diff (root AGENTS.md artifact-boundary rule).
- [ ] **Step 2: Verify** — `pytest tests/merge/ tests/plan/ -q`; `python scripts/check_clauses.py` if stage clauses are in its scope.
- [ ] **Step 3: Commit** — `git commit -m "docs(stages): plan/merge contracts carry the deterministic conjunct (FR-301)"`

**Estimated scope:** Small.

---

### Task 5: `sdlc calibration` CLI verb (B1)

**Files:**
- Modify: `src/sdlc/calibration/store.py` (add `summary()`: per `(gate, bucket_key)` — n, verdict via `verdict_for(recent(...))`, agreement rate, last sample at)
- Modify: `src/sdlc/cli.py` (new verb; follow the existing subcommand pattern)
- Test: `tests/calibration/test_cli.py` over a temp SQLite.

**Behavior:** table of every bucket: `gate | bucket | verdict | n | agreement | effectively-HARD?` (the flag when `verdict != "calibrated"`). Exit 0 always — it is a read surface, not a gate. No dashboard work here (D4).

**Steps:**

- [ ] **Step 1: Write failing tests** — empty ledger → empty table; seeded ledger → verdicts computed; sub-`MIN_SAMPLES` bucket flagged effectively HARD.
- [ ] **Step 2: Implement** store summary + verb; keep `store.py` free of CLI imports.
- [ ] **Step 3: Verify** — `pytest tests/calibration/ -q`; run the verb against a scratch board DB by hand.
- [ ] **Step 4: Commit** — `git commit -m "feat(calibration): sdlc calibration operator surface (FR-301 monitoring)"`

**Estimated scope:** Small-Medium.

---

### Task 6: SC-6 measurement (B2)

**Files:**
- Modify: `src/sdlc/calibration/store.py` or a sibling `metrics.py` (pure aggregation)
- Modify: `src/sdlc/cli.py` (the same verb prints the override rate)
- Test: extension of `tests/calibration/test_cli.py`.

**Behavior:** soft-gate override rate = human decisions on SOFT gates ÷ all SOFT gate decisions, over the run records the board already retains (`GATE_DECIDED` events carry `policy`/`decided_by`). Step 1 verifies where retained events are queryable (retro export path, `records/`); if nothing queryable exists, fall back to appending a per-decision row beside `gate_calibration` at `_on_gate_decided` time — decide in Step 1, do not grow scope silently.

**Steps:**

- [ ] **Step 1: Discovery** — locate the retained GATE_DECIDED source; record the choice in the commit body.
- [ ] **Step 2: Write failing tests → implement → verify** — `pytest tests/calibration/ -q`.
- [ ] **Step 3: Commit** — `git commit -m "feat(calibration): SC-6 soft-gate override rate beside the ledger surface (FR-301)"`

**Estimated scope:** Small-Medium.

---

### Task 7: close-out — PRD, ROADMAP, ADR-24 status

**Files:**
- Modify: `PRD.md` §FR-301 (SHALL clauses gain the deterministic conjunct)
- Modify: `ROADMAP.md` FR-301 → `[x]` with a one-sentence *Landed* entry; prepend the full entry to `docs/roadmap/last-verified-log.md`; AP-4.2 note: its validator half now feeds the gate
- Modify: `docs/adr.md` ADR-24: strike "not built" for the `plan_valid` half; `approve`/`tests_passed` remain AP-3
- Modify: `docs/roadmap/agent-architecture-plan.md` AP-4.2 (partially served note)

**Steps:**

- [ ] **Step 1:** Apply the doc edits; keep the ROADMAP cell one sentence, full entry in the log.
- [ ] **Step 2: Verify** — full fast tier `pytest`; `ruff check . && ruff format . && mypy`; `python scripts/check_file_size.py`.
- [ ] **Step 3: Commit** — `git commit -m "docs: close FR-301 — AND-clause landed, calibration surface landed"`

**Estimated scope:** Small.

---

## Checkpoints

- **After Tasks 1–2:** fast tier green; a SOFT plan auto-approve of an invalid plan is impossible in unit tests; architecture unchanged.
- **After Task 3:** dispatcher tests green on old and new graph literals; the revise loop bounded; halt strings verbatim.
- **After Tasks 5–6:** `sdlc calibration` runs against a scratch DB and answers "why is nothing auto-approving."
- **Close (Task 7):** all tiers green, docs consistent, ROADMAP checkbox flipped.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Reorder breaks a graph variant not inventoried | High | Task 3 Step 1 greps every `*.graph.yaml`; dispatcher executability check fails closed at run start (`graph.py:159`) |
| `plan_check` revise loop burns rounds a human should see | Medium | D3: validator failures never open human gates; exhaustion keeps the terminal halt (today's behavior) |
| Conjunct silently freezes architecture SOFT | Medium | D1 vacuous verdict + Task 2 characterization pinning architecture auto-approve unchanged |
| New `verdict` param grows a default in a future edit | High | calibration/AGENTS.md rule extended in Task 2 Step 3; test asserting the signature has no default |
| Default graph sha shift surprises benchmark comparisons | Low | Expected and recorded (Task 3 Step 4); graphs are input-pinned so in-flight runs are untouched |
| SC-6 has no queryable source | Medium | Task 6 Step 1 discovery with an explicit fallback decision recorded in the commit body |

## Open Questions

- Seeding cold buckets: benchmark runs write judge-backed labels (`LabelSource.BENCHMARK`); production proxy labels accrue organically. Should a seeding run be scheduled before close, or is "effectively HARD until n≥20, now visible" acceptable? (Owner; not blocking.)
- Dashboard calibration card: deferred (D4) — file under the canvas/UI epic when picked up.
- `THRESHOLD`/`EPSILON` re-derivation (calibration/AGENTS.md mandate) waits on real samples — operational, not in this plan's code path.
