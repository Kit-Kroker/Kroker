# Bug Assessment: Replay-harness notify race — unregistered activities hard-fail workflow tasks under load

- **Slug**: notify-flake
- **Created**: 2026-09-20
- **Source**: pasted text — TASK BRIEF `.workspace/tmp/notify-flake-brief.md` + card `.workspace/tasks/e75-notify-flake.md`
- **Verdict**: valid
- **Severity**: medium

## Report (summarized)

`tests/replay/test_graph_golden.py` fails NONDETERMINISTICALLY under full-file
load with:

```
temporalio.exceptions.ApplicationError: NotFoundError: Activity function
notify for workflow e74-<scenario>-<uuid> is not registered on this worker
```

Card evidence matrix: fails at baseline bf2383f (pre-E-75) and at E-75 branch
HEAD, different scenario each run; single-scenario runs pass at every commit.
Proven pre-existing — NOT an E-75/E-77 regression. Per-scenario runs are the
ruled SG-1 gate; full-file runs are flake-classified.

## Symptom

Replay-driven golden tests are nondeterministic: the temporalio worker
hard-fails a workflow task with "Activity function ... is not registered"
instead of letting the intended benign schedule-to-start expiry play out.
Expected: every replay scenario reproduces its golden byte-identically on
every run, single- or full-file.

## Reproduction

1. Check out main (flake reproduced at bf2383f, a6d8d56; one green roll
   observed at 2c732e0 — nondeterministic by nature).
2. Run the full file: `uv run --frozen pytest tests/replay/test_graph_golden.py -m temporal -q`.
3. Repeat until a scenario fails with "Activity function notify not
   registered" (card observed budget_arch_reject, max_gate_rounds_1,
   plan_revise_approve across commits).

Chasing repeats is ruled out; the deterministic gate is the contract test
below.

## Suspected Code Paths (all anchors re-verified at 2c732e0)

- `src/sdlc/workflows/gates.py:48-52` — `NOTIFY_ACT`: s2c 30s, **s2s 5s**,
  retry max_attempts=1. Verified.
- `src/sdlc/workflows/gates.py:135-167` — `_notify`: catch-all `Exception`
  → `_on_notified(gate, reason, "unresolved", False, str(e)[:200])`. Verified.
  Note `out.results` is iterated OUTSIDE the try/except (gates.py:166-167).
- `tests/replay/scenarios.py:244-251` — `_base_activities()`: no `notify`.
  Verified.
- `tests/replay/scenarios.py:335-344` — `_budget_activities()`: no `notify`.
  Verified.
- **Every other notify-scheduling scenario builds an inline bundle** —
  `brownfield_happy` (scenarios.py:398), `arch_timeout_reject` (:447),
  `waves` (:468), `seeded` (:484), `research_greenfield` (:519),
  `cancel_during_code` (:551), `partial_awaiting_architecture` (:574) — none
  registers `notify`. Only 6 of the 13 notify-scheduling scenarios ride the
  two shared helpers. Verified by executable sweep (below).
- `tests/replay/harness.py:86-93` — `Worker(activities=scenario.activities())`.
  Verified.
- `tests/replay/projection.py:24-37,57-90` — command projection records only
  ACTIVITY_TASK_SCHEDULED per activity type; TraceRecorder records only
  STAGE_STARTED / GATE_DECIDED (never GATE_NOTIFIED); close is the terminal
  string. Verified — this is what makes the fix projection-invisible.
- `src/sdlc/workflows/run_host.py:86-97` — `_on_notified` emits
  RunEventKind.GATE_NOTIFIED; grep confirms no test/golden consumes it.
  Verified.
- `src/sdlc/stages/research/step.py:178-190,254-271` — `plan_research`
  scheduled by `_fan_out_research`; its failure is caught
  (`except Exception` → `_degraded_research_brief`) — the research analogue
  of the notify benign path. Verified.
