# Benchmark record inventory (004 T007, FR-012 / SC-005, ruling A3)

Read-only research artifact, produced 2026-10-01 on branch
`004-model-forwarding-single-retry`. Method per [research.md R9](research.md)
and the row schema in [data-model.md](data-model.md) — `location |
bench_run_id | case | arm | role | labelled_model | answering_model |
evidence`. No benchmark was re-run, no record or label was edited, no
history was rewritten.

**Operator confirmation (2026-10-01, GATE 2, relayed by the orchestrator):**
no other machines, container volumes or external stores hold benchmark
records; this checkout's locations (rows 1, 2 and 4 below) are the complete
set.

A record is **affected** when a proposer role ran under `--role-model`, an
arm `role_models` entry for a proposer role, or an arm `default`. **Result:
no affected records exist.** No benchmark record exists at all — no
`bench_run_id` was ever written on this machine.

| location | bench_run_id | case | arm | role | labelled_model | answering_model | evidence |
|---|---|---|---|---|---|---|---|
| `benchmarks/experiments/` (checkout + `git log --all -- benchmarks/experiments`) | — | — | — | — | — | — | none found: holds `.gitkeep` only; the single commit touching the path (`66a0ec5`) added exactly that file — no record was ever committed |
| `runs/benchmarks/` (default root; `SDLC_BENCHMARKS_ROOT` unset in the shell, `.env`, `.env.example`, `pyproject.toml`; default is `runs/benchmarks` per `src/sdlc/benchmarks/recorder.py:11,24`) | — | — | — | — | — | — | none found: the directory does not exist; `find runs -name records.jsonl` is empty (`runs/` holds `bf-e2e-*`/`bf-intake-*` pipeline E2E exports, `board.sqlite3`, `local/sessions/` — none is a benchmark record) |
| benchmark scratch area `D:\srv` (top-level listing only, per R9) | — | — | — | — | — | — | none found: top level holds `scratch-repos/` only; not walked |
| case and arm configs, `git log -p --all -- benchmarks/cases` | — | — | — | — | — | — | none affected: the only arm configs ever committed set harness roles only (`dev`/`test`/`devops`); no commit ever set an arm `default` (pickaxe `-G"^\s+default:"` empty). The two walked configs are quoted below |
| external record stores | — | — | — | — | — | — | none exist (operator confirmation, 2026-10-01, quoted above) |

## Walked arm configs (evidence for row 4)

1. Commit `d0a4b06` — `benchmarks/cases/crew-probe/case.yaml` (on main;
   the only arms-bearing case in main's history):

   ```yaml
   arms:
     - name: crew-glm-5.3
       role_models:
         dev: zai-coding-plan/glm-5.3
         test: zai-coding-plan/glm-5.3
         devops: zai-coding-plan/glm-5.3
   ```

   `dev`/`test`/`devops` are `HARNESS_ROLES`; no proposer role and no
   `default` — no cell of this arm can produce an affected record.

2. Commits `cd7de66` → `4fe507f` — `benchmarks/cases/herdr-probe/case.yaml`
   (only on the unmerged branch `feat/e-87-herdr-harness`; the path never
   existed on main). Introduced as:

   ```yaml
   arms:
     - name: herdr-opus-5
       role_models:
         dev: herdr:claude-opus-5
         test: herdr:claude-opus-5
         devops: herdr:claude-opus-5
   ```

   `4fe507f` relaxed the same harness-only arm (dropped the `herdr:`
   provider-prefix trick; comments only besides). Harness roles only, no
   proposer role, no `default` in either state.

## Verdict

Zero affected records: no benchmark record was ever written on this
machine, and no committed case/arm config — on any ref — has ever set a
proposer role model or an arm `default`. There is nothing to re-run,
re-label or rule on individually; pre-004 benchmark-record caveats in
`BENCHMARK.md` (T036) can state that no record predating the fix carries a
mislabelled proposer model.
