# Feature Specification: glm-5.2 Arm Retirement

**Feature Branch**: `019-glm52-arm-retirement`

**Created**: 2026-10-27

**Status**: Approved. GATE 1 cleared by the user (relayed by the
orchestrator) on 2026-10-27: **all defaults**. See Rulings. Uncommitted by
convention: the round's first task commits it.

## Rulings (GATE 1, user, 2026-10-27)

- **Q0 = A**: strong `zai-coding-plan/glm-5.3`, weak
  `zai-coding-plan/glm-5.3-flash`.
- **Q1 = A**: arm-drift staleness is in scope (FR-009). It is a code
  change, and its tests are written RED first.
- **Q2 = A**: the spec lead edits theatre-box-office in
  `D:\own\sdlc-private-cases` and commits it there, in a separate commit.
- **Q3 = A**: the shipped test role moves to `zai-coding-plan/glm-5.3`.
  `agents/test/agent.yaml` and the `PipelineConfig` mirror change together.
- **Q4–Q11 = R**: every listed case is re-paired to the Q0 pair. The
  glm-5.2 `--variant max` entry is dropped, because the glm-5.3 family
  declares no opencode variants (todo-api precedent).
- **Q12–Q13**: no change.

With these answers the parameterised requirements are bound. No case is
frozen, so FR-001 has no exceptions. FR-007's expected-verdict table
applies as written for Q0 = A.

**Input**: Orchestrator brief for round 019 (2026-10-27): "retire the dead
glm-5.2 arms across the benchmark corpus." Source cards:
`D:\own\Kroker\.workspace\tasks\2026-10-26-corpus-cases-glm-5-2-arm-retirement.md`
(the task) and
`D:\own\Kroker\.workspace\tasks\2026-10-26-glm-5-3-full-429-rate-limit-matrix.md`
(the matrix question). Code references are against branch head `6ba483a6`.

## Context

z.ai marked `glm-5.2` deprecated in the `zai-coding-plan` catalog. opencode
filters deprecated models when it resolves a model, so every run arm
declared on `zai-coding-plan/glm-5.2` dies within about 5 seconds with
`ProviderModelNotFoundError`. Runs 1793006961 and 1793021198 lost 15 of 15
code attempts this way. Eight corpus cases in this repo, one in the private
store, and one shipped pipeline role still declare the model.

Round 017 already moved the smoke case (`todo-api-greenfield`) off glm-5.2
(commits `2e813a28`, `ac58b434`). This round does the same for everything
else, and records what each change does to stored acceptance evidence.

## Verified Facts (hypotheses from the brief, checked in files)

| # | Hypothesis | Finding |
|---|---|---|
| V1 | glm-5.2 is gone from the live catalog | **True, refined.** Worker `kroker-worker-1` `/root/.cache/opencode/models.json` (2026-10-26 17:28) lists seven zai-coding-plan models. Four are `deprecated`: `glm-4.7`, `glm-5-turbo`, `glm-5.2`, `glm-5.2-highspeed`. Three are live: `glm-5.3`, `glm-5.3-flash`, `glm-5.3-highspeed`. The task card's catalog list contradicts itself; this probe replaces it. |
| V2 | The listed cases declare glm-5.2 arms | **True for 8 of 9.** `cat-cafe-monitoring`, `deveval-geotext`, `deveval-readtime`, `deveval-hone`, `deveval-lice`, `deveval-particle-swarm-optimization` and `deveval-stocktrends` each have `weak_arm: zai-coding-plan-glm-5.2`, an arm of that name, and `models: [zai-coding-plan/glm-5.2]`. Only cat-cafe (and the private theatre-box-office) also carries `extra_args_by_model` `--variant max` for glm-5.2. `todo-api-greenfield` is already migrated (only a history comment). `crew-probe` runs glm-5.3 and mentions glm-5.2 only in a history comment. `add-login-greenfield` has no reference. |
| V3 | The private case declares glm-5.2 too | **True.** `D:\own\sdlc-private-cases\cases\theatre-box-office\case.yaml` has the same arm block. Its `acceptance.yaml` is `rejected no_separation` (flash 0.0179 vs 5.2 0.0179). That store is its own git repository (head `8b8c2ea`). |
| V4 | Swapping an arm invalidates the oracle identity link | **False as stated.** `oracle_identity()` (`src/sdlc/benchmarks/oracle_id.py`) hashes only the files under `oracle/`. An arm swap does not change it. What breaks is the **arm link**: `separation()` (`acceptance.py:80`) selects runs by arm name, so stored runs of a removed arm count as `not_comparable`. |
| V5 | A swap makes the acceptance record stale | **False today. This is a gap.** `corpus_status()` (`corpus.py:60`) treats a record as stale only when its `oracle_id` differs from the current oracle. After an arm swap, cat-cafe's `provisional` record (weak arm `zai-coding-plan-glm-5.2`) would still read fresh and still count toward the "1 of 8" tally, even though its case no longer declares that arm. |
| V6 | A re-label needs no model spend | **True.** `benchmark accept <case>` without `--offline` (`cli.py:481`) reruns the reference and floor checks locally, rebuilds separation from the stored run records for the case's *current* `strong_arm`/`weak_arm`, and rewrites `acceptance.yaml`. If an arm has no graded runs, `decide()` returns `not_assessed` ("no strong arm runs" / "no weak arm runs"). No model is called. |
| V7 | Other glm-5.2 references are corpus-only | **False.** The shipped **test role** runs on it: `agents/test/agent.yaml` `model: zai-coding-plan/glm-5.2`, mirrored by the hardcoded `PipelineConfig` default (`src/sdlc/core/models.py:375`). The worker asserts at boot that the two agree. Any pipeline run that does not override the test role sends test tasks to a dead model. Also: the DevEval importer default (`src/sdlc/benchmarks/importers/deveval.py:228`) writes `models: [zai-coding-plan/glm-5.2]` into every newly imported case. |
| V8 | The 429 matrix card is blocked on backoff | **Unblocked.** The backoff the card asked for landed on this branch's base (`dea09d36`, `6ba483a6`: exponential 429/5xx backoff in the single-retry seam). Whether full glm-5.3 now survives a clarify burst has **not** been measured. |

