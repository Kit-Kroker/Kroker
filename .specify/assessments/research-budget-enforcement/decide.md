# Decision: Research budget-enforcement defect cluster

- **Slug**: research-budget-enforcement
- **Decided**: 2026-10-03 — drafted for the USER GATE after two skeptic
  passes. The verdict is a recommendation, not a decision.
- **Verdict (recommended)**: **go** for the S-batch and M-1; M-2 queued, not
  scheduled. The skeptic's final position is **kill** for both M items — the
  disagreement is set out under "Skeptic's final position" for the user to
  rule on.
- **USER GATE outcome (2026-10-03)**:
  1. **Go for the S-batch and M-1**, as recommended. The S-batch goes
     straight to an exec run; M-1 goes through a short spec; M-2 stays queued
     and unscheduled.
  2. **D1 stays in force.** 6.2, N2 and N3 remain a linked follow-up
     candidate; the proposed re-ruling text below was not adopted.
  3. **All four proposed register rows are approved.** The orchestrator adds
     them to the register.
- **Artifacts reviewed**: intake.md, research.md, problem.md, concept.md
- **Baseline**: main `269fa29`
- **Evidence tiers used below**: *measured* (experiment run in `kroker-dev`
  with a scripted fake model), *read* (seen in code, not run), *hypothesis*
  (neither).
- **Consultations**:
  - advisor — `.workspace/tmp/research-budget-enforcement-advisor-1.md`
  - skeptic — `.workspace/tmp/research-budget-enforcement-skeptic-1.md`,
    `.workspace/tmp/research-budget-enforcement-skeptic-2.md`
  - experiments — `.workspace/tmp/research-budget-enforcement-experiments.md`

## What changed since draft 1

Draft 1 recommended an S-batch of H1, H5, H3 and notes, with a measurement
task. The skeptic objected that its main item rested on an unrun experiment
and that splitting H1 from N4 would mislead. The orchestrator upheld the
objection and authorized E1 and E2 inside this pass. Both were run:

- **E2**: a caller-owned usage object holds the spend when the run aborts.
- **E1**: under CodeMode a budget refusal reaches the model as a retry
  prompt. If the model concludes, nothing is lost. If it retries, the run
  ends in `UnexpectedModelBehavior`, which the real stage handler does not
  catch, and each refused call over-charges the run counter — 4 phantom
  charges for 1 real search, 11 with a three-way gather, in one attempt.

So the split in draft 1 was wrong: on the production path the loss at a
budget cap goes through N4, not through the handler H1 fixes.

## Per-defect verdicts

`R/` = `src/sdlc/stages/research/`.