- Goldens: `activity:notify` in **13 files** (12 golden scenarios +
  `partial_awaiting_architecture.json`, whose fixture is required by
  `test_fixtures_present.py` despite `golden=False`), **34 schedulings** —
  the brief's "12 files" count excludes the partial fixture; 34 is exact.

## Root Cause Hypothesis

The replay harness hands `Worker(activities=scenario.activities())` bundles
that do not register every activity the golden histories schedule. Two names
are missing today:

1. **`notify`** — 13 goldens, 34 schedulings. The designed benign path is
   unregistered → 5s schedule-to-start expiry → `_notify` catches →
   `_on_notified("unresolved")`. But if a subsequent workflow task activates
   while the unregistered activity task is still pending, the temporalio
   worker hard-fails the WFT with "Activity function notify not registered".
   Under full-file load (hot loop, many scenarios) the race window is hit
   regularly.
2. **`plan_research`** — `research_greenfield` golden schedules it once; the
   scenario bundle does not register it. Same race class; its failure is
   currently absorbed by the research step's degrade branch
   (`step.py:269`), which is why the golden still closes `deployed:`.

**Confidence: high.** Verified statically (bundle contents vs. golden command
projections, executable sweep) and dynamically (deterministic contract RED,
below). The production fire-and-forget design (NOTIFY_ACT + catch-all +
degrade) is correct as-is; the defect is harness-only.

**Correction to the brief**: "today that is exactly `notify`" is FALSE. The
executable sweep proves `plan_research` is also unregistered
(`research_greenfield`). The fix must cover both, else the contract test
stays red.

## Deterministic RED (verified, not merely asserted)

A pre-existing untracked file at HEAD,
`tests/replay/test_notify_registration_chaos.py` (provenance flagged below,
content verified line-by-line against the code by this assessment), pins the
contract. Executed at 2c732e0:

```
uv run --frozen pytest tests/replay/test_notify_registration_chaos.py -q
→ exit=1, 29 failed / 15 passed   (.workspace/tmp/nf-chaos-red-pre-fix.txt)
```

- 13 × `test_notify_is_registered_by_every_scenario_that_schedules_it` — RED
  on exactly the 13 notify-scheduling scenarios.
- 1 × `test_no_activity_other_than_notify_is_left_unregistered` — RED only on
  `research_greenfield` (`plan_research`).
- 2 × helper rows (`_base_activities` / `_budget_activities`) — RED.
- 13 × Results-contract rows — RED (no fake registered yet).
- 15 sweep rows GREEN (the other scenarios register everything they
  schedule).

Independent cross-check (throwaway script, same extraction of
`__temporal_activity_definition` names vs. golden commands) reproduces the
identical missing-set: `notify` ×13, `plan_research` ×1.

Supporting evidence, NOT the gate: one full-file
`test_graph_golden.py -m temporal` run at HEAD came up **green**
(exit=0, `.workspace/tmp/nf-head-fullfile-run1.txt`) — consistent with the
race being nondeterministic and with the card's "do not chase repeats" rule.

## Proposed Remediation