## Scope Decision: the Matrix Question

The matrix question (which strong/weak pair the corpus uses now that
glm-5.2 is gone and full glm-5.3 is quota-starved) is a **hard dependency,
not a deliverable** of this round. It is answered by the user as **Q0 at
GATE 1**. Every per-case answer (Q4–Q13) is written against it. The round
runs no paid probes or reruns to answer it (paid runs are the user's call).
If the user wants Q0 measured before ruling, the round blocks at GATE 1
until that measurement exists, and the measurement is planned outside this
round.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - No case or role declares a dead model (Priority: P1)

An operator launches any corpus case, the smoke case, or a plain pipeline
run. No cell dies on `ProviderModelNotFoundError`, because no live config
declares a deprecated model.

**Why this priority**: Every glm-5.2 cell costs worker time and records a
dead cell. The test-role default (V7) affects pipeline runs outside the
benchmark too.

**Independent Test**: Sweep the live config surfaces (FR-001) for
deprecated zai-coding-plan model ids and load every case through the case
loader.

**Acceptance Scenarios**:

1. **Given** the round has landed, **When** the sweep runs over both case
   roots, `agents/`, the `PipelineConfig` default and the importer default,
   **Then** it finds no glm-5.2 model declaration. History comments are
   allowed.
2. **Given** a re-paired case, **When** it is loaded, **Then** `strong_arm`
   and `weak_arm` name declared arms and are not identical (existing
   `CaseSpec` validation).
3. **Given** the test role was moved (Q3), **When** the worker boots,
   **Then** the registry mirror check passes.

---

### User Story 2 - Acceptance records tell the truth after the swap (Priority: P1)

A reader of `benchmark corpus` sees, for every touched case, a verdict
that matches the case's current arms. No record still counts evidence
from an arm the case no longer declares.

**Why this priority**: The corpus tally (1 of 8) is the round-gating
number for the corpus programme. A silent stale `provisional` would
overstate it.

**Independent Test**: After the swap, run `benchmark accept` (online, no
spend) per touched case, then `benchmark corpus`. Compare each verdict
against the expected table in FR-007.

**Acceptance Scenarios**:

1. **Given** cat-cafe is re-paired, **When** it is re-labelled, **Then**
   its verdict is `not_assessed` and it no longer counts toward the tally.
2. **Given** a case's arms changed and no re-label has run yet, **When**
   `benchmark corpus` runs, **Then** the row shows stale (if Q1 = A).
3. **Given** the swap, **When** the run records under `runs/` are hashed,
   **Then** every hash matches the pre-round manifest. Nothing is deleted
   or rewritten.

---

### User Story 3 - The record of why (Priority: P2)

A later reader finds, in `BENCHMARK.md` and in each touched case, a dated
note: glm-5.2 was retired for catalog deprecation, which separation
evidence was dropped, and what re-proving needs.

**Why this priority**: Old run ids in reports and records still name the
glm-5.2 arm. Without the note they read as live.

**Independent Test**: Read the `BENCHMARK.md` break marker and each case's
note. Each states date, cause, old pair, new pair (or parked/frozen), and
the prior verdict.

**Acceptance Scenarios**:

1. **Given** the round has landed, **When** a reader opens `BENCHMARK.md`,
   **Then** a dated break marker lists every touched case with its old and
   new verdict.

### Edge Cases

- **Flash changes slot.** If Q0 makes `glm-5.3-flash` the weak arm, the arm
  keeps its name and definition. Its stored graded runs then count as
  **weak** evidence for the new pair (same oracle, same role models). Only
  glm-5.2 runs become `not_comparable`. Cat-cafe would re-label to
  `not_assessed` "no strong arm runs" with weak = flash 0.833 (n=1).
- **Flash stays strong, weak slot empty.** `weak_arm` is removed, the case
  keeps one arm, and the re-label gives `not_assessed` "no weak arm runs".
- **Parked cases.** Separation is never assessed for parked cases. A swap
  leaves their verdict at `not_assessed`. They can still run under
  `--allow-parked`, so a dead arm there still fails.
- **Rejected for reference.** `deveval-lice` fails its reference check
  (30/31). `decide()` checks reference first, so its verdict stays
  `rejected reference` whatever the arms are.
- **Private store.** theatre-box-office lives in a separate git repository.
  Its edits commit there, never in this repo. The private-leak tests must
  stay green.
- **Inverted ordering.** geotext scored flash 0.222 below 5.2 at 0.778. A
  re-label drops that inversion evidence along with the 5.2 arm. The
  rejected record's note is the only trace, so FR-006 keeps it in the case
  note.
- **highspeed.** `glm-5.3-highspeed` is live, but it is very likely the
  same model as glm-5.3 served faster. It is not a capability gradient, so
  it is not offered as a weak arm.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001 (sweep surface)**: These are live config: `benchmarks/cases/*/case.yaml`,
  `D:\own\sdlc-private-cases\cases\*\case.yaml`, `agents/*/agent.yaml`, the
  `PipelineConfig.roles` default, the DevEval importer's `models` default,
  and `benchmarks/config.yaml`. After the round, none of them declares
  `glm-5.2` as a model, arm, `models` entry or `extra_args_by_model` key.
- **FR-002 (per-case treatment)**: Each case in V2/V3 gets exactly the
  treatment the user rules at GATE 1 (Q4–Q13):
  - **re-pair**: arms, `strong_arm`, `weak_arm`, `models` and
    `extra_args_by_model` are rewritten to the Q0 pair. The glm-5.2
    `--variant max` entry is dropped. The glm-5.3 family declares no
    opencode variants (todo-api precedent).
  - **retire**: `role: parked` with a dated reason note. The glm-5.2 arm is
    removed as well, so the case never declares a dead model (FR-001).
  - **freeze**: the case is left unchanged apart from a dated stale-catalog
    note. A frozen case is listed by name as an FR-001 exception.
- **FR-003 (shipped test role)**: `agents/test/agent.yaml` and the
  `PipelineConfig` mirror move together to the Q3 model. These tests pin
  the old value and are updated to the new one:
  `tests/test_agents_registry.py`, `tests/test_registry_mirror.py`, and the
  `tests/conftest.py` mirror fixture. These tests pin the old arms on real
  cases and are updated with the re-pair: `tests/test_benchmark_corpus.py`
  and `tests/test_golden_case_loads.py`. This list was amended
  2026-10-27 after the advisor consult. Tests that use `glm-5.2` only as a
  string-grammar literal are left alone.
- **FR-004 (importer default)**: The DevEval importer emits the Q0 strong
  model as its `models` default.
- **FR-005 (re-label, no spend)**: After its case.yaml edit, each touched
  case with an `acceptance.yaml` gets a fresh record from `benchmark accept`
  (online mode, no model calls). The result is committed with the case. The
  round launches no benchmark run.
- **FR-006 (dated notes)**: Each touched case's `case.yaml` carries a
  dated comment. It goes in `case.yaml`, not `acceptance.yaml`, because
  `save_acceptance` rewrites the whole record file on every accept. The comment is dated
  (`2026-10-27` or the landing date) naming the cause (catalog
  deprecation), the old pair, the treatment, and the prior verdict with its
  scores. Examples: "provisional, flash 0.833 vs 5.2 0.472";
  "rejected no_separation, flash 0.222 vs 5.2 0.778 (inverted)".
- **FR-007 (expected verdicts)**: The plan fixes, per case and per ruling,
  the verdict the re-label must produce. Under Q0 = A with all re-paired:
  cat-cafe, geotext and readtime go to `not_assessed`; theatre-box-office
  goes to `not_assessed`; lice stays `rejected reference`; hone,
  particle-swarm and stocktrends stay `not_assessed` (parked). Any other
  re-label result is a stop-and-report, not a fix-forward.
- **FR-008 (records untouched)**: No stored run record is rewritten or
  deleted. glm-5.2 runs stay as history. A sha256 manifest of the case's
  run records is taken before the round and re-checked at close (rounds
  015–017 precedent).
- **FR-009 (arm-drift staleness, if Q1 = A)**: `benchmark corpus` marks a
  record stale when the record's separation arms differ from the case's
  current `strong_arm`/`weak_arm`, exactly as it does for oracle drift.
  Stale records stay out of the tally. RED tests come first.
- **FR-010 (docs)**: `BENCHMARK.md` gains a dated break marker (old pair,
  new pair, per-case old→new verdict, tally before and after). The README
  `--role-model dev=zai-coding-plan/glm-5.2` example and the stale judge
  comment in `benchmarks/config.yaml` (which names `anthropic:glm-5.2` and
  Gemini while the value is `anthropic:claude-sonnet-5`) are corrected.
  History lines that describe past runs stay as written.
- **FR-011 (re-proving is out of round)**: Reruns that would re-prove
  separation are listed as a follow-up card with the exact commands and arm
  names. They are not executed in this round.

### Out of Scope

- Historical artifacts: `.specify/specs/0xx-*` for rounds up to 018,
  `docs/superpowers/**`, `docs/reports/**`, recorded fixtures
  (`tests/fixtures/opencode/*.jsonl`) and baseline hash manifests. They
  record what ran then.
- Proposer-route literals `anthropic:glm-5.2` in tests, the durability
  fixture agents, and docstrings that document the rollback override. The
  provider and catalog for that route are separate from zai-coding-plan.
  Its viability is not this round's question.
- Dashboard illustrative data (`fleet-snapshot.json`,
  `interfaces/dashboard/frontend/src/api/mock/index.ts`,
  `scripts/dump_dashboard_fixtures.py`). Changing them regenerates UI
  fixtures and couples to round 018's open UI branch. They go on a
  follow-up card.
- Measuring glm-5.3's 429 survival under the new backoff (see Scope
  Decision).