| Item | Verdict | Mechanism | Tier | Lands in |
|---|---|---|---|---|
| **H1** exhaustion zeroes usage | **defect** | zero `RoleUsage` built at `R/stage.py:243`, returned unchanged at `:277-282`; `R/step.py:140-141` skips it. Fires on request-limit exhaustion and on a direct `BudgetExceeded`. On the production (CodeMode) path, budget exhaustion does not reach this handler — see N4. | read; fix primitive measured (E2) | M-1 |
| **N4** `UnexpectedModelBehavior` uncaught | **defect** | raised when `run_code` exceeds 3 retries; not caught at `R/stage.py:277`, not in the non-retryable list at `R/step.py:64`. Result: up to 6 attempts, then a `failed=True` finding with zero usage (`R/step.py:109-110`, `R/models.py:98`). | measured (E1 S1, S4); the 6-attempt consequence is read | M-1 |
| **H4** run counter not rolled back | **defect** | `R/budget_store.py:121-122` commits the run charge before the scope charge can refuse; no compensation. Every refused call leaks one charge. | measured (E1: run 5 vs scope 1; 12 vs 1) | M-1 |
| **H2** exhaustion discards partial work | **not a defect as stated; residual is a design question** | For a budget cap in production the model is told and can conclude (E1 S2), which is the documented contract (`R/deps.py:31-33`, `R/stage.py:195-198`). Work is lost only when the run ends in an exception: request limit, or N4. No structured partial finding exists to carry — the brief is the run's final output. | measured (E1 S2) + read | deferred, needs ruling |
| **H3** non-atomic budget write | **latent defect** | in-place `write_text` at `R/budget_store.py:87`; a truncated or empty file fails validation at `:82` and nothing repairs it, so every later charge on that scope fails. Precedent for the fix: `R/verify.py:56-59`. The inbox card's "double-count / lost decrement" wording is **not a defect** of this write: the read-modify-write is locked (`:79-89`) and has no `await` inside. | read | S-batch |
| **H5** retain re-runs the verifier | **latent defect (determinism)** | `R/step.py:346` → `R/retain.py:19` → `Path.is_file` / `read_text` (`R/verify.py:74,80`) in workflow code, deciding how many retain activities are scheduled. Redundant in the workflow: the same brief already verified clean in an activity (`R/step.py:273-297, 333-342`). Why the sandbox does not block it (passthrough import) is a *hypothesis*; that a replay without page files fails is a *hypothesis*. | read | M-2 |
| Lock `TimeoutError` not caught | **not a defect at the stage boundary; "uncapped" is already fixed** | retries are bounded: 6 on the sub-question activity (`R/step.py:59-65`), 3 on agent activities (`src/sdlc/agents/roles.py:40-44`). Under CodeMode a tool-side timeout would also become a retry prompt first, so it can feed N4. | read; CodeMode part inferred from E1 | wording in S-batch; behaviour covered by M-1 |
| Retries inherit the spent allowance | **not a defect (by design)** | counters persist per run+scope (`R/budget_store.py:29-39`) so a crash cannot reset a budget. Its cost is that doomed retries re-charge — which is N4 + H4. | read | — |
| Stale docstrings | **doc-only; three, not two** | `R/deps.py:8-12`, `R/toolset.py:21-26`, `R/stage.py:216-218`. | read | S-batch |
| **N1** Gotchas `scope == "run"` bullet | **doc-only** | the architect uses `scope="architect"` (`src/sdlc/stages/architecture/step.py:159`). The collapsed branch at `R/budget_store.py:110-113` has no production caller; tests and the default scope still use it. | read | S-batch |
| **N2** architect ignores configured run ceiling | **defect** | `architecture/step.py:149-161` never sets `max_run_cost_usd`; default 4.0 applies (`R/deps.py:57`). Two ceilings enforced on one counter. | read | architect follow-up |
| **N3** architect sub-run limits | **latent defect** | no `usage_limits` at `R/toolset.py:52-56`, so the library default of 50 requests applies, not the configured 40; only `BudgetExceeded` is caught at `:57`. | read | architect follow-up |

Nothing in the cluster is already fixed in code. The only "already fixed"
element is the *uncapped retry* claim.

## Scorecard

| Criterion | Rating | Justification |
|-----------|--------|---------------|
| Problem validity | adequate | Three defects have a measured or measured-primitive mechanism (H1, N4, H4). Whether they fire in real runs depends on model behaviour that fakes cannot show. |
| Evidence strength | adequate | In-code file:line for every verdict; the two experiments the decision hinged on were run. No real run shows a wrong record; one recorded benchmark run hit the request limit before fan-out existed. |
| Value vs. inaction | adequate | Inaction is survivable. But the measured failure is self-amplifying: a model that retries a refusal loses its spend record *and* drains the ceiling its siblings share. |
| Feasibility / appetite | adequate | One S-batch and two M items, each with an in-repo precedent. Not the single S-batch draft 1 claimed. |
| Strategic fit | adequate | Follows the stated rule that an activity calling a model hands its usage back, and the rule against I/O in workflow code. No constitution check was made. |
| Risk posture | adequate | M-1 changes what new capped runs record and schedule (below). M-2 touches the retain path with no research replay fixture today. Both are named and each M gets its own spec. |

## Verdict & Rationale

**Recommended: go for the S-batch and M-1. Queue M-2 as a register row
without scheduling it.**

The decisive facts are measured: spend is recoverable at the cap (E2); a
model that retries a refusal ends in an exception the stage does not handle
(E1 S4); and each refused call over-charges the shared run counter (E1).
These three sit in one handler and one counter and should be fixed together.

The honest weakness: nobody has seen this happen in a real run. Whether a
real model retries or concludes is unmeasured.

## Skeptic's final position, and where I differ

After the second pass the skeptic and I agree on the facts, the per-defect
verdicts (bar N1, below), the sizing and the order. We disagree on whether
the M items are worth doing.

**Skeptic: kill M-1 and M-2; go for the S-batch only.** Its reason: research
is off by default, a cap hit has never been observed in a fan-out run, and
when the model concludes on refusal no spend is lost — so two M cycles hedge
against a synthetic failure that the Gotchas already document.

What I checked:

- Research is off by default (`src/sdlc/core/models.py:383`). True.
- It is switched on for two benchmark cases:
  `benchmarks/cases/todo-api-greenfield/case.yaml:22` and
  `benchmarks/cases/cat-cafe-monitoring/case.yaml:57`. The one recorded
  cap incident was on `todo-api-greenfield`.
