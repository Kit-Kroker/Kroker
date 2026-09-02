# The crew — a Temporal-native multi-agent code stage (`E-88`)

**Landed 2026-09-01.** Spec:
`docs/superpowers/specs/2026-08-31-crew-temporal-native-multi-agent-design.md`
(step 2 addendum: `…/2026-08-31-crew-step-2-design.md`). Plans:
`docs/superpowers/plans/2026-08-31-crew-spine.md`,
`…/2026-08-31-crew-step-2.md`. Contracts: `src/sdlc/crew/`,
`src/sdlc/workflows/crew.py`, assets in `crew/`. ARCHITECTURE §§2–4.

**Problem it closed.** E-87 (`feat/e-87-herdr-harness`, never merged) put a
multi-agent round machine *inside an activity* — 782 lines of driver, a journal
file, and a hand-written recovery path — because an activity has no history of
its own. Everything that machine hand-rolled, Temporal already owns. E-88
rebuilds the same capability from `main` as a child workflow: the round loop,
the brakes, and the durable state are workflow code, and every side effect is
an activity. E-87 is not merged and not deleted; it stays as the archived ref
its measurement can be reproduced from.

- [x] **Step 1 — the spine.** `CrewTaskWorkflow` with a one-role crew, four
  activities (`prepare_crew`, `run_crew_turn`, `read_round`,
  `checkpoint_round`), heartbeat-details resume, and the four brakes (wall
  clock, per-turn timeout, cost cap, round bound). Roles and layouts as files
  (`crew/{roles,layouts,skills}/`), fail-at-boot loader checks, and the round
  protocol living inside the worktree but out of the diff — the checkpoint's
  `git add` is pathspec-scoped rather than relying on an exclude file.
  `HarnessKind.CREW` is a **composition mode, not a CLI**; the code stage
  routes to a child workflow and gets the same `HarnessRunResult` back.
  *Acceptance:* `bench-crew-probe-1788180917` matched the E-87b baseline's
  mechanical signals — the whole pipeline through code/qa/review/merge/handoff/
  deploy, 6 tasks, 11 real crew-turn attempts, valid `notes-v1` notes.
- [x] **Step 2 — the crew.** The critic role and the second round that can hear
  it (`rounds.max: 2`, because at `max: 1` a critic is spend with no consumer:
  the only thing that can read `advisor.md` is the next round's brief).
  Containment resolved **per role** — a non-lead keeps `cwd` at the worktree so
  it can read the code it is criticising, and confines its writes with
  `HarnessRequest.write_root`, which is an *argument* to the existing hook, not
  a fifth predicate and not a policy bump. `advisor-v1` / `review-v1` /
  `question-v1` join `notes-v1` under the same untrusted-input discipline.
  ADR-6's family rule extended to crews through one pure function called from
  both the loader and a client-side pre-flight. `CrewTaskWorkflow` becomes a
  `GateHost`, so `tool_approval` and `crew_question` are answered by the
  existing signals; `parent_run_id` on every pending decision lets the inbox
  group a crew's gate under its run while the fleet view stays run-level.
  *Acceptance:* `bench-crew-probe-1788215955` — two real rounds per task across
  `CREW-001`…`CREW-007`, non-null token counts on every code record, round-2
  notes incorporating round-1 critique, `deferred` escalations reaching the
  inbox under their parent run, and a broken-environment attempt failing
  cleanly instead of fabricating.
- [x] **Step 3 — the seams.** Absorbed into steps 1 and 2 rather than run as a
  third pass: `benchmarks/drift.py` names the crew turn in `CODING_ACTIVITIES`
  (without it, drift is silently uncomputed for crew tasks), the `crew` pytest
  marker is registered, `test_crew_{loader,worktree}.py` are the retargeted
  herdr tests, and the worker image installs `claude` beside `opencode` — pulled
  forward because step 2's critic needs a second vendor to exist.

**Known boundaries (recorded, not fixed).**

- ⚠️ **The reviewer role and the `critic || reviewer` fan-out are out**, and
  deliberately so: a third opinion needs a third vendor (`cursor-agent`
  installed or an `agy` adapter). Until it exists there is nothing to
  parallelise, and `require_reviewer_approval` stays a layout field with no
  behaviour behind it. Tracked as its own item.
- ⚠️ **`no-out-of-worktree-write` is hook-layer**, so a non-lead role on a
  harness that compiles only native-layer rules is not confined by the fence at
  all — the rule lands in `rules_unenforceable` and the turn refuses under
  `containment_strict`. Containment is therefore a statement about a crew's
  composition: in a contained run, a non-lead role wants a harness with a hook
  layer.
- ⚠️ **Session resume is not worker-pinned.** A retry taken by a different
  worker needs that CLI's session store to be reachable; Worker-Specific Task
  Queues would fix it and are not scheduled.
- ⚠️ **`CursorHarness` parses cost under `# ASSUMPTION: may be absent`**, so a
  cursor role may yield `cost_incomplete`.
- Quality is **not** a crew acceptance criterion. The `crew-probe` baseline
  scores 0.000 for an environment reason E-87b §7.2 identified (the retry brief
  references a worker-only mount); comparing quality across the two would
  measure the mount, not the design.