### Key Entities

- **Case** (`case.yaml`): role, arms (name → per-role models),
  `strong_arm`/`weak_arm`, `models`, `extra_args_by_model`.
- **Acceptance record** (`acceptance.yaml`): verdict, reason, note,
  oracle_id, reference/floor checks, separation (per-arm run ids, scores,
  means, margin, `not_comparable`), kroker_commit, updated.
- **Run record** (`runs/…/*.jsonl`): arm, oracle_id, status, partial
  credit. Immutable here.
- **Corpus tally**: count of non-stale accepted or provisional corpus cases
  out of 8.

## Open Questions for GATE 1

Every per-case question has a recommended default that follows Q0. "All
defaults" is a valid one-line answer.

**Q0 — Matrix pair (gates everything).** Live candidates (V1): glm-5.3,
glm-5.3-flash, glm-5.3-highspeed.

| Option | Pair | Implication |
|---|---|---|
| **A (recommended)** | strong `glm-5.3`, weak `glm-5.3-flash` | Matches the public ordering. The 429 backoff has landed, but glm-5.3's burst survival is unmeasured, so the first rerun is the proof. Flash scored 6/6 on smoke (T021), so on easy cases the weak arm may saturate and fail to separate. |
| B | strong `glm-5.3-flash`, no weak arm | No paid exposure to glm-5.3. Separation cannot be assessed anywhere until a weak arm exists. Every corpus case re-labels to `not_assessed`. |
| C | cross-provider pair (named by the user) | Real capability gradient. Paid. ADR-6: no `anthropic:` author while the judge is `anthropic:claude-sonnet-5`. Needs its own credential and route checks, which would likely make it a separate round. |
| D | measure first | Round blocks at GATE 1. A paid glm-5.3 probe is planned outside the round. |