- No fan-out run on this machine shows a cap hit. True.

Where I land, and why it differs:

- **M-1: go.** The research stage runs where spend records matter most —
  benchmark cases — and the measured failure corrupts exactly that record
  while draining the ceiling siblings share. The fix is bounded and its
  primitive is proven. But this is a judgement about an unobserved failure,
  and the skeptic's kill is a defensible reading of the same evidence.
- **M-2: I move toward the skeptic.** H5 needs a replay on a host without
  the page files, with grounded findings and memory enabled. It is latent and
  nothing was measured. Record it as a register row; do not schedule it.

Two corrections the skeptic's second pass adds, both accepted:

- **E1 scenario S2 is optimistic.** The fake concluded with plain text; the
  production agent must emit a schema-valid `ResearchBrief`
  (`agents/research/agent.py:60`). Concluding after a refusal is harder for a
  real model than S2 shows, which makes the retry path (N4) more likely, not
  less. S1, S3 and S4 are unaffected.
- **N1 is more than wording.** The collapsed branch at
  `R/budget_store.py:110-113` has no production caller. I keep the verdict
  doc-only because the branch is correct and tested, but the S-batch note
  should say so rather than only fix the bullet.

**The gate question for the user is therefore: S-batch only, or S-batch plus
M-1.** Both seats support the S-batch.

## Remediation shape, sizing and order

Every task starts with a test that fails on `269fa29`. Tests run in
`kroker-dev` only. Sizes per `.workspace/orchestration-protocol.md`; M items
do not batch and each gets a short spec.

| Order | Work | Contains | Shape | Size |
|---|---|---|---|---|
| 1 | **S-batch** | H3 | Write the budget file via temp file and atomic replace, as `write_page` does. Do not auto-reset an unreadable file — that would hand the budget back. | S |
| | | Notes | Three stale docstrings; "uncapped" wording (`R/toolset.py:33-38`, Gotchas); the `scope == "run"` bullet. `AGENTS.md` edits need orchestrator approval. | S |
| 2 | **M-1 cap handling at the stage boundary** | H1 | Give the sub-question run a caller-owned usage object and return it whenever the run ends in exhaustion. Keep `failed=False` for exhaustion (pinned by `tests/research/test_research_subquestion_activity.py:63-79`). | M (one spec) |
| | | N4 | Decide how `run_code` retry exhaustion caused by a budget refusal is told apart from other `UnexpectedModelBehavior`, then degrade it instead of retrying six times. | |
| | | H4 | Make a refused scope charge leave the run counter unchanged. | |
| queued, not scheduled | **M-2 retain without workflow I/O** | H5 | Retain from the verification result the activity already returned, keeping the contract that only verified findings are retained (`tests/research/test_research_grounding.py:24-50`). Add the first research replay test. | M (one spec) |

Order reasoning: the S-batch is independent and cheap, so it goes first. M-1
next because it holds the measured loss. M-2 is a latent hazard with nothing
measured, so it is queued behind a register row rather than scheduled. Inside
M-1, H4 lands before or with N4, so that degrading instead of retrying does
not leave the leak in place.

Things M-1's spec must rule on, because they change what new runs record:

- A capped sub-question will now be priced: one extra `price_usage` activity,
  and higher `calls` and `cost_usd` on the research row (`R/step.py:140-163`).
  The run budget gate reads that total. Replay of existing histories is
  unaffected — the change is activity-side and replay takes activity results
  from history — but benchmark history gets a visible break.
- `calls` today counts sub-questions, not model requests
  (`R/stage.py:67`). Keep that meaning unless ruled otherwise.
- `UnexpectedModelBehavior` is a general error. Treating all of it as
  exhaustion would hide unrelated model failures.
- Adding an entry to the non-retryable list changes names pinned by
  `tests/research/test_research_fanout_wiring.py:68`.

Known residual after all three: spend on an attempt that fails for a reason
other than exhaustion is still lost.

### Deferred (not in this go)

| Item | Contains | Size | Gate |
|---|---|---|---|
| Carry partial work | H2 residual: salvage when a run ends in an exception | L | user ruling; changes briefs and benchmark comparability; may be declined |
| Architect research surface | 6.2, N2, N3 | M | user re-ruling of D1; a short spike on how usage crosses the tool-activity boundary |

## Ruling on 6.2 (architect research sub-runs unpriced)

**Out of this go. In as a named, linked follow-up. D1 is not re-ruled by
this assessment.**

