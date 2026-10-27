VERDICT: approve

1. **data-model.md §2 (Acceptance record, lice column)** — the table predicts
   `separation: null` for deveval-lice after re-label. Wrong: FR-005's re-label
   is online, and `dispatch_accept` computes a separation for every
   `role == corpus` case regardless of the reference result
   (`src/sdlc/benchmarks/cli.py:526-546`; lice is `language: python`,
   `role: corpus`, so the "no oracle" branch is not taken either). The fresh
   lice record will carry a computed separation with
   `strong.arm: zai-coding-plan-glm-5.3`, empty `strong.run_ids`, weak =
   flash, `not_comparable` ≥ its glm-5.2 graded runs — i.e. the same shape as
   the cat-cafe column, not null. The verdict/reason predictions are
   unaffected (`decide()` checks reference first, `acceptance.py:175-176`,
   so `rejected (reference)` stands), SG-2's literal gate still passes, and
   the row is non-stale either way — but contract §2 binds the written file
   to "data-model §2's gated fields", so an expected-value cell that the
   execution is guaranteed to contradict must be fixed before tasks are
   generated. One-cell fix.
2. **quickstart.md §5.2 (SC-001 sweep)** — the allowed-hits list ("YAML
   comments that record history … and the `config.yaml` comment, if one is
   kept") does not cover two hits the sweep command will still return after
   the round: `agents/planner/agent.py:26` (Python comment naming the
   proposer route `anthropic:glm-5.2`) and `src/sdlc/core/models.py:190`
   (`model: str | None = None  # e.g. "zai-coding-plan/glm-5.2"` — a Python
   annotation line that begins with `model:` and so reads as a hit under the
   literal pass condition "no hit on a `model:`"). Neither is a live glm-5.2
   declaration (both are out of scope per spec Out of Scope / the plan's
   "one string" edit to models.py), but as written the sweep's pass condition
   is ambiguous for models.py:190 and the implementer must improvise — or
   stop, or make an out-of-scope edit. Add both to the allowed list or word
   the pass condition as "YAML key".
3. **spec.md §FR-010 / quickstart.md §5** — FR-010's README
   `--role-model dev=zai-coding-plan/glm-5.2` example (README.md:310) and the
   `BENCHMARK.md` break marker have no validation in quickstart or the
   contracts; only plan Step 6 (the edit) and Step 7's verification.md. The
   config.yaml comment half of FR-010 is touched by the §5.2 sweep, the other
   two halves are not. A one-line `git grep -n "glm-5\.2" -- README.md`
   expecting no hit would close the loop. Minor.

# Plan Quality Checklist: glm-5.2 Arm Retirement (round 019, pass 1)

**Purpose**: Validate the plan by spec-kit's checklist method — requirement
traceability, step concreteness, no placeholders, exact file paths, explicit
test commands — plus the reviewer brief's four consistency checks
(FR/SC mapping, stop-guard checkability, file:line existence, expected
verdicts vs `decide()`).
**Created**: 2026-10-27
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [research.md](../research.md)
· [data-model.md](../data-model.md) · [contracts/corpus-status.md](../contracts/corpus-status.md)
· [quickstart.md](../quickstart.md)

## Requirement Traceability (FR/SC → plan step → validation)

- [x] CHK001 - Does every functional requirement FR-001..FR-011 map to a named
  plan step? [Traceability, Plan §Steps] — Yes: FR-001→Steps 2/3/4 + §5.2
  sweep; FR-002→Steps 4/5; FR-003→Step 2; FR-004→Step 3; FR-005→Steps 4/5
  (quickstart §4); FR-006→Step 4 (data-model §1 block); FR-007→contract §2 +
  SG-2; FR-008→Step 0 manifest + SG-1; FR-009→Step 1; FR-010→Step 6;
  FR-011→Step 6 (card, not executed).
- [x] CHK002 - Does every success criterion SC-001..SC-006 map to a validation
  in quickstart or the contract? [Traceability, Spec §Success Criteria] —
  Yes: SC-001→quickstart §5.2; SC-002→fast tier
  (`test_load_corpus_returns_ten_specs…`, golden case loads, private-leak
  tests; 10 repo cases confirmed in `benchmarks/cases/`); SC-003→contract §2/§3
  + quickstart §4; SC-004→quickstart §5.1 + SG-1; SC-005→quickstart §3 (RED
  T1–T4) + §5.3 gates; SC-006→rule 2 + SG-7 + D-5 read-only runs mount.
- [ ] CHK003 - Is FR-010's README example and BENCHMARK.md break-marker
  correction validated by any quickstart or contract command? [Gap, Spec
  §FR-010] — No; see gap 3 above.
- [x] CHK004 - Are the GATE 1 rulings (Q0=A, Q1=A, Q2=A, Q3=A, Q4–Q11=R)
  bound into the plan as constants rather than left as parameters?
  [Traceability, Spec §Rulings] — Yes: D-1/D-2 fix the pair and fields;
  data-model §1/§4 fix the values; plan §Summary and Steps use them literally.
- [x] CHK005 - Does the plan bind every parameterised FR (FR-002/003/004/007/
  009) to its ruled value with no decision left open? [Traceability] — Yes.

## Stop-guard checkability

- [x] CHK006 - Is each stop-guard SG-1..SG-8 phrased so its firing condition
  is observable from output the plan produces? [Measurability, Plan
  §Stop-guards] — Yes: SG-1→§5.1 manifest diff; SG-2→printed line vs D-3 +
  §4 file checks; SG-3→`reference.detail`/`floor.detail` prefix +
  `tests_total` (offline_checks.py:101-106 confirmed); SG-4→baseline.md
  failure list; SG-5→replay gate at Step 0 vs after Step 2; SG-6→§2.1 catalog
  probe command with expected output; SG-7→policy guard + read-only mount;
  SG-8→rule 5.
- [x] CHK007 - Does each stop-guard name its recovery action? [Clarity] —
  Yes (SG-2's `git checkout -- <path>`; "leave the tree as it is, no
  fix-forward"; SG-3's single-rerun allowance).

## File-path exactness (spot-checks, 28+ verified)

- [x] CHK008 - Do the cited `file:line` references exist as claimed?
  [Traceability] — Yes, all verified: acceptance.py:80 (separation), :175,
  :183, :186, :189, :255-262; corpus.py:60 (196 lines); cli.py:481, :502,
  :515, :567; oracle_id.py:13; models.py:375 and the mirror comment
  :367-371 (plan cites 368-372); deveval.py:228; agents/test/agent.yaml:3;
  matrix.py:29-40, :136; workflow.py:105; runs.py:186-200, :321;
  offline_checks.py:101-106, :115-135; smoke.py:146-191; conftest.py:175-182;
  test_agents_registry.py:15-18; test_registry_mirror.py:58, :86;
  loader.py:219-241, :244-267, :331-343; feature.py:285, :341;
  cache.py:42-47; B/models.py:402-419; test_benchmark_corpus.py:18-26,
  :107-108, :107-125 (474 lines); test_golden_case_loads.py:44-50;
  test_private_leak.py:290-310; todo-api case.yaml:31-34; README.md:310.
- [x] CHK009 - Are the claimed file sizes and growth estimates accurate?
  [Clarity, Plan §Constraints] — Yes: corpus.py 196, test_benchmark_corpus.py
  474, BENCHMARK.md 927 (all confirmed by count); growth (+10/+90/+28) keeps
  every file under the 1000-line ceiling.

## Expected-verdict correctness (vs `decide()`)

- [x] CHK010 - Does each contract §2 expected line follow from
  `acceptance.py` `decide()`? [Consistency, Contract §2] — Yes:
  cat-cafe/geotext/readtime/theatre: reference passes, strong (glm-5.3) has
  no stored runs → `separation.passed is None` and empty strong scores →
  `not_assessed` "no strong arm runs" (:186-187; separation.detail is ""
  so the `or` fallback fires); lice: reference fails 30/31 → `rejected
  (reference)` (:175-176, checked before separation); hone/pso/stocktrends:
  parked sentinel detail "separation not assessed for parked case"
  (cli.py:533-537) → `not_assessed` (:183-184). Printed-line format
  `<case>: <verdict> (<reason>)` matches cli.py:569-571.
- [x] CHK011 - Does the tally prediction (1 of 8 → 0 of 8) follow from the
  code? [Measurability, Research D-3] — Yes: `EXIT_CASES = 8`
  (corpus.py:13); tally counts only `role == CORPUS and stale is False and
  verdict in {accepted, provisional}` (corpus.py:176-178); cat-cafe is the
  only provisional today and re-labels to `not_assessed`.
- [ ] CHK012 - Does data-model §2's expected-record table match what
  `dispatch_accept` writes for every case? [Consistency, Data-model §2] —
  No, for lice; see gap 1 above.
- [x] CHK013 - Do D-6's "today's rows" claims hold (no row flips before the
  round's edits)? [Consistency, Research D-6] — Yes: cat-cafe and geotext
  records' separation arms equal their case.yaml arms; lice's record has
  `separation: null`; parked rows are exempt by role.

## Concreteness and placeholders

- [x] CHK014 - Is any step left as a placeholder (TBD/TODO/`<...>` other
  than the FR-006 template variables)? [Completeness, Plan §Steps] — No; the
  only `<...>` forms are the FR-006 comment template's value slots, filled
  from baseline.md (data-model §1).
- [x] CHK015 - Are the RED-test expectations concrete and falsifiable?
  [Measurability, Contract §1] — Yes: seven tests T1–T7 with per-case
  expected `stale` values; "exactly T1–T4 fail" before the corpus.py change.
- [x] CHK016 - Are the test commands explicit and reproducible?
  [Clarity, Quickstart §1/§3/§4/§5] — Yes: full `docker run` invocation with
  mounts and env, per-case accept command, corpus command with expected
  tally, gate commands with `uv run --no-sync`.

## Sweep and scope consistency

- [ ] CHK017 - Does quickstart §5.2's pass condition classify every hit the
  sweep will return after the round? [Coverage, Quickstart §5.2] — No; see
  gap 2 above.
- [x] CHK018 - Is data-model §1's "before" column faithful to the current
  case files? [Consistency, Data-model §1] — Yes (cat-cafe, geotext, lice
  verified: strong flash / weak glm-5.2, `models: [glm-5.2]`,
  `extra_args_by_model --variant max` on cat-cafe only among repo cases).
- [x] CHK019 - Does the plan's edit scope match FR-001's sweep surface?
  [Consistency, Spec §FR-001] — Yes; V2's per-case claims confirmed by grep
  (7 repo cases + history comments in todo-api/crew-probe; add-login clean).
- [x] CHK020 - Are the round's Step 0 preconditions present in the tree
  (`.specify/feature.json`, CLAUDE.md SPECKIT pointer)? [Completeness, Plan
  §Steps] — Yes, both confirmed.

## Pass 2

All three pass-1 gaps re-checked in the tree; all closed. Remaining items
are two non-blocking presentation nits (below), so the verdict is approve.

**Gap 1 (data-model §2 lice column) — closed.** The lice column now shows
the computed shape (`strong.arm: zai-coding-plan-glm-5.3`, empty
`strong.run_ids`, `weak.arm: flash`, `weak.run_ids: []`, `not_comparable: 0`)
with a "Lice correction" paragraph citing `cli.py:526–546` and
`acceptance.py:175`. Verified against the code path and against the runs
root: no `*lice*` run records exist under `D:\own\Kroker\runs\benchmarks`,
so "(no stored lice runs)" and `not_comparable: 0` are exact. research.md
D-6 known-limit 2 now reads "offline accepts, such as lice's current
record" and points to data-model §2 for the post-re-label state —
consistent with D-6 "Today's rows" ("Lice has `separation: null`", true
today) and with D-3's "(not reached)", which is decide() control flow. The
fix also makes SG-2 and quickstart §4's file checks uniform across all
eight cases (no null edge case left).

**Gap 2 (quickstart §5.2 sweep) — closed.** The pass condition ("no live
YAML text names glm-5.2, meaning no occurrence outside a `#` comment") is
now enforced by one mechanical command,
`grep -nE "^[^#]*glm-5\.2" <case.yaml/agent.yaml/config.yaml set>`. The
regex is sound: full-line and trailing comments cannot match, and any
live-text occurrence does. Ran it at base: exactly **51 lines** — 7 in
cat-cafe (weak_arm, arm `name`, dev/test/devops, `models` item,
`extra_args_by_model` key — every declaration form), 6 in each of the six
other repo cases, 1 in `agents/test/agent.yaml`, 7 in
`theatre-box-office/case.yaml`, 0 in `benchmarks/config.yaml` (its mention
is a comment) — matching the quickstart's stated 51/7 exactly. The
Python-string check (`git grep '"zai-coding-plan/glm-5.2"' -- models.py
deveval.py`) currently prints deveval.py:228, models.py:190 and
models.py:375; post-round only models.py:190 (the `# e.g.` comment)
remains, as stated. The allowed-hits list (FR-006 blocks, todo-api
`case.yaml:31–34`, crew-probe `case.yaml:34`, the config.yaml comment,
`agents/planner/agent.py:26`, `src/sdlc/core/models.py:190`) is now
complete against every hit the broad sweep returns post-round — checked
against the full base grep over all five paths.

**Gap 3 (FR-010 validation) — closed.** Quickstart §5 item 2a validates
the README example (`git grep -n "dev=zai-coding-plan/glm-5\.2" --
README.md` must print nothing; it matches README.md:310 today), the
`BENCHMARK.md` R019 break marker (grep shows the marker; per-case table
has 8 rows = the 8 touched cases, consistent with plan Step 6), and the
file-size gate for `BENCHMARK.md`. FR-010 now maps to a plan step and to
quickstart validations for all three of its items (README, BENCHMARK.md,
config.yaml comment).

**Remaining gaps (non-blocking, cosmetic):**

1. **data-model.md §2** — the "Lice correction" paragraph is inserted
   between the `separation.not_comparable` and `kroker_commit` rows,
   splitting the markdown table: the `kroker_commit` row (line 62) follows
   the paragraph without a blank line and renders as paragraph text, not a
   table row. Content is intact; moving the paragraph below the table (or
   the row above it) restores rendering. No functional impact.
2. **research.md §6 (D-6 known-limit 2)** — the inserted sentence ("After
   the online re-label, lice's record carries a computed separation")
   makes the referent of the next sentence's "Their verdict did not read
   the arms" ambiguous (the null-separation records vs lice's new record).
   Harmless: under either reading the behavior is identical (the
   null-separation exemption is about null records; lice's post-re-label
   record's arms match its case, so it is non-stale regardless), and
   data-model §3's rule text is unambiguous. A wording tidy-up only.