**Preferred** (harness-only, atomic — one logical change: "the harness
registers every activity type the golden histories schedule"):

1. Define a no-op fake in `tests/replay/scenarios.py`:

   ```python
   @activity.defn(name="notify")
   async def fake_notify(inp: NotifyInput) -> Results:
       return Results()
   ```

   (`Results` from `sdlc.notify.contract` — `GateHost._notify` iterates
   `out.results` OUTSIDE its try/except, so the fake must return the real
   contract shape, and must accept the production `NotifyInput` incl.
   `deadline=None` / `project=None`.) Append it to `_base_activities`,
   `_budget_activities`, **and the 7 inline notify-scheduling bundles**
   (brownfield_happy, arch_timeout_reject, waves, seeded, research_greenfield,
   cancel_during_code, partial_awaiting_architecture) — patching only the two
   helpers leaves 7 goldens red.

2. Define a fake `plan_research` returning an EMPTY plan
   (`ResearchPlan(sub_questions=[], usage=<zero RoleUsage>)`) and register it
   in the `research_greenfield` bundle. Empty `sub_questions` is what keeps
   byte-identity: the workflow then takes the deterministic
   "every sub-question failed" degrade branch (step.py:256-257) — no
   `research_subquestion` / `synthesize_brief` get scheduled, so commands,
   trace and close are unchanged. (A fake returning a non-empty plan WOULD
   change the command projection and break goldens.)

3. Keep/land the contract test pinning registration completeness (the chaos
   file above, post-clearance) — it must go GREEN exactly when the fakes
   land.

**GOLDEN BYTE-IDENTITY argument** (to be proven by run, not argument):
- commands: `activity:notify` / `activity:plan_research` are scheduled either
  way — projection unchanged; no new activity types appear (empty-plan fake).
- trace: TraceRecorder records only STAGE_STARTED/GATE_DECIDED;
  GATE_NOTIFIED is never recorded.
- close: terminal string; neither notification outcomes nor the degraded
  brief's error text reach it.
- Honest note: the payload DOES shift semantically (one `_on_notified(
  "unresolved", False, ...)` call becomes zero; the degraded brief's embedded
  exception text changes from the NotFoundError to "every sub-question
  failed"). These shifts are projection-invisible but real; recorded here per
  the brief's honesty requirement.

**Files likely to change**:
- `tests/replay/scenarios.py` — fake_notify + fake_plan_research + 9 bundles
- `tests/replay/test_notify_registration_chaos.py` — the contract test (see
  provenance flag)

**Tests to add or update**: none beyond the contract file; the golden suite
itself is the regression gate (3× consecutive green full-file + per-scenario
runs per the brief).

## Risks & Considerations

- **Golden churn is the prime risk** — mitigated: empty-plan fake; verify
  `git status` shows zero `tests/replay/golden/**` changes and run all 16
  scenarios per-scenario after the fix.
- **Concurrent-modification hazard**: this assessment ran in the primary
  checkout at 2c732e0 and observed (a) the untracked chaos test file
  appearing mid-session, (b) an unrelated ` M pyproject.toml` edit
  (`[tool.setuptools.package-data]`) — attribution corrected by the
  orchestrator (user-confirmed, 2026-09-20): it is the **user's parallel
  session**, not any seat's and not the orchestrator's. Excluded from this
  bug's scope; HARD RULE on file: no seat stages, commits, or reverts it —
  the orchestrator asks the user. Any gate run must re-check
  `git log`/`git status` immediately beforehand, per the brief. Fix work is
  planned in a fresh worktree on branch `fix/notify-flake`, which also
  isolates it from this shared tree.
- The fakes import production contract types (`NotifyInput`, `Results`) —
  import-only, no behavior coupling; `sdlc.notify.activities.notify` (the
  production activity) must remain unregistered.
- Registering `notify` on the worker removes the 5s s2s expiry wait per gate
  in live runs — full-file wall time may improve slightly; timing itself is
  not projected (time-skipping env).

## Out of scope (unchanged from brief)

Sibling `./runs` readers CWD-anchoring; fail-edge fix axis (E74-OQ-3);
E75-OQ-2/3/4; E-9 notification feature work; T043/e2e-proposer flakes;
frontend/TS; uv.lock; unrelated tests.

## Open Questions

- [RESOLVED BY VERIFICATION] Harness-only is POSSIBLE — both missing names
  are covered by harness fakes; no `src/` change is needed; no SCOPE-GATE
  fork required.
- [RESOLVED BY RULING 2026-09-20] Provenance of the untracked
  `tests/replay/test_notify_registration_chaos.py`: qa-chaos's RED work
  product, authored during this run's RED phase in the primary checkout
  (report: red-report-qa-chaos.md). ADOPTED — committed on fix/notify-flake
  with provenance noted; not anonymous.
- [RESOLVED BY RULING 2026-09-20] The `partial_awaiting_architecture` fixture
  golden (scenario `golden=False`, file required by test_fixtures_present)
  IS in the contract test's sweep set — granted by the orchestrator.
