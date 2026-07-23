# Cat-café Tier-A oracle — E-34 via the existing decomposition case

| | |
|---|---|
| Date | 2026-07-23 |
| Status | Approved design |
| Roadmap items | **E-34** (decomposition-forcing benchmark case, closed via cat-café), **E-29 / OQ-B3** (recorded as already decided, no code change) |
| Anchors | SC-1/SC-3 (benchmark matrix), FR-106 (criterion→test discipline), ADR-15/E-30 (toolchain dispatch), E-31 (held-out oracle machinery) |
| Depends on | E-30 ✓, E-31 ✓ — no new `src/` machinery |

## 1. Problem

The benchmark suite has one Tier-A case (todo-api, held-out oracle) and one
decomposition-forcing case (cat-café, E-27) — but they are not the same case.
Cat-café, the only case where planner decomposition is load-bearing, is graded
by rubrics alone (Tier-B). E-34's gap is therefore not "no decomposition case
exists" (the roadmap text predates E-27 landing cat-café) but "the
decomposition case has no objective grade."

Two obstacles kept cat-café rubric-only:

1. **No frozen contract.** The kata deliberately says *"anything not described
   here is your choice — the rules are up to you"* and telemetry is generated
   randomly. An oracle cannot assert against nondeterministic data flowing
   through rules the implementer invented.
2. **The research grounding gate.** The roadmap (E-29) records the live run
   dying at `rejected:research.grounding`. **This is stale.** A 2026-07-20
   decision (`feature.py:987-1006`) already changed the behavior: a grounding
   violation fails the research *stage* (`research_failed`, record kept with
   `outcome=FAIL`, retain and digest skipped) and the pipeline proceeds on the
   idea alone. Cat-café can complete end-to-end today.

## 2. Decision summary

**Assets-only increment. Zero `src/` changes.**

- Cat-café's description gains a frozen **interface contract** (the todo-api
  move: an interface is not a functional requirement, so the kata's
  "do not shrink / do not add" clause is preserved — the six activities and
  the risk rule stay byte-identical).
- A held-out `oracle/` suite grades through the existing E-31 machinery,
  turned on by adding `language: python` to `case.yaml`.
- The oracle asserts **unambiguous extremes only**, and reads the app's own
  `GET /floorplan` before crafting scenarios — so no coordinates or
  thresholds are pinned and the kata's design freedom survives intact.
- E-29/OQ-B3 is **recorded as decided, not implemented**: benchmark cells
  accept a research-stage failure as a recorded `FAIL` that does not block
  the run; rubric judging of the brief happens only when grounding passes.
  (The "demote to inferred + still judge" variant was considered and
  deliberately not built — clean follow-on if ever needed.)

Rejected alternatives: (B) folding a true research-advisory knob into this
increment — touches the most sensitive block of `feature.py` in an otherwise
code-free change; (C) pinning thresholds/zone radii in the description —
sharper assertions at the cost of the kata's own rules.

## 3. Frozen interface contract (appended to `case.yaml` description)

Appended as a new "Interface contract" section; the functional-requirements
text above it is untouched.

- Implement in **Python**. Expose an ASGI application importable as
  `app:app` (module `app.py` at the repo root, attribute named `app`).
- **Importing `app:app` must not auto-start the random telemetry
  generator.** Simulation runs only when launched explicitly (e.g.
  `python app.py`). *(This is the determinism seam: the oracle imports the
  app via `httpx.ASGITransport` and sees only what it injects.)*
- `POST /telemetry` — body `{cat_id, x, y, breathing_rate, timestamp}`,
  responds 2xx; the reading is processed exactly as if a collar emitted it.
- `GET /floorplan` — 200; a JSON body in which each zone exposes at least
  `{kind, x, y}` with `kind ∈ {rest_area, litter_box, water_bowl,
  food_bowl}`. Richer shapes are allowed; the implementer chooses all
  coordinates.
- `GET /cats` — 200; a list of `{id, x, y, activity, at_risk}` where
  `activity` is one of `sleeping | eating | drinking | litter_box | playing
  | fighting` or `null` when undetermined, and `at_risk` is a boolean.
- `GET /cats/{id}` — 200; detail including the latest sensor reading and
  `history`: the cat's readings (`{timestamp, x, y, breathing_rate}`) for
  the last 24 hours **relative to that cat's newest reading** (never the
  wall clock). Unknown id → 404.

Timestamps are ISO-8601 strings supplied by the caller; detection and the
24-hour window are computed from telemetry timestamps, not server time.

