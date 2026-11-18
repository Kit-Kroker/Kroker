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
