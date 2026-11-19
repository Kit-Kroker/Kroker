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

## T042b — SMOKE PASS (attempt 2, 2026-11-18 20:10–21:43 UTC)

`bench-todo-api-greenfield-1795032560-32ae46`: **smoke: PASS
ec3f128f1440de5957824f65b6658f32bc302db2** — stamp `passed=true,
failed_conditions=[]` at 21:43:13Z; the attempt-1 failed stamp is
preserved in the evidence dir. 49 records, wall ≈ 93 min, **measured
judge $1.3241** (research 0.5908, architecture 0.3578, handoff 0.1002,
analyze 0.0950, plan 0.0649, review 0.0428, clarify 0.0369, qa 0.0356)
vs $1.50 announced / $2.91 stop — under. Attendant: 12 interactions,
all automated, no steering, no idle, no cost-stop. Oracle **6/6 at
1.0**. The run dir stays in the runs root (counted in spend, excluded
from the scored set by role, B.9).

**Recurrence watch (mandated per-run note):** the candidate class —
QA-authored validators breaking fix loops — fired AGAIN on T1 (3
attempts + escalation): the validator's probe crashed on
`anyio.__version__` (AttributeError; anyio 4.16 exposes no module
attribute; the analyzer records "Assertions 1-2 MET … validation-
script artifact, not a requirements.txt defect"). Distinct from T3,
which is the machinery WORKING: review caught a real defect (HEAD
/todos/{id} falls through to the DELETE branch) and the NEW per-task
lint voted its first genuine findings (committed `__pycache__`
bytecode → `checks=['qa','review','lint']` at a=0), resolved at a=1.
T5's loop began with an empty diff (a=0; the analyzer flagged the
unsubstantiated tests_passed=true claim), 3 attempts + escalation.
Loop shape: 3 loops, 1 resolved; 2 escalations; no lint-only loop
(T3's failed record is mixed, not `['lint']`). Two smokes, two T1
validator-authoring failures — the candidate class is now 2-for-2 on
this task; watched per scored run.

## T043 — ceiling re-announce (after the passing smoke)

Smoke-2 measured **$1.3241** ≤ $1.94 × 1.5 = $2.91 → **no
re-derivation; the ceiling stands**: judge **$13.95** + research
**$1.00** (EXA, cat-cafe only among scored runs). Per-run stops:
cat-cafe $3.00, readtime $1.73, geotext $1.91, lice $1.40.
**Cumulative: $2.8202 / $13.95 → $11.13 headroom.** Per-run
expectations for the announcements (smoke-2's buckets + the 025
derivation): cat-cafe ≈ stage 0.34 + research judge 0.59 + 5 rubrics
× ~0.308 ≈ **$2.50–2.90** (025 derived 2.862); deveval runs
(no rubrics, no research) ≈ stage judging **$0.34–0.47** (smoke-2
measured 0.3385; 025 derived 0.464).

## SCORED RUN 1 — ANNOUNCEMENT (cat-cafe-monitoring, T044)

**Run 1: cat-cafe-monitoring, arm zai-coding-plan-glm-5.3, fleet
commit ec3f128f1440de5957824f65b6658f32bc302db2 (frozen). Expected
judge ~$2.90 (025-derived; smoke-2-derived $2.50), per-run stop
$3.00, EXA research line $1.00 applies. Spend so far $2.82 / $13.95;
ceiling left $11.13.** Command: `SDLC_RUNS_ROOT=… uv run python -m
sdlc.cli benchmark run --case
benchmarks/cases/cat-cafe-monitoring/case.yaml --arm
zai-coding-plan-glm-5.3 --gate-policy hard` from the frozen checkout,
attendant servicing (stop $3.00). Launched 2026-11-18 ~21:5x UTC.
*(No commit lands between now and the last scored run — the window is
open; preflight updates accumulate uncommitted.)*

## Scored run 1 — cat-cafe-monitoring (2026-11-18 21:52 → 2026-11-19 00:37 UTC)

`bench-cat-cafe-monitoring-1795038284-ae394b`: full pipeline, **cell
PASS, merge verdict REVISE (non-blocking — `lint_clean` did NOT
block; 025's cat-cafe died on lint_clean alone), deploy PASS**. The
frozen oracle graded **0.6389 FAIL** (15 task-oracles, mean 0.698:
act_* mostly 1.0, mon_movement 0.0, mon_history_window 0.0,
mon_detail 0.333, telemetry_ingest 0.5). Rubrics: research 0.75,
clarify 0.93, architecture 0.86, plan 1.0, per-task qa 0.75–1.0 (one
0). **Class: case failure** (oracle miss — every gate passed and the
work deployed; the 025-F5 shape). 87 records, wall ≈ 2 h 45 m.
**Actual $1.5781** vs $2.90 expected / $3.00 stop — well under; EXA
fetch-budget within the $1.00 bound. **Cumulative $4.3983 / $13.95 →
$9.55 headroom.** Loops: **5, all 5 resolved** (T01 a2, T02/T04/T05
a1, T06 a2 — first-pass 6/11); T01's first failure carried the round's
first lint-inclusive mixed record `['tests','qa','review','lint']`
(not lint-only). **Zero escalations**; attendant 10 interactions, all
automated, no steering, no idle, no cost-stop. **Recurrence watch:
CLEAN** — no validator-authoring artifacts in any failed code/qa
summary (loops failed on real tests/qa/review findings). Kept in the
runs root, scored.

## SCORED RUN 2 — ANNOUNCEMENT (deveval-readtime, T045)

**Run 2: deveval-readtime, arm zai-coding-plan-glm-5.3, fleet commit
ec3f128f1440de5957824f65b6658f32bc302db2 (frozen). Expected judge
~$0.47 (025-derived 0.464; smoke-2-derived 0.34), per-run stop $1.73.
No rubrics, no research (EXA n/a). Spend so far $4.40 / $13.95;
ceiling left $9.55.** Sequential per the brief (runs 1+2 alone).
Launched 2026-11-19 ~00:4x UTC.

## Scored run 2 — deveval-readtime (2026-11-19 00:4x → 03:16 UTC)

`bench-deveval-readtime-1795048725-984945`: the round's first fully
shipped run — **architecture PASS (the 025 run-1 crash mode did not
recur), merge PASS, deploy PASS, cell PASS**. Frozen oracle **0.167
FAIL** (7 task-oracles: plain_text/html/markdown 0.0,
custom_wpm_rate 0.667, input_validation 0.5, boundary/arithmetic 0.0)
— below 025's readtime repeat (0.25). **Class: case failure**
(shipped, oracle miss). 73 records. **Actual $1.0864** vs $0.47
expected — 2.3×, under the $1.73 stop, concluded before any cancel
point (the 025-geotext shape: escalation retries). **Cumulative
$5.4847 / $13.95 → $8.47 headroom.** Loops: **5, 4 resolved**
(T-02/T-03/T-04/T-10 at a1; T-07 unresolved at 3 attempts → 1
escalation, approved); first-pass 5/10. Attendant: 13 interactions,
all automated, no steering, no idle, no cost-stop.

**SC-3-lint's first lint-only loops ever:** T-02 and T-03 failed with
`checks=['lint']` EXACTLY and both RESOLVED at a=1 — per-task lint
caught introduced findings and the dev fixed them inside the loop
(025: lint surfaced only at merge and blocked 3/3 merge-reaching
runs). The T013–T016 design intent, observed live.

**Recurrence watch: FIRED on T-07** (attempts 1–2): "harness flag
tests_passed=false contradicts the embedded pytest log ('16 passed in
0.13s', failing_tests empty)" — the validator chain's verdict
discrepancy masked green tests and burned the loop's last two
attempts. Same family as the smoke T1 failures (authoring artifacts,
not diff defects). Third occurrence across three runs — the candidate
class is now a pattern in the data, watched per scored run and
recorded for T050's triage. (T-04 a0 is NOT the class — a genuine
contract miss, 25s vs 24s under the diff.)

## SCORED RUNS 3+4 — ANNOUNCEMENT (concurrent, per the brief's ≤2 window)

**Run 3: deveval-geotext, arm zai-coding-plan-glm-5.3, fleet commit
ec3f128f… (frozen). Expected ~$0.47, per-run stop $1.91.** **Run 4:
deveval-lice, same arm/commit. Expected ~$0.47, per-run stop $1.40.**
No rubrics, no research (EXA n/a). Spend so far $5.48 / $13.95;
ceiling left $8.47 (both runs draw from it). Two attendants, one per
run, each with its own stop and ledger. Launched 2026-11-19 ~03:2x UTC.

Run 4 dispatch note (for the record, $0): the first lice launch
escaped the frozen checkout (a compound-shell slip — the `cd` bound
only to the first background job) and the corpus-run guard REFUSED it
pre-dispatch from the primary ("tree is dirty; smoke check refuses
uncommitted changes (commit: 78847648…)"). No workflow, no spend —
the guard worked as designed. Relaunched correctly:
`bench-deveval-lice-1795058418-99ee8c` (both workflows Running,
~5 min behind geotext). Two attendants live: geotext stop $1.91,
lice stop $1.40.

## Scored run 3 — deveval-geotext (2026-11-19 03:2x → 05:34 UTC)

`bench-deveval-geotext-1795058243-31bec2`: **shipped end-to-end —
architecture PASS, merge verdict REVISE (non-blocking; `lint_clean`
did not block), deploy PASS, cell PASS.** Frozen oracle **0.600
FAIL** (5 task-oracles: country/nationality extraction 1.0, city 0.5,
mention_counts 0.5, reference_data_loading 0.0) — far above 025's
geotext (0.222). **Class: case failure** (shipped, oracle miss). 61
records. **Actual $1.1655** vs $0.47 expected — 2.5×, under the $1.91
stop, concluded before any cancel point (the escalation-retry shape).
**Cumulative $6.6502 / $13.95 → $7.30 headroom.** Loops: **3, all 3
resolved** (T-06 a2, T-07 a1, T-08 a2); first-pass 5/8; **zero
escalations**; attendant 13 interactions, all automated, no steering,
no idle, no cost-stop. **Lint votes again:** T-07 is the round's
third lint-ONLY loop (`['lint']`, resolved at a1); T-08's middle
attempt failed lint-only inside a mixed loop. **Recurrence watch:
CLEAN** — no validator-authoring artifacts. Kept in the runs root,
scored.

## Scored run 4 — deveval-lice (2026-11-19 04:1x → 06:14 UTC)

`bench-deveval-lice-1795058418-99ee8c`: **shipped — architecture
PASS, merge verdict REVISE (non-blocking; `lint_clean` did not
block), deploy PASS, cell PASS.** Frozen oracle **0.000 FAIL** (all 7
task-oracles zero — license_generation, template_variables, …; 025's
lice also graded 0.000: the case remains unsolved on this arm).
**Class: case failure.** 80 records. **Actual $1.4013** vs $0.47
expected (3.0×) — **crossed the $1.40 stop by $0.0013 in the final
minute**: the attendant's 60-s poll fired COST-STOP at 06:13:28Z and
the run closed on its own at 06:14:09Z — no cancel point remained
(and cancelling a concluding run over $0.0013 would have destroyed
it). Disclosed; no further run proceeds without accounting for it.
**Cumulative $8.0515 / $13.95 → $5.90 headroom.** Loops: 4, **2
resolved** (T01 and T10 — **both lint-ONLY, both resolved at a1**;
the round's 4th and 5th lint-only loops), 2 unresolved (T06, T07 at 3
attempts → 2 escalations); first-pass 8/12. Attendant: 14
interactions, all automated, no steering, no idle.

**Recurrence watch: FIRED HEAVILY — the class drove both unresolved
loops.** T06 (all 3 attempts): "ad-hoc `python -c` one-liner failed
with SyntaxError (unterminated string literal)… harness-side probe
artifact only"; T07 (attempts 1–2): "the harness's own malformed
inline check (literal newline inside a single-quoted string)";
T07 a=2: **"Contract test command passed: unittest 62 tests OK (exit
0) — Collector reported tests_passed=false."** Green tests masked by
authoring artifacts, burning 6 attempts across two loops that could
not resolve. Fourth and fifth occurrences (smoke-1 T1, smoke-2 T1,
readtime T-07, lice T06+T07); now materially affecting SC-3, not
just spend. Recorded for T050's triage as its own class.

## SCORED RUN 5 — ANNOUNCEMENT (cat-cafe repeat, T048)

**Run 5: cat-cafe-monitoring (repeat), arm zai-coding-plan-glm-5.3,
fleet commit ec3f128f… (frozen). Expected judge ~$2.90 (run-1
measured $1.58; 025-derived 2.86), per-run stop $3.00, EXA research
line applies. Spend so far $8.05 / $13.95; ceiling left $5.90.**
Launched 2026-11-19 ~06:2x UTC.

## Scored run 5 — cat-cafe-monitoring repeat (2026-11-19 06:2x → 08:42 UTC)

`bench-cat-cafe-monitoring-1795068903-eadec8`: **THE FLEET'S FIRST
FULL SUCCESS — case oracle 1.0, all 15 task-oracles at 1.0** (run 1's
same case: 0.639; 025's cat-cafe: 0.861). Architecture PASS, merge
verdict REVISE (non-blocking), **deploy PASS, cell PASS, oracle
PASS.** 67 records. **Actual $1.6667** vs $2.90 expected / $3.00 stop
— under; EXA within the $1.00 bound. **Cumulative $9.7182 / $13.95 →
$4.23 headroom.** Loops: 2, both resolved (T1 a1; T2 a1 — **the
round's 6th lint-only loop, resolved**); first-pass 7/9; **zero
escalations**; attendant 13 interactions, all automated, no steering,
no idle, no cost-stop. **Recurrence watch: CLEAN.** Same-case variance
read: cat-cafe 0.639 → **1.0** on the repeat (025's variance pair:
readtime 0.036-crash → 0.25-shipped). Kept, scored.

## T049 — run 6 decision

**Run 6 not needed:** 5 scored runs concluded and every one is
SC-2-measured (a `summary.json` sits in each run's pipeline dir; the
026 scorer reads the runs root — the 025 export-path gap is what this
round's T003–T006 fixed). Headroom $4.23 ≥ $1.73 would have allowed
it; the measured-count condition fails. No extension of the
delegation; never exceeds 6.

**THE FREEZE ENDS** (last scored run concluded 08:42:24Z). Commit
window reopens.