## 4. Held-out oracle (`benchmarks/cases/cat-cafe-monitoring/oracle/`)

Same shape as todo-api's oracle: copied uncommitted into the produced
worktree at grade time by `grade_oracle`, run via
`ToolchainAdapter.oracle_test_cmd`, graded as fraction passing from JUnit
XML. Never in a worktree, prompt, or recall during the run
(`held_out_ok` diff check unchanged).

**Fairness rule (load-bearing):** every assertion must hold under *any*
reasonable ruleset. Scenarios are extreme and oracle-authored; ambiguous
outcomes accept a set of answers.

Files:

- `conftest.py` — `client` fixture (`httpx.ASGITransport` over the produced
  `app:app`, `sys.path` root insertion — mirror todo-api's conftest).
  Helpers: `zone(client, kind)` → the app's own coordinates for a zone
  kind; `feed(client, cat_id, readings)` → POST a timestamped sequence.
- `test_activity.py` — all scenarios inject a sustained sequence (several
  readings over a few minutes) *at the app's reported zone coordinates*:
  - stationary at `food_bowl`, normal bpm → `eating`
  - stationary at `water_bowl` → `drinking`
  - stationary in `rest_area`, low bpm → `sleeping`
  - stationary at `litter_box` → `litter_box`
  - two cats co-located away from all zones, fast movement, high bpm →
    `playing` **or** `fighting` (either passes)
- `test_risk.py` —
  - sustained ~180 bpm while stationary in `rest_area` → `at_risk is True`
  - sustained ~5 bpm → `at_risk is True`
  - calm cat, ~25 bpm, resting → `at_risk is False` (the research-grounded
    floor was >35 bpm at rest; 25 is unambiguously normal)
- `test_monitoring.py` —
  - POST moves a cat → `GET /cats` reflects the new coordinates
  - `GET /cats/{id}.history` contains the injected readings
  - a reading 25 h older than that cat's newest is **absent** from history
  - unknown cat id → 404

No sleeps, no randomness, no wall-clock reads anywhere in the suite.

## 5. Wiring

`case.yaml` (`benchmarks/cases/cat-cafe-monitoring/case.yaml`):

- add `language: python` — this alone opts the case into oracle grading
  (`BenchmarkWorkflow` → `grade_oracle`, manifest-vs-marker language signal
  included);
- append §3's contract to `description`;
- everything else unchanged (`research_enabled: true`, rubrics, models,
  judge, `--variant max`).

No changes to `oracle.py`, `feature.py`, `workflow.py`, or any adapter.

## 6. Validating the oracle itself

An unexecuted oracle is the one artifact here that can be silently broken.

- `tests/fixtures/cat_cafe_ref/app.py` — a minimal reference implementation
  satisfying §3 (in-memory state, simple distance/threshold rules, no
  simulator). Lives under `tests/`, never shipped to a worktree, never seen
  by any run — it exists to exercise the oracle, not to leak an answer key.
- `tests/test_cat_cafe_oracle.py` — copies `oracle/` + the reference app
  into a tmpdir and runs pytest there programmatically:
  1. **green** against the reference implementation (whole suite passes);
  2. **red** when risk detection is stubbed out (a broken variant of the
     reference — proves the oracle discriminates, not just executes).
- Mirrors the `tests/fakes/` philosophy: deterministic CI stand-in for the
  live proof.

The live end-to-end proof (a real benchmark cell producing an oracle grade
for cat-café) is a run-time exercise outside CI, at the user's discretion —
same status as E-27's smoke run.

## 7. Documentation updates

- **ROADMAP.md** — mark **E-34** landed via cat-café (note the roadmap's
  "both current cases" text predated E-27); mark **E-29** closed by the
  2026-07-20 stage-fail-continue decision (grounding failure no longer
  blocks a run; judging only on grounded briefs); update E-27's "unblocks
  when E-29 or E-30 lands" note.
- **docs/BENCHMARK.md §7** — record OQ-B3 as answered: benchmark cells run
  with the hard grounding verifier; a violation is a recorded research-stage
  `FAIL` in the cell's record, not a cell abort.

## 8. Out of scope

- Research-advisory knob (demote-to-inferred + judge on failure) — named
  follow-on, not built here.
- E-31a diff-coverage anti-cheat — separate roadmap item.
- Any new language adapter (E-30a/b/c) — cat-café is Python.
- Changes to the six functional activities, the risk rule, or any other
  kata requirement.