**Q1 — Arm-drift staleness in code (FR-009).** A: add it, a small code
change with tests, so future swaps cannot leave a silent fresh record
**(recommended)**. B: no code; rely on FR-005's mandatory re-label in this
round only.

**Q2 — Private store commits.** A: the spec lead edits and commits
theatre-box-office in `D:\own\sdlc-private-cases`, in a separate commit in
that repository **(recommended, round 016 precedent)**. B: leave it to the
orchestrator or user.

**Q3 — Shipped test role (V7).** A: `zai-coding-plan/glm-5.3`, the same as
dev and devops **(recommended)**. B: `zai-coding-plan/glm-5.3-flash`, which
sidesteps the glm-5.3 quota for the test role. C: out of round, routed
through the bug crew as a main defect (ruling 2026-10-17). It is a
main-branch defect, but the brief asked for this sweep, so A or B keeps it
here.

Per-case blocks. Options are **R** re-pair to Q0, **P** retire (park, arm
removed), **F** freeze with a stale-catalog note.

**Q4 — cat-cafe-monitoring** (corpus, private; `provisional`, flash 0.833
vs 5.2 0.472, n=1; the only case where the harness agreed with the public
ordering). Default **R**. The record re-labels to `not_assessed`. Under
Q0=A the flash run carries into the weak slot. Tally drops from 1 of 8 to
0 of 8 until a strong-arm rerun. P loses the case from the corpus. F keeps
a provisional that rests on a dead arm, which needs an FR-009 exemption
and does not match the case's arms.

