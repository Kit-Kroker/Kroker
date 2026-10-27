# Implementation Plan: glm-5.2 Arm Retirement (round 019)

**Branch**: `019-glm52-arm-retirement` | **Date**: 2026-10-27 | **Spec**: [spec.md](spec.md) | **Base**: `6ba483a6`

**Status**: Reviewer-approved (plan checklist, pass 2, 2026-10-27).
- **Pass 1**: fixes-needed with 3 gaps: the lice record shape after the
  online re-label, an ambiguous SC-001 sweep condition, and no validation
  for FR-010. All were folded in.
- **Pass 2**: approve. Two cosmetic nits were fixed after approval.
- **Record**: [checklists/plan.md](checklists/plan.md).

**Input**: [spec.md](spec.md). GATE 1 cleared on 2026-10-27 with all
defaults (see the spec's Rulings). Scope: user stories 1 to 3, FR-001 to
FR-011, SC-001 to SC-006.

**Design artifacts**:
- [research.md](research.md): decisions D-1 to D-9, each checked in the
  tree;
- [data-model.md](data-model.md): the case and record field changes, and
  the staleness rule;
- [contracts/corpus-status.md](contracts/corpus-status.md): the
  `benchmark corpus` stale column contract and the re-label output
  contract;
- [quickstart.md](quickstart.md): how to validate.

**Consults**:
- advisor `D:\own\Kroker\.workspace\tmp\advisor-019-1.md`, which added two
  spec corrections, folded in as FR-003 and FR-006 amendments;
- skeptic `D:\own\Kroker\.workspace\tmp\skeptic-019-1.md`. L3 (expected
  verdicts) and L2 (no row flips today) hold. Its L1 confounder, L2 known
  limits and L4 quota risk are recorded in research D-3, D-6 and D-7.
  Nothing is overturned.

`S/` = `src/sdlc/`, `B/` = `src/sdlc/benchmarks/`, `PRIV/` =
`D:\own\sdlc-private-cases\`.

## Summary

The round removes every live declaration of the deprecated
`zai-coding-plan/glm-5.2`.
- **Re-pair eight cases** (seven repo cases plus `PRIV/cases/theatre-box-office`)
  to strong `zai-coding-plan-glm-5.3` and weak
  `zai-coding-plan-glm-5.3-flash`.
- **Move the shipped test role** and its `PipelineConfig` mirror to
  `zai-coding-plan/glm-5.3`.
- **Point the DevEval importer default** at glm-5.3.
- **Re-label every touched acceptance record** with a no-spend
  `benchmark accept`.
- **One small code change (FR-009)**: `benchmark corpus` treats a record
  whose separation arms no longer match the case's arms as stale, built
  RED-first.

No run record changes. No paid run is launched. The corpus tally goes from
1 of 8 to 0 of 8, and that drop is the expected result.

## The rules every task is checked against

1. **Run records are read-only.** Nothing under `D:\own\Kroker\runs` is
   modified, moved or deleted. Step 0 writes `baseline-records.sha256`,
   which is re-checked before the closing commit. Re-labels run with the
   runs root mounted **read-only** (D-5).
2. **No paid run, no model call.** No task starts a benchmark or pipeline
   run. `benchmark accept` runs online (it reads stored records) but calls
   no model.
3. **RED first for code.** FR-009 and FR-004 each start with a failing test,
   committed together with the fix (no red commits, 006 precedent). The
   RED run's output is pasted into the task report.
4. **Edit, then accept, then compare.** No `acceptance.yaml` is committed
   unless its printed verdict and reason match the D-3 table (SG-2).
5. **Main-branch defects go to the bug crew** (user ruling 2026-10-17). A
   defect found outside this round's items stops the task and is reported.
6. **Commits**: `git commit -F <file>`, one path per `git add` argument,
   subject and body only, no attribution trailers. Private-store edits are
   committed in `PRIV/`, never here.

## Technical Context

**Language/Version**: Python 3.13 (Pydantic v2). YAML config edits.

**Primary Dependencies**: existing only. No change to `pyproject.toml` or
`uv.lock`.

**Storage**:
- case config `benchmarks/cases/*/case.yaml` and `PRIV/cases/*/case.yaml`;
- acceptance records `<case>/acceptance.yaml`, rewritten by accept;
- run records `D:\own\Kroker\runs\benchmarks\**`, read-only.

**Testing**: in a throwaway container from `kroker-dev:latest` with the
worktree at `/app` (D-5; quickstart §1).
- `uv run pytest` (fast tier);
- `uv run pytest -m temporal tests/replay` at step 0 and after the test
  role flip;
- `ruff check`, `ruff format --check`, `mypy`;
- host: `python scripts/check_file_size.py`.

**Target Platform**: CLI (`benchmark accept`, `benchmark corpus`) and the
worker's boot-time registry mirror.

**Performance Goals**: none. Each accept is dominated by its local oracle
reference and floor runs.

**Constraints**:
- The live `kroker-kroker-dev-1` binds the main tree and is **not**
  rebound, because run infrastructure is the user's call.
- `B/corpus.py` is 196 lines and grows by about 10.
- `tests/test_benchmark_corpus.py` is 474 lines and grows by about 90.

**Scale/Scope**:
- 2 modified source files (`B/corpus.py`, `B/importers/deveval.py`), plus
  `S/core/models.py` (one string);
- 1 registry file (`agents/test/agent.yaml`);
- 7 repo `case.yaml` and 7 `acceptance.yaml`, plus 2 files in `PRIV/`;
- 5 test files modified (`test_benchmark_corpus.py`,
  `test_golden_case_loads.py`, `test_agents_registry.py`,
  `test_registry_mirror.py`, `test_deveval_importer.py`) plus
  `tests/conftest.py`;
- docs: `BENCHMARK.md`, `README.md`, the `benchmarks/config.yaml` comment.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template, so no
constitution gate applies (016 and 017 precedent). The binding rules are
the root `AGENTS.md` and `S/core/AGENTS.md`.

| Rule | Status |
|---|---|
| Cross-stage calls banned | Not touched. All code is in `B/` (a non-pipeline domain) and `core/` config. |
| Producer owns its artifacts | Holds. `PipelineConfig` stays in `core/` (config). The staleness rule stays in `B/corpus.py` beside the oracle rule. |
| Behaviour and clauses change in one diff | Holds. `BENCHMARK.md` gains the break marker and the staleness sentence in the same commits as the case and code edits (Steps 1 and 4). No stage contract (`<stage>.md`) describes the test role's model. |
| 1000-line ceiling | `B/corpus.py` 196 → about 206. `tests/test_benchmark_corpus.py` 474 → about 565. `BENCHMARK.md` 927 → about 955. Root `*.md` is covered by the ceiling, so step 6 keeps the marker compact and checks it is ≤ 1000. |
| `S/core/AGENTS.md` | Read before step 2. The edit is the documented mirror pair ("change one, change both", `models.py:368–372`). |
| Registry boot mirror | `agents/test/agent.yaml` and `PipelineConfig` change in one commit with the `conftest.py` fixture (D-7). |
| Replay safety | No workflow code changes. The default `PipelineConfig` value changes, and workflows build it when no config is passed, so the replay gate runs after step 2 (SG-5). |

No violation, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/019-glm52-arm-retirement/
├── spec.md
├── plan.md                    # this file
├── research.md                # D-1..D-9
├── data-model.md
├── quickstart.md
├── contracts/corpus-status.md
├── checklists/requirements.md
├── tasks.md                   # /speckit-tasks
└── written during execution: baseline.md, baseline-records.sha256, verification.md
```

### Source Code (touched)

```text
src/sdlc/benchmarks/corpus.py              # FR-009 arm-drift staleness
src/sdlc/benchmarks/importers/deveval.py   # FR-004 models default
src/sdlc/core/models.py                    # FR-003 PipelineConfig test-role mirror
agents/test/agent.yaml                     # FR-003
benchmarks/cases/{cat-cafe-monitoring,deveval-geotext,deveval-readtime,deveval-lice,
  deveval-hone,deveval-particle-swarm-optimization,deveval-stocktrends}/{case,acceptance}.yaml
benchmarks/config.yaml                     # stale judge comment
BENCHMARK.md, README.md
tests/test_benchmark_corpus.py, tests/test_golden_case_loads.py,
tests/test_agents_registry.py, tests/test_registry_mirror.py,
tests/test_deveval_importer.py, tests/conftest.py
PRIV/cases/theatre-box-office/{case,acceptance}.yaml   # separate repo, separate commit
```

**Structure Decision**: existing layout. No new module.

## Steps (the order tasks.md will follow)

0. **Pre-flight (no commit except the spec artifacts).**
   - Commit the spec, plan, research, data-model, contracts, quickstart and
     checklist, plus the `CLAUDE.md` SPECKIT plan pointer (already edited)
     and `.specify/feature.json`.
   - Re-probe the catalog (SG-6).
   - Write `baseline-records.sha256` (D-9).
   - Write `baseline.md`: each touched case's current verdict, reason,
     note, separation means and run ids from `git show HEAD:`, plus the
     `benchmark corpus` output, the fast-tier result and the replay-gate
     result, both at base.
1. **FR-009, RED to GREEN.**
   - Add the seven tests from contract §1 to
     `tests/test_benchmark_corpus.py` and run them RED.
   - Implement the rule in `B/corpus.py` (data-model §3) and run GREEN.
   - Add one `BENCHMARK.md` sentence on staleness causes and the two known
     limits.
   - Commit.
2. **FR-003, the test role.**
   - Change `agents/test/agent.yaml`, `S/core/models.py:375`, the
     `tests/conftest.py` fixture, `tests/test_agents_registry.py` and
     `tests/test_registry_mirror.py`.
   - Run the fast tier and the replay gate.
   - Commit.
3. **FR-004, the importer default.**
   - RED assertion in `tests/test_deveval_importer.py` that the default
     `models` is `["zai-coding-plan/glm-5.3"]`.
   - Change `B/importers/deveval.py:228`.
   - Commit.
4. **FR-002/005/006/007, the repo case re-pair and re-label.**
   - Per case: capture the old record (Step 0 did it), rewrite `case.yaml`
     (data-model §1) with the dated FR-006 comment, run `benchmark accept
     <case>` in the D-5 container, check against D-3 (SG-2, SG-3).
   - Update `tests/test_benchmark_corpus.py:18–26, 100–125` and
     `tests/test_golden_case_loads.py:44–50` to the new arms, fixing the
     "base cell id from `models:`" comments (D-2).
   - Run `benchmark corpus`: the tally must be 0 of 8 and no row stale.
   - One commit with all seven cases, their records and the two tests.
5. **Private case (Q2).**
   - Same loop for `PRIV/cases/theatre-box-office`, with
     `SDLC_PRIVATE_CASES_ROOT=/srv/private-cases`.
   - Commit in `PRIV/` (subject `R019: re-pair theatre-box-office to
     glm-5.3 / glm-5.3-flash`).
   - Re-run this repo's `tests/test_private_leak.py`, which must stay
     green.
6. **FR-010/011, docs and the follow-up card.**
   - `BENCHMARK.md` break marker: date, cause, old and new pair, a per-case
     old → new verdict table, tally 1 → 0 of 8, the skeptic L1 confounder,
     and the test role change.
   - README `--role-model` example → `zai-coding-plan/glm-5.3`.
   - `benchmarks/config.yaml` judge comment, corrected to the actual
     `anthropic:claude-sonnet-5` rationale.
   - The follow-up card
     `D:\own\Kroker\.workspace\tasks\2026-10-27-r019-reprove-separation-reruns.md`
     carries the exact `benchmark run --case <c> --all-arms` commands for
     the four separable cases, both arms on one commit, n ≥ 3 each. It also
     covers the dashboard-mock refresh (out of scope here). It is not
     executed.
   - Commit (the card is outside git, in `.workspace`).
7. **Close.**
   - Manifest re-check (SG-1).
   - SC-001 sweep (quickstart §5).
   - Fast tier, replay gate, ruff, ruff format check, mypy, file-size
     check.
   - Write `verification.md` (requirement → evidence; logged reference and
     floor count drift).
   - Closing commit.

## Stop-guards

On fire: stop, leave the tree as it is (no fix-forward), and report to the
orchestrator.

| ID | Fires when |
|---|---|
| SG-1 | Any `baseline-records.sha256` line mismatches, or a file appears or disappears under `runs/benchmarks`. |
| SG-2 | A re-label prints a verdict or reason different from the D-3 table, or `separation.strong.arm` is not `zai-coding-plan-glm-5.3`, or the strong `run_ids` are non-empty. Restore the file (`git checkout -- <path>`) before stopping. |
| SG-3 | A re-label's `reference.detail` or `floor.detail` starts with `oracle environment failed`, or a check has `tests_total == 0`. One rerun is allowed. If it happens a second time, stop. |
| SG-4 | The fast tier shows a failure that is not in `baseline.md` and is not one of the planned test edits. |
| SG-5 | The replay gate is red after step 2 when it was green at step 0. |
| SG-6 | The catalog re-probe shows `glm-5.3` or `glm-5.3-flash` deprecated or missing. Q0 is then re-gated. |
| SG-7 | Any step would need a model call, a benchmark or pipeline run, or a change to live run infrastructure (rebinding `kroker-dev`, the compose worker). |
| SG-8 | A defect on main outside the round's items (rule 5). |

## Runbook

The pre-flight and re-label container command is in quickstart §1. It is
the only container started.

## Complexity Tracking

Empty: no violation.
