# Pre-flight evidence — round 026 Part B (T040–T041, 2026-11-18)

Fleet commit (frozen): **`ec3f128f1440de5957824f65b6658f32bc302db2`**
(HEAD of `main`, pushed and in sync with `origin/main`; the Part A
close-out `b8f6b0d2` plus the docs-only scribe pass `ec3f128f` — Part B
changes no code, so the freeze takes the pushed HEAD per the
orchestrator's GATE 2 acceptance).

## T040 checklist

### 1. CLI verbs / `--arm` name — PASS

From `src/sdlc/benchmarks/cli.py`: `benchmark run --case <case.yaml>
--arm <name>`, `benchmark smoke` (both take `--gate-policy`),
`benchmark score --all [--out <dir>]`, `benchmark verify-case --case
<id>`. Arm name from the case files themselves
(`benchmarks/cases/cat-cafe-monitoring/case.yaml`):
`strong_arm: zai-coding-plan-glm-5.3` — the dashed form; every 026 run
uses `--arm zai-coding-plan-glm-5.3 --gate-policy hard`.

### 2. Doctor — PASS with the two recorded 025 notes

`uv run python -m sdlc.cli doctor`: **10 passed, 1 warning, 2 failed**
— byte-for-byte the 025 pre-flight state: FAIL `gh` not on PATH
(benchmark runs have no remote and skip the PR step, merge/step.py);
FAIL host git identity (benchmark checkpoints commit inside the
containers, which carry identity via the compose worker's env). PASS:
provider keys (`ANTHROPIC_API_KEY`, `EXA_API_KEY`, `ZAI_API_KEY`),
`GH_TOKEN`, **temporal connected (localhost:7233)**, **worker pools
"routing on: 'ai-sdlc-harness' polled by 1 worker(s)"**, board db,
containment policy, notify routes.

### 3. Pools overlay + harness cap — PASS

`docker compose -f docker-compose.yml -f docker-compose.pools.yml -f
docker-compose.override.yml config -q` → valid. Both pools Up on the
new fleet image (below): `kroker-worker-1` (core) and
`kroker-worker-harness-1`; `KROKER_HARNESS_CAP` defaults to **2**
(`docker-compose.pools.yml:39`). Pollers verified live via the
Temporal CLI: `ai-sdlc` ← `core@…` workflow pollers;
`ai-sdlc-harness` ← `harness@…` activity pollers (last access <1 min).

### 4. The 025 host fixes — ALL PRESENT

- `KROKER_HARNESS_QUEUE=default` — in `.env` (line 94; read by both
  containers via env_file) and mirrored in the fleet checkout's
  untracked `.env` (the CLI-side copy, line 94 there).
- `safe.directory` × 5 — `docker-compose.override.yml` carries
  `GIT_CONFIG_COUNT=5` with one tight entry per case repo
  (`/srv/scratch-repos/<case>`) on BOTH pools; verified in-container
  (`GIT_CONFIG_COUNT=5` on both).
- read-only opencode `auth.json` bind —
  `~/.local/share/opencode/auth.json:/root/.local/share/opencode/auth.json:ro`
  on both pools; verified present in both containers.
- image built **with** `--build-arg
  KROKER_COMMIT=ec3f128f1440de5957824f65b6658f32bc302db2` — see T041.
- `KROKER_RUNS_BIND=/home/maksim/work/kroker-fleet-runs-026` (fresh
  dedicated root; `.env` line 93) — verified in both containers; the
  host-side CLI uses `SDLC_RUNS_ROOT` at the same path: one tree.

### 5. Credentials — PASS (names only, values never recorded)

`.env`: `ZAI_API_KEY` (author arm + opencode auth), `ANTHROPIC_API_KEY`
+ `ANTHROPIC_BASE_URL` (judge), `EXA_API_KEY` (research provider:
cat-cafe, todo-api), `GH_TOKEN`, `HINDSIGHT_*`, `SDLC_MEMORY_*`.

### 6. Adversary / containment off in a DUMPED CELL CONFIG — PASS (R4)

Dumped a real cell config through the production path
(`load_case_spec` → `arm_filtered_spec` → `expand_matrix` →
`_cell_config` for cat-cafe at `--arm zai-coding-plan-glm-5.3`):

```json
{"adversarial_review_enabled": false,
 "containment_enabled": false}
```

### 7. Fresh dedicated `SDLC_RUNS_ROOT` + the roots line — PASS

`/home/maksim/work/kroker-fleet-runs-026` created fresh and empty
(verified 0 entries; the workers' `/app/runs` bind points at it — one
tree with the host CLI side). The roots line printing this root is
T006's renderer, proven on the 025 copy at T008 ("records: …
(runs_root); summaries: … (runs_root)").

### 8. Scratch repos — fresh seeding, 025 evidence untouched — PASS

New dir `/home/maksim/work/scratch-repos-026/` (the 025 dir and its
evidence branches are untouched; the override's mount now binds the
new dir at the same container path `/srv/scratch-repos`, so no
`case.yaml`/tree edit). Five repos seeded per the 025 T021 protocol —
non-bare, single empty `init` commit on `main`, author
`sdlc <sdlc@local>` (mirrors the 025 repos' init shape):

```
todo-api-greenfield, deveval-readtime, deveval-lice,
deveval-geotext, cat-cafe-monitoring — each: main only, 1 commit
```

`sdlc benchmark verify-case`: deveval-readtime **PASS**, deveval-lice
**PASS**, deveval-geotext **PASS**, cat-cafe-monitoring **PASS**;
todo-api-greenfield **FAIL** is the known tool-shape mismatch (the
hand-written smoke case has no `reference/`; its validation is the
smoke stamp itself — the 025-recorded note).

### 9. Attendant (A-3/A-5) — READY

`/tmp/opencode/fleet_attendant_026.py` (025's v3 + the 026 duties):
tends every pending decision (stage gates / task escalations / merge
gates approved; clarify answered with the suggested answer, else an
explicit no-preference reply logged as ALERT); **approve-only on
planned gates, with any REVISE verdict still approved but logged as
STEERING** (disclosed in the fleet report); **30-minute idle
watchdog** (no interaction AND no new record bytes for 30 min →
prominent IDLE alert, re-armed every 10 min — a parked run surfaces,
never sits silently); **judged cost polled every 60 s** against the
run's announced per-run stop (`SDLC_BENCHMARKS_ROOT` record streams;
crossing logs COST-STOP — the operator cancels, the attendant never
kills); **ledger on** (stdout + `ATTENDANT_LEDGER` file). py_compile
clean.

## T041 — the freeze (2026-11-18 19:2x)

- Dedicated checkout: `git worktree add ../kroker-fleet-026 ec3f128f`
  → **fleet commit `ec3f128f1440de5957824f65b6658f32bc302db2`**;
  `git status --short` **empty**. All runs dispatch from this
  checkout. Untracked `.env` copied in (mode 600) for CLI-side
  credentials.
- Image rebuilt FROM the dedicated checkout:
  `docker build -f ../kroker-fleet-026/Dockerfile --target runtime
  --build-arg KROKER_COMMIT=ec3f128f1440de5957824f65b6658f32bc302db2
  -t ghcr.io/kit-kroker/kroker-worker:latest ../kroker-fleet-026`
  → **`sha256:41b306a9c003…`** (created 2026-11-18T19:24:51+01:00).
  Both workers recreated onto it with the three-file compose.
- In-container verification battery, BOTH pools green:
  image `sha256:41b306a9c003…`, restarts=0; `KROKER_COMMIT`
  = the full fleet sha; `resolve_provenance()` (awaited) returns
  `Provenance(kroker_commit='ec3f128f1440de5957824f65b6658f32bc302db2')`;
  `ENGAGEMENT_CAP_S=600`; `KROKER_HARNESS_QUEUE=default`;
  `KROKER_RUNS_BIND=/home/maksim/work/kroker-fleet-runs-026`;
  `GIT_CONFIG_COUNT=5`; auth.json present; `/srv/scratch-repos` = the
  five fresh repos; `/app/runs` empty (the 026 root). Pollers live:
  `core@…`→`ai-sdlc`, `harness@…`→`ai-sdlc-harness`.
- readtime reference deps (beautifulsoup4/pyquery/markdown2/lxml)
  re-provisioned post-recreate into BOTH containers
  (`uv pip install --python /app/.venv/bin/python`) and verified
  importing; same caveat as 025: writable layer, survives restarts
  but not a recreate — no recreate is planned between now and the
  last run, and any unplanned recreate is an infra event anyway.
- **FREEZE ANNOUNCED: fleet commit
  `ec3f128f1440de5957824f65b6658f32bc302db2`. No commit lands between
  the smoke stamp and the last scored run.**

## T042 — the smoke (paid, unscored, announced)

Announced (orchestrator, GATE 2 acceptance, on the record): expected
judge spend **$1.94** (025's measured smoke cost). Per-run stop line
for the attendant's cost polling: 1.5 × headroom = **$2.91**.
Command: `SDLC_RUNS_ROOT=/home/maksim/work/kroker-fleet-runs-026 uv
run python -m sdlc.cli benchmark smoke --gate-policy hard` from the
frozen checkout.

Launched 2026-11-18 19:27 UTC+1 → bench id
**`bench-todo-api-greenfield-1795026442-a5bc19`** (parent
BenchmarkWorkflow + child GraphWorkflow confirmed Running on Temporal;
one strong cell per the 025 fix (a) matrix). The dispatcher shell
reported a spurious "Exit code 2" ~2 min in — verified FALSE: the CLI
process (PID 596232) is alive and awaiting the parent; its stdout is
block-buffered under redirect, so the log stays empty until completion.
Attendant started 19:32 with `ATTENDANT_COST_STOP=2.91`, ledger at
`/tmp/opencode/026-attendant-smoke.txt`. *(results appended below when
concluded)*

## T042 conclusion — the smoke FAILED on `oracle_all_pass` (2026-11-18 20:03 UTC)

`bench-todo-api-greenfield-1795026442-a5bc19`, wall ≈ 89 min
(18:34–20:03 UTC). Stamp (failed) at the checkout's
`runs/ops/smoke/ec3f128f1440de5957824f65b6658f32bc302db2.json`:
`passed=false, failed_conditions=[oracle_all_pass]`. The three infra
conditions PASSED: rubric_scores (clarify/architecture judged),
commit_on_records (all 54 records carry `ec3f128f…`),
one_file_per_cell (1/1). **Measured judge cost $1.4961** (54-record
scan; research $0.6395, architecture $0.3974, plan $0.1170, clarify
$0.0295, stage judging the rest) vs $1.94 expected / $2.91 stop —
under expectation. z.ai flat; the earlier "Exit code 2" on the
dispatcher shell was a monitoring artifact (the CLI process ran to
completion; true exit 1 = the failed smoke check).

**Classification: CASE FAILURE — agent behavior inside task
execution, the pre-registered always-case category.** Evidence:

- NOT infra: no host/container error outside task execution; every
  stage produced valid artifacts; gates serviced end-to-end (merge
  gate reached, deploy PASS, cell PASS).
- NOT a 026 harness regression, three independent proofs: (1) the
  case file is byte-identical between the fleet commits (`git log
  ce3a36f8..ec3f128f -- benchmarks/cases/todo-api-greenfield/` is
  empty); (2) the validator execution path is unchanged
  (`run_test_suite` runs `create_subprocess_shell(test_cmd)` at BOTH
  commits — T015's diff touches only the return path and adds the
  lint ride-along, which "never touches tests_passed"); (3) the NEW
  per-task lint ran and never voted — `T1-qa.json` carries
  `lint: {state: measured, introduced: []}` and no failed record's
  `failure.checks` contains `lint`.
- What actually failed: the QA agent's authored validation commands.
  T1 attempts 1–2: a malformed heredoc — the terminator line was
  written `PY && grep -q …` (a terminator must be bare `PY`), so bash
  never closed the heredoc and Python received the shell line as
  line 8 → SyntaxError (captured verbatim in `T1-qa.json`); the
  analyzer even verified the crashed checks pass directly against the
  materialized diff, yet `tests_passed=false` burned the attempts.
  T1 attempt 0 was a legitimate diff gap (requirements files absent).
  T3 attempts 0–2: the dev's code passed the REAL functional suite
  every attempt (73→75 pytest green, "all nine assertions
  satisfied"), but a QA-authored auxiliary route-audit script crashed
  (a=0) or mis-counted FastAPI's route table (grouped
  `@app.api_route(methods=[…])` objects ≠ "exactly five routes",
  a=1/a=2) — three attempts burned on the audit, not the code.
  Both tasks escalated at attempts=3; the attendant
  approved-to-proceed (2 of its 13 interactions, all automated, no
  steering, no idle, no cost-stop). The deliverable lacked working
  CRUD → the FROZEN oracle graded create/list/get_by_id/update/delete
  0.0 and get_missing 1.0.
- The 025 control: the same case, same stage, same execution path at
  `ce3a36f8` authored working validators and passed this oracle 1.0
  (the 025 T023 smoke, zero escalations). The variable is the model's
  authored validator quality — not the harness, not the case, not the
  round's changes.

**Consequences.** Per T042 a case-difficulty failure STOPs for the
owner: NO scored run starts. Mechanically the gate is hard anyway —
`_run_matrix` refuses corpus runs without a passing smoke stamp for
the fleet commit, so Part B cannot proceed at `ec3f128f` until some
smoke passes (owner rules: re-run the smoke as-is ~$1.50 announced,
or amend). First-pass shape for the record: 5/7 tasks first-attempt
pass; T1+T3 consumed 6 failed attempts; 2 escalations.

Evidence hygiene: the failed smoke's run dir is QUARANTINED out of
the runs root, labeled, unscored —
`/home/maksim/work/kroker-fleet-runs-026-evidence/case-smoke-1-benchmarks`
+ `case-smoke-1-pipeline` (kept whole: records, events, evidence,
summary); the runs root is clean again (benchmarks/ empty). The
scratch repo `scratch-repos-026/todo-api-greenfield` carries the
run's branches beside its clean `main` (unique run-id prefixes; the
025 repos accumulated runs the same way). The failed stamp stays in
the checkout (gitignored `runs/`).

## T043 — ceiling re-announce (recorded at the halt)

Smoke measured **$1.4961** ≤ $1.94 × 1.5 = $2.91 → **no
re-derivation; the ceiling stands**: judge **$13.95** + research
**$1.00**; per-run stops cat-cafe $3.00 / readtime $1.73 / geotext
$1.91 / lice $1.40; smoke stop $2.91. Cumulative 026 spend: **$1.50**
(all of it this smoke) / $13.95 — $12.45 headroom. No spend of any
kind proceeds past this halt without the owner's ruling.

## Owner ruling + smoke re-run announcement (2026-11-18, ~20:4x UTC)

Option (a) ruled: **re-run the smoke as-is at the frozen commit
`ec3f128f`**. Rationale on record: the 025 control passed this exact
case/path at oracle 1.0 — the failure was validator-authoring
variance, not machinery. **SPEND ANNOUNCEMENT: smoke attempt 2,
expected ~$1.50, stop line $2.91** (1.5 × the $1.94 base expectation);
cumulative after attempt 1: $1.4961 / $13.95. **NEW GUARD (owner):**
a second smoke failure in the same case-difficulty mode halts for the
owner — twice is a pattern, not variance. The recurrence note
(QA-authored validators breaking fix loops, 6/21 attempts) is a
candidate triage class; every scored run is watched for it and notes
any occurrence. Otherwise: stamp → ceiling re-derivation → scored
runs with per-run announcements. The attempt-1 failed stamp is
preserved at `case-smoke-1-failed-stamp.json` (evidence dir).