**Q5 — deveval-geotext** (corpus, public; `rejected no_separation`,
inverted flash 0.222 vs 5.2 0.778). Default **R**. Re-labels to
`not_assessed`, and the inversion is kept in the note. P is reasonable if
the user reads the inversion as a case defect rather than model noise.

**Q6 — deveval-readtime** (corpus, public; `rejected no_separation`,
near-tie 0.250 vs 0.167). Default **R**, re-labels to `not_assessed`.
Alternative: P.

**Q7 — theatre-box-office** (private store, corpus; `rejected
no_separation`, both arms 1/56 dead at merge). Default **R**, re-labels to
`not_assessed`. Note: the 1/56 was a pipeline artefact that round 017
addressed, not model evidence.

**Q8 — deveval-lice** (corpus, public; `rejected reference` 30/31, excluded
from R1). Default **R**, verdict unchanged. Alternative: P, which matches
its de-facto exclusion.

**Q9 — deveval-hone** (parked). Default **R**, verdict unchanged
`not_assessed`. F is acceptable but leaves a dead model behind
`--allow-parked`.

**Q10 — deveval-particle-swarm-optimization** (parked). Same as Q9.
Default **R**.

**Q11 — deveval-stocktrends** (parked). Same as Q9. Default **R**.

**Q12 — todo-api-greenfield** (smoke). Already migrated in round 017; only
a history comment remains. Default: no change.

**Q13 — crew-probe** (probe). Runs glm-5.3, with a history comment only.
Default: no change.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Sweeping the FR-001 surfaces finds 0 glm-5.2 model
  declarations, except cases ruled F (listed by name).
- **SC-002**: All 10 repo cases and the private case load without error.
- **SC-003**: Every touched case's `acceptance.yaml` verdict equals its
  FR-007 expected value. `benchmark corpus` prints the tally the plan
  predicts.
- **SC-004**: The run-record manifest matches 100% at close (0 records
  changed or removed).
- **SC-005**: The full test suite shows no new failures against the main
  baseline. If Q1 = A, the new staleness tests are RED before and GREEN
  after.
- **SC-006**: $0 model spend in the round. No benchmark or pipeline run is
  launched.

## Assumptions

- The models.dev catalog snapshot of 2026-10-26 is current at landing. If
  glm-5.3-flash or glm-5.3 is deprecated before then, the round stops and
  re-gates Q0.
- Keeping an arm's name and definition preserves the comparability of its
  stored runs. `separation()` keys on arm name and oracle_id, not on
  kroker_commit. That is existing behaviour and this round leaves it alone.
- `benchmark accept` runs inside the dev container against the live runs
  root, with `SDLC_PRIVATE_CASES_ROOT` set for the private case (round 016
  ops notes).
- Commits are subject and body only, with no attribution trailers.
