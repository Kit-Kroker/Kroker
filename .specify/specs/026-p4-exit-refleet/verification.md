# 026 verification

## §026-A (Part A)

> Assembled incrementally; T027 appends the full battery, the T008
> baseline, the T024 summary and the red→green ledger.

### T018 — the "autofix alone" offline conversion read (no model calls)

Method (read-only on the 025 evidence roots; every tree worked on a
`mktemp -d` copy under `/tmp/opencode/t018-*`, the scratch repos and the
025 runs root untouched):

1. `git -C <scratch-repo> archive <surviving integration branch> | tar -x -C $(mktemp -d)`
2. before: `ruff check --statistics --exit-zero --no-cache .`
3. the T013 autofix command, tree-wide for this read:
   `ruff check --fix --force-exclude --exit-zero --no-cache -- .`
4. after: `ruff check --statistics --exit-zero --no-cache .`

ruff 0.16.9 (the repo venv's), each tree's own configuration resolution
(the deveval cases carry richer rule selects than the default set —
UP/RUF/PERF/PLW/SIM/TRY/DTZ/EXE appear).

| Case (025 run) | before | after T013 autofix alone | spec H3 expectation |
|---|---|---|---|
| cat-cafe-monitoring (`…-1794967369-e94f43`) | 22 | **4** | 22→4 ✓ |
| deveval-geotext (`…-1794967369-ea94f8`) | 24 | **15** | 24→15 ✓ |
| deveval-lice (`…-1794958404-f74c98`) | 74 | **42** | 74→42 ✓ |
| deveval-lice, second branch (`…-1794980735-e87339`, secondary read) | 43 | 36 | — |

Reading: safe autofix alone removes 82 % (18/22), 38 % (9/24) and 43 %
(32/74) of the merge-blocking diagnostics on the three H3 trees; what
remains is exactly the non-safe-fixable residue (PERF102/PLW1510/TRY004
on cat-cafe; UP031/PLW1510/F401-in-`__init__`/UP022 on geotext;
RUF059/UP031/PLW1510/SIM117/UP030/EXE001/DTZ005 on lice). The per-task
scoped lint + fix loop (T014–T016) is what addresses that residue;
autofix is the floor, not the cure. Evidence dirs preserved:
`/tmp/opencode/t018-catcafe.*`, `/tmp/opencode/t018-geotext.*`,
`/tmp/opencode/t018-lice1.*` (primary), `/tmp/opencode/t018-lice2.*`
(secondary).

### 025 baseline (T008, the $0 re-score — Part B entry condition)

Command (copy, never the 025 root itself):

```
D=$(mktemp -d -p /tmp/opencode t008-XXXX)   # -> /tmp/opencode/t008-4DJV
cp -a /home/maksim/work/kroker-fleet-runs-025/. "$D"/
SDLC_RUNS_ROOT="$D" uv run python -m sdlc.cli benchmark score --all
```

Outputs written under `$D/benchmarks/_all/score/` (report.md,
sc-rollup.{json,html}, heatmap/grid/gate-oracle, per-case matrices);
the rollup, read from `sc-rollup.json`:

| criterion | rate | n |
|---|---|---|
| SC-1 | 0.00 | 6 |
| SC-1-strict | 0.00 | 6 |
| SC-2 (shipped) | n/a | 1 |
| SC-2-all | n/a | 4 |
| SC-3 | 0.385 | 13 |
| SC-3-non-lint | 0.385 | 13 |
| SC-3-lint | n/a | 0 |
| SC-4 | n/a | 4 |
| SC-6 | 1.00 | 15 |
| SC-6-advisory | 0.067 | 15 |

- commits: `['ce3a36f88d08e54892e8a72c96ceb6165ba4bc13']` — one commit,
  read by the rollup.
- roots line (T006): `records: …/benchmarks (runs_root); summaries:
  …/pipeline (runs_root); 4 of 6 scored runs summarized; no-summary:
  bench-deveval-lice-1794980735-e87339/…: terminated,
  bench-deveval-readtime-1794957781-bccb20/…: crashed; smoke excluded:
  bench-todo-api-greenfield-1794953137-1ba84e/…`
- evidence tier: weak (SOFT: no gate asked a human unless it escalated);
  summary_runs 4, pre-012 records 0.

Every quickstart expectation asserted and met: 4/6 summarized; the
readtime crash and the lice termination named as the no-summary pair;
smoke excluded; the single 025 commit; SC-1/SC-1-strict 0.00 (n=6);
SC-2-all n/a on 4 measured; SC-3 0.385 (n=13) with the new partition
reading non-lint 0.385 (n=13) and lint n/a (n=0) — every 025 loop is
legacy (`failure is None`), which is the before-half of this round's
T013–T016 change. No mismatch; no STOP. This is the baseline T050's
deltas read against.
