VERDICT: approve

Gap 1 is resolved (see "## Pass 2" at the end).

1. **tasks.md:62 — dangling task id `(T049)` in the Worktrees exception.**
   "**Exception**: `S/stages/*/*.md` clause edits (T049) are made in the
   primary checkout, per root `AGENTS.md`." No T049 exists: tasks.md runs
   T001–T038 and plan.md defines no T049 (its ids jump T046 → T050). The
   clause-edit task is **T029** (which itself carries the primary-checkout
   rule and the copy into `../Kroker-020-2`). The reference sits inside
   the Worktrees bullet this integration pass rewrote (its PR-1 base line
   became "after `main` is fast-forwarded to PR-1"), so the bullet was
   edited and left with an id that points at nothing. One-token fix:
   `(T049)` → `(T029)`.
   **→ RESOLVED in pass 2**: tasks.md:62 now reads `(T029)`; no `T049`
   remains in either file.

# Integration consistency checklist: round 020 (2026-11-08)

**Scope**: the three user decisions (fast-forward integration with no
PRs; orchestrator-only gates and restart; T001 done by the orchestrator)
as applied to `plan.md` and `tasks.md`. Subject: both files; everything
else is reference.

## Decision 1 — fast-forward, no pull requests

- [x] CHK001 - No wording implies opening a PR or merging after review?
  [Consistency] — plan.md: T019 and T089 now end in "hand back: the
  orchestrator verifies the branch and fast-forwards `main` to it. The
  crew does not push."; both files carry the Integration note
  ("fast-forward merges to `main`, with **no pull requests**; 'PR-1' and
  'PR-2' are stage names"); tasks.md T015/T035 say "no pull request is
  opened". Remaining "PR-1/PR-2" mentions are stage names only.
  plan.md's note explicitly supersedes the PR wording in research R-9
  and quickstart. One wording nit, not a gap: plan.md T042's STOP still
  says "do not merge" — a prohibition ("do not integrate the branch"),
  not a description of a review-merge process.
- [x] CHK002 - T015/T035 wording? [Traceability] — T015: "**Orchestrator-
  only.** The orchestrator verifies branch `020-delete-featureworkflow`
  (T014 record) and fast-forwards `main` to it."; T035: same shape for
  `020-delete-featureworkflow-2`, "The fast-forward deploys nothing; do
  not push a `v*` tag". Both stages and both blocking gates kept.

## Decision 2 — orchestrator-only tasks and executor STOPs

- [x] CHK003 - Every orchestrator-only task marked? [Consistency] —
  tasks.md: T001 ("Orchestrator-only, done"), T015, T016 ("it needs live
  Temporal"), T035, T036, T037, plus the header list (line 43) and the
  Phase 10 preamble ("The executor never runs T036 or T037. It stopped
  after T034."). plan.md: line 17 note, T030, T090, T091 and the Phase E
  header ("orchestrator-only"; "The executor stops before T090 and hands
  back"). T038 is "done by whoever the orchestrator assigns" — fine.
- [x] CHK004 - Executor STOP points explicit and matching Dependencies?
  [Consistency] — After T014: T014 ends "**Executor STOP: hand back to
  the orchestrator here.**"; T017 opens "(executor resumes here, only
  after T016 PASSED)"; Dependencies: "T014 → executor STOP → T015
  (orchestrator fast-forward) → **T016 (gate 1, orchestrator)** → T017
  (executor resumes)". After T034: T034 ends "**Executor STOP: hand back
  … Do not start T035, T036 or T037.**"; Dependencies: "… depends on T031.
  Then executor STOP." then "T035 → T036 (gate 2, orchestrator) → T037
  (orchestrator) → T038". Header restates both STOPs. All three places
  agree.

## Decision 3 — T001 done

- [x] CHK005 - T001 marked `[x]`, recorded, not executor work?
  [Traceability] — tasks.md T001 is `[x]` "**Orchestrator-only, done by
  the orchestrator (2026-11-08).** Not an executor task. Recorded for
  traceability…"; the header "Commits" line and Dependencies ("T001
  (done) → T002") agree.

## temporal discipline

- [x] CHK006 - No executor task runs a `temporal` command? [Consistency]
  — tasks.md: "**The executor never runs any `temporal` CLI command.**
  The only tasks that do are T016 and T036, and both are
  orchestrator-only." T034 repeats "No `temporal` command runs in this
  task"; T037 uses `docker compose` and is orchestrator-only. plan.md
  marks T030/T090 orchestrator-only. The stale "T034 and T061" rule from
  before the tasks pass 2 has not regressed.

## Ids and citations

- [x] CHK007 - Task ids unchanged? [Consistency] — tasks.md holds
  T001–T038, sequential, no renumbering; plan.md still defines its 32
  ids (T010–T092 with gaps by design), zero dangling ids inside plan.md.
- [x] CHK008 - Plan-id citations unchanged? [Traceability] — All 32 plan
  tasks are still cited exactly once in tasks.md (T045's citation sits
  wrapped across two lines inside T024). No citation was altered by the
  integration edits.
- [ ] CHK009 - Every unqualified task reference resolves? [Clarity] —
  **No**: `(T049)` at tasks.md:62 (gap 1). Systematic sweep: plan.md 0
  dangling; tasks.md exactly this one.

## Notes

- One token to change and this passes; nothing else in either file
  contradicts the three decisions or the other file.

## Pass 2 (2026-11-08)

Gap 1 re-checked. **Resolved.**

- tasks.md:62 now reads "- **Exception**: `S/stages/*/*.md` clause edits
  (T029) are made in the primary checkout, per root `AGENTS.md`."
- A fresh sweep of both files finds no `T049` anywhere; every `T0xx`
  token in tasks.md resolves to a task id (T001–T038, still sequential)
  or a plan id; plan.md still has zero dangling ids.
- Nothing else changed since pass 1: the decision-1/2/3 checks
  (CHK001–CHK008) stand as recorded.

**The integration pass is approved.**