- It is real on main (read): `R/toolset.py:52-56` returns only
  `result.output`; `agents/architect/agent.py:29-35` returns only the brief.
- Why it is tempting to absorb: same failure class as H1 (model spend lost at
  an activity-side agent run), same agent, same files as N2 and N3. After
  M-1 the record is right for the stage and still wrong for the architect.
- Why it stays out:
  1. Different hand-back channel. The stage returns usage on its own
     activity result. The architect's tool result goes back to the architect
     *model*, so usage has to leave the tool activity by a new route —
     a changed tool return, a side channel, or tool-return metadata. None of
     these has been tried. (That the tool runs on a deserialized copy of the
     run context is the advisor's reading of library code; I did not verify
     it.)
  2. D1 is the user's ruling, restated in 003, 004 and 007
     (`.specify/specs/007-bounded-proposer-prompts/spec.md:116`). Reversing
     it inside a defect fix is the silent absorption the brief forbids.
  3. None of the cluster's measured interactions (H1, N4, H4) run through it.
- I am not claiming 6.2 is harder than M-1 in replay terms; M-1 also changes
  what new runs schedule. The difference is that M-1's channel exists and
  6.2's does not.
- What would flip it in: a spike showing usage can be handed back with no
  change to what the architect model sees.
- Proposed re-ruling text for the user: "D1 is lifted for 6.2 only; 6.2 is
  scheduled as the architect-research-surface follow-up, after M-1 lands,
  together with N2 and N3."

## Proposed register rows (for the user to add; the register is not edited)

For `docs/reports/external-ideas-2026-09.md`, section C:

| # | Candidate | Source | Status | Where it lands |
|---|---|---|---|---|
| (new) | Research cap handling: report spend at the cap, degrade on run_code retry exhaustion, no run-counter leak on refusal | assessment research-budget-enforcement (H1, N4, H4); E1/E2 measured | proposed (M) | `src/sdlc/stages/research/` |
| (new) | Research retain path: no file I/O in workflow code; first research replay test | assessment research-budget-enforcement (H5) | proposed (M) | `src/sdlc/stages/research/retain.py`, `step.py` |
| (new) | Research: salvage partial work when a sub-question ends in an exception | assessment research-budget-enforcement (H2) | proposed, needs ruling | `src/sdlc/stages/research/` |
| (new) | Architect research surface: price sub-runs (6.2), honour configured run ceiling and request limit | assessment research-budget-enforcement (6.2, N2, N3); D1 | proposed, needs D1 re-ruling | `src/sdlc/stages/research/toolset.py`, `src/sdlc/stages/architecture/step.py` |

## If go — Handoff

- **Problem**: when a research sub-question hits a bound and the model keeps
  retrying, the stage loses the spend record, retries a doomed activity six
  times and over-charges the shared run ceiling; separately, the budget file
  write is not crash-safe and the retain path reads files in workflow code.
- **Chosen approach**: concept.md, "Recommendation — revised": S-batch, then
  M-1. The S-batch goes straight to an exec run. M-1 goes through
  `/speckit-specify` with a short spec. M-2 is a register row only.
- **In scope**: H3, notes (S-batch); H1, N4, H4 (M-1, if the user takes it).
- **Out of scope**: H5 (queued), H2 residual, N2, N3, 6.2, cap values, attempt budgets,
  the other fail-and-continue Gotchas, the register file.
- **Success metrics**: one test per fixed defect that fails on `269fa29`; a
  sub-question that exhausts a bound shows non-zero research tokens; the E1
  scenarios leave the run counter equal to real work done; clean-run replays
  unchanged. (For M-2, if ever scheduled: no file read reachable from
  `step.py` outside an activity.)
- **Carried-forward open questions**:
  - how often a real model retries a refusal rather than concluding;
  - how to tell budget-caused retry exhaustion from other model failures;
  - whether `calls` should count model requests;
  - whether to lift D1 for 6.2;
  - whether salvaging partial work is wanted at all.

## What would change this recommendation

- **To the S-batch only** (the skeptic's position): the user judges that
  research caps are hit too rarely to justify an M item. The Gotchas already
  warn editors; H3 and the notes are still worth an hour.
- **To schedule M-2 as well**: evidence that research histories are replayed
  on hosts other than the one that ran them.
- **To kill outright**: research is to stay off, including in benchmark
  cases. Then only the notes are worth doing.
- **To needs-clarification**: nothing outstanding blocks the verdict. The
  one open measurement — real model behaviour at a refusal — needs live
  runs, which this pass is not allowed to make.
