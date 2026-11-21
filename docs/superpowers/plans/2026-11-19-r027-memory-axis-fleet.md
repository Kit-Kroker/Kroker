# R027 Memory-Axis Fleet — Finalize P3 (SC-4/SC-6 Measurable) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (the
> orchestrator drives this plan live; it is an operations protocol, not product code
> — no source in `src/` changes. Part-B discipline: findings become backlog cards,
> never in-round code fixes).

**Goal:** Make SC-4 and SC-6 measurable from real runs (P3's exit criterion) by
running round 027 — 6 memory-ON + 2 memory-OFF `deveval-readtime` runs at SOFT
gate policy on the R026 fleet commit — then close out the roadmap.

**Architecture:** The R026 stack (workers on image `sha256:41b306a…` = commit
`ec3f128f`, hindsight container, temporal) serves the round unchanged except for
env-only fixes (`.env`, outside the tree — the fleet is not voided). The newly
discovered R026 defect — hindsight's LLM was pointed at `openai` with a z.ai key
(HTTP 401 ×1134, bank empty, memory enabled-but-dead) — is fixed by pointing the
hindsight extraction LLM at the working z.ai Anthropic-compatible route with
`claude-haiku-4-5`. A deterministic attendant script answers escalations and
clarifications from a pinned answer map; the round is scored with the existing
rollup and reported per the fleet-runs ops manual.

**Tech Stack:** sdlc CLI (`python -m sdlc.cli`), docker compose (project
`kroker`), Hindsight API, Herdr panes for the attendant.

**Spec:** owner rulings 2026-11-19 (shape B: 6 on + 2 off; carry the 026 smoke
stamp — same commit `ec3f128f` + image; ceiling **$15 judged** + disclosed
haiku extraction cents; case `deveval-readtime`); normative protocol:
`docs/operations/fleet-runs.md`.

## Global Constraints

- Fleet commit: `ec3f128f1440de5957824f65b6f32bc302db2` (R026's). No commit
  lands between stamp and last scored run; the dedicated checkout's
  `git status --short` stays empty. Env/compose/host fixes do not void.
- Gate policy: `--gate-policy soft` on every run (SC-6's denominator; the
  confidence-gated path + MergeVerdict get exercised for the first time).
- Runs are STRICTLY SEQUENTIAL (series integrity: run N's recall must see run
  N−1's retain).
- Ceiling $15 judged (rubric-judge spend from records); hindsight haiku
  extraction spend is tracked separately and disclosed. z.ai planning is
  subscription-flat.
- Smoke: `--skip-smoke` under the owner's stamp-carry ruling (recorded in the
  report). A case-class smoke failure does not apply (no smoke run).
- Stop rules (ops manual): an infra-class failure halts for the owner; ceiling
  crossing ends the delegation; no re-running to improve; originals kept.
- Pre-registered failure classes: case failure (scored, does not stop),
  infrastructure failure (halts). The known case-class noise: readtime's
  validator/collector-artifact class (R026: 3 loops, 0 resolved) — expected,
  disclosed, does not stop the round.
- No product-code changes during the round. Close-out docs land in the primary
  checkout after the last scored run.

## Review Focus

1. **Memory silently dead again** (the R026 defect class) — every run's summary
   must be checked for `memory_enabled=True` AND the bank's
   `failed_operations` must not grow during Phase 1; Phase 2 summaries must
   show `memory_enabled=False`.
2. **Attendant mis-answer / stuck run** — the attendant must answer every
   pending interaction within minutes; a run parked >1 h on an unanswered
   interaction is an infra-class halt.
3. **Cross-root contamination** — the 027 runs root must contain only 027 runs;
   the rollup's roots line must say `runs_root` for both halves, commit set
   exactly one (`ec3f128f`).
4. **Worker recreate drift** — after each compose recreate, verify the worker
   image is still `sha256:41b306a…` and `SDLC_MEMORY_*` matches the phase.
5. **Spend overrun** — per-run judged $ announced before each run; cumulative
   tracked; stop at $15.

---

### Task 1: Preflight — env fixes, fleet checkout, proofs

**Files:** `.env` (memory LLM fix + `KROKER_RUNS_BIND` flip),
`../kroker-fleet-027/` (git worktree at `ec3f128f`),
`../kroker-fleet-runs-027{-evidence,}/` (runs root + evidence).

- [ ] **Step 1: Fix the hindsight LLM config in `.env`** —
  `HINDSIGHT_API_LLM_PROVIDER=anthropic`,
  `HINDSIGHT_API_LLM_BASE_URL=https://api.z.ai/api/anthropic`,
  `HINDSIGHT_API_LLM_MODEL=claude-haiku-4-5` (key unchanged);
  `KROKER_RUNS_BIND=/home/maksim/work/kroker-fleet-runs-027`. Create both
  runs dirs.
- [ ] **Step 2: Recreate the stack** — `docker compose -f docker-compose.yml -f
  docker-compose.pools.yml up -d` (from the primary checkout; recreate
  hindsight + both workers). Verify: hindsight log shows
  `provider=anthropic, model=claude-haiku-4-5`; worker image still
  `sha256:41b306a…`; worker env `SDLC_MEMORY_ENABLED=true`; bank
  `project-default` exists with 0 nodes; `/health` green.
- [ ] **Step 3: Fleet checkout** — `git worktree add ../kroker-fleet-027
  ec3f128f` + `uv sync --frozen --extra dev`; `git status --short` empty;
  `git rev-parse HEAD` = the fleet commit.
- [ ] **Step 4: Prove memory works (live, cents)** — from the worktree:
  `SDLC_LIVE_TESTS=1 TEMPORAL_HOST=localhost:7233 SDLC_MEMORY_BASE_URL=http://localhost:8888
  uv run python -m pytest tests/test_hindsight_live.py -v -m live` — expected
  PASS (retain + recall + reflect against the fixed container). Then a
  scratch-bank probe: retain one small fact on bank `probe-r027`, recall it,
  delete the bank. Snapshot everything into
  `../kroker-fleet-runs-027-evidence/preflight/`.
- [ ] **Step 5: Snapshot baseline state** — hindsight bank stats JSON,
  calibration CLI output (`no samples recorded`), `sdlc doctor`,
  `sdlc schedules list` (nightly-reflect 03:00 UTC on project:default —
  harmless, disclosed), temporal env, per the 025 B.2 checklist lines.

### Task 2: Attendant — script + Herdr pane

**Files:** `../kroker-fleet-runs-027-evidence/tooling/attendant.py` (outside
the repo), its JSONL interaction log in the evidence dir.

- [ ] **Step 1: Write the attendant** — poll (20 s) the run's pending
  interactions via the CLI from the fleet worktree; for each pending gate:
  `approve` (approve-to-proceed, R026 regime); for each pending clarification:
  answer from the pinned map (substring match on the question text; fallback
  "Use the simplest consistent interpretation; prefer the library default",
  logged as fallback). Log every interaction.
- [ ] **Step 2: Pin the answer map** (from readtime's R026 Q1–Q9, consistent
  across runs — this is what memory retains):
  WPM/decay → "Plain sum of per-image times, no decay; 200 WPM default" ·
  text format → "Human-readable `2m 30s` style; sub-minute as `45s`" ·
  rounding → "Ceiling to whole seconds; minutes = floor(seconds/60)" ·
  markdown → "Convert via markdown2, then the HTML pipeline" ·
  HTML text → "Exclude script/style contents; include title text" ·
  operators → "+ and − on Result objects over seconds, returning Result" ·
  validation → "ValueError for unsupported format, None/non-string content,
  non-positive WPM, empty string" · inputs → "Content strings only" ·
  CJK → "Whitespace tokenization is sufficient".
- [ ] **Step 3: Start it in a Herdr pane** — sibling pane, same cwd, `--no-focus`,
  running against the active run id; restart per run (or loop over the
  current pending set). Verify it answers a real interaction in run 1 within
  a minute.

### Task 3: Phase 1 — 6 memory-ON SOFT runs (the series)

- [ ] **Step 1..6 (one per run):** announce
  (`RUN n/8: case deveval-readtime, arm zai-coding-plan-glm-5.3, commit
  ec3f128f, expected ~$1.1–1.7, spend so far $x, ceiling left $y`), then from
  the fleet worktree:
  `SDLC_RUNS_ROOT=/home/maksim/work/kroker-fleet-runs-027 TEMPORAL_HOST=localhost:7233
  uv run python -m sdlc.cli benchmark run --case deveval-readtime
  --gate-policy soft --skip-smoke`, attendant on duty. After each run:
  record outcome class, judged $, interactions count; verify the summary
  (`memory_enabled=True`, clarifications count, gates all soft) and that the
  bank's node/document count GREW (memory alive). A summary without a grown
  bank = the Review-Focus-1 defect: halt for owner.
- [ ] **Step 7: Series checkpoint** — after run 6: questions-per-run list,
  `sdlc calibration` output (samples may now exist if any SOFT gate
  auto-approved), bank stats snapshot.

### Task 4: Phase 2 — 2 memory-OFF control runs (the delta)

- [ ] **Step 1:** `.env` `SDLC_MEMORY_ENABLED=false` → recreate workers →
  verify env + image unchanged (Review-Focus 4).
- [ ] **Step 2..3:** runs 7–8 exactly as Phase 1 (announce, run, verify
  `memory_enabled=False` in the summaries). Bank must NOT grow.
- [ ] **Step 4:** flip `.env` back to `true` and recreate (leave the host as
  found).

### Task 5: Score + fleet report

- [ ] **Step 1:** `SDLC_RUNS_ROOT=/home/maksim/work/kroker-fleet-runs-027
  uv run python -m sdlc.cli benchmark score --all` from the worktree; confirm
  the roots line reads `runs_root` for both halves, commit set = {ec3f128f},
  8/8 summarized.
- [ ] **Step 2:** write `../kroker-fleet-runs-027/fleet-report.md`: SC table
  (SC-4 rate + n + series + questions-per-run; SC-6 + SC-6-advisory rates +
  n vs the n≥5 floor), the on/off delta (oracle grade, judged $,
  clarifications per run), the R026 hindsight-401 discovery + fix (infra
  class, outside the tree), smoke-stamp-carry ruling, spend vs ceiling
  (judge + haiku extraction), infra/failure tables, honest misses, named
  follow-ons (calibration cold-start deadlock; SC-4 proxy immobility;
  collector-artifact class).
- [ ] **Step 3:** verify rollup numbers against hand counts (spot-check SC-6
  denominator against the summaries' gate rows).

### Task 6: Repo close-out (primary checkout, after the last scored run)

- [ ] **Step 1: ROADMAP.md** — P3 item `[x]` with the measured story; SC-4 and
  SC-6 entries get **Measured at R027** blocks (value, n, target met/missed);
  FR-404 caveat + §9.3 item 4 corrected (R026 ran memory-enabled-but-dead:
  hindsight 401, empty bank — 027 is the first working-memory fleet);
  last-verified cell refresh + full prepend to
  `docs/roadmap/last-verified-log.md`.
- [ ] **Step 2: Backlog cards** (`.workspace/tasks/`): (a) calibration
  cold-start deadlock — samples only accrue from auto-approved SOFT gates, so
  an empty ledger can never bootstrap (SC-6 structurally 1.00); (b) SC-4
  proxy immobility under an attendant regime — the rate cannot move; the
  live signal is questions-per-run, which no rollup row charts.
- [ ] **Step 3: Commit** — docs-only commit on the primary checkout
  (`docs: close P3 — R027 memory-axis fleet makes SC-4/SC-6 measurable`),
  including this plan.
