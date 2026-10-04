# Decision: What to carry when research stops early

- **Slug**: research-partial-salvage
- **Decided**: 2026-10-05 — **FINAL.** Ruled at the USER GATE by the
  orchestrator under the user's standing delegation of 2026-10-05
  («принимай все рекомендованое на гейтах»), after one advisor consult and
  three skeptic passes. The user was not present; the ruling is reported
  to them first thing.
- **Verdict**: **kill** for the register row and for everything that
  would be built now; one item queued. In three parts —
  1. **kill** — after-the-fact salvage of a stopped sub-question
     (register row C11 as titled). Runs that have stopped stay gap-only.
     No reopening condition.
  2. **kill, with a reopening condition** — make the last request the
     limit allows a conclude-only turn. The live check E8 is declined and
     was not run. *Reopens when* a request-limit stop is observed in a
     real fan-out run; any live check then must run at realistic depth,
     meet a bar of at least 90% verbatim quotes, and come with a page
     snapshot story that closes the sibling re-fetch race.
  3. **go, queued unscheduled (M)** — keep the finished sub-question
     findings when synthesis fails, falling back to today's brief if they
     do not verify. *Becomes urgent when* a synthesis failure is observed
     in a real run.
- **Assessor's recommendation going into the gate**: 1 kill; 2
  needs-clarification (with the note that declining was at least as
  defensible); 3 go, small, not urgent.
- **Skeptic's final position**: kill on all three. The ruling follows the
  skeptic on parts 1 and 2 and the assessor on part 3; the skeptic's
  return-on-effort reading of part 3 is noted.
- **Artifacts reviewed**: intake.md, research.md, problem.md, concept.md
- **Baseline**: main `bcfbffc`
- **Evidence tiers**: *measured* (scripted model in `kroker-dev`), *read*
  (seen in code, not run), *hypothesis* (neither).
- **Consultations**: advisor —
  `.workspace/tmp/research-partial-salvage-advisor-1.md`; skeptic —
  `.workspace/tmp/research-partial-salvage-skeptic-1.md`,
  `.workspace/tmp/research-partial-salvage-skeptic-2.md`,
  `.workspace/tmp/research-partial-salvage-skeptic-3.md`. Briefs sent to
  both are in `consults/`.
- `R/` = `src/sdlc/stages/research/`

## Gate ruling (2026-10-05)

Given by the orchestrator under the user's standing delegation; quoted in
substance.

| # | Question | Ruling |
|---|---|---|
| Q1 | Decline register row C11 as titled? | **Yes.** Both seats agree. |
| Q2 | Permit the live check E8 for part 2, or decline? | **Decline E8. Part 2 is killed with a reopening condition**, not left at needs-clarification. Reasons, verified by the orchestrator against code: the cheap form of the check (limit 6, roughly 5k tokens of context) decides nothing about the regime that matters (30+ requests, 80k+ tokens); the representative form needs the frequency precondition first — a request-limit stop seen in a real fan-out run — plus a page story that survives a sibling's overwrite (`R/verify.py:59`, `os.replace`); and the closeness to BENCHMARK.md OQ-B3 is real. |
| Q3 | Part 3: build, queue, or decline? | **Queue unscheduled, size M.** The assessor's go-small stands recorded; the skeptic's return-on-effort reading is noted. |
| Q4 | Accept the four inbox candidates? | **All four accepted.** The orchestrator verified the anchors and files the cards. |

**Reopening conditions**

- *Part 2*: a request-limit stop observed in a real fan-out run. Any
  future live check runs at realistic depth, with a bar of at least 90%
  verbatim quotes and a snapshot story that closes the sibling race.
- *Part 3 → urgent*: a synthesis failure observed in a real run.
- *Part 1*: none. If structured partial state is ever wanted, the route
  is recording findings as the run goes (concept.md, set-aside table) — a
  different, larger proposal.

## How the recommendation changed across drafts

Draft 1 recommended a small go on "keep findings when synthesis fails,
unfiltered, plus name the real cause in gaps", and a kill-for-now on
sub-question salvage with a reopening condition. The skeptic's kill-case
was upheld on five points (research.md, S1–S6):

- Unfiltered kept findings could end a run before the human gate where
  today's gap-only brief reaches it. **Fixed**: fall back to today's brief
  when they do not verify.
- A fallback inside the synthesis activity misses timeouts. **Fixed**: it
  sits in workflow code, where every synthesis failure surfaces.
- The cause-string fix was bundled in. **Split out** as an inbox task.
- The reopening condition could never be met — production keeps no
  message history. **Dropped**; after-the-fact salvage is declined
  outright.
- I had set aside "reserve the last request" after testing the wrong
  hook. **Tested with the right one (E7b)**: it works on a scripted
  model, and it became part 2.

Not upheld: that cheap offline checks could replace a live call.

The second kill-case (on draft 2) was upheld on three more points
(research.md, T1–T3):

- Part 2 left a residual open — a forced last turn with a bad quote would
  fail the stage where a gap reaches the gate. **Answered** with a
  self-check in the sub-question that falls back to today's gap-only
  result.
- The live check's pass criterion ("verifies in most repetitions") was
  too soft for a four-way fan-out. **Restated** as an explicit threshold.
- A limit held as a constant would cut the architect's research short.
  **Made a requirement**: the mechanism does nothing unless the
  sub-question run hands it a limit.

The third kill-case (on part 2 as revised, at the orchestrator's gate
hold) was upheld on four points (research.md, U1–U5), and they decided
part 2:

- The self-check is not airtight: a sibling re-fetching a page between
  the two checks can still fail the stage.
- The self-check is a double standard: a forced run's bad quote becomes a
  gap, a self-concluding run's bad quote fails the stage — a softening of
  the fail-closed rule (OQ-B3) for one class of run. Without it the
  option can end worse than today. It cannot have both.
- The live check at a limit of 6 says nothing about a 40-request history;
  at realistic depth it is ten full-length runs.
- One conclude-only turn leaves no room for the agent's single output
  retry.

Not upheld from the third pass: that the last request is "wasted" (it is
spent today too, on a tool call nobody reads), and that two capped
sub-questions multiply the failure rate (with a fallback each stands
alone).

## What the assessment found

1. After 008, the stops the register row names are handled inside the
   sub-question activity; that handler is where the work is dropped.
   (read; measured E6)
2. At that moment the full message history could be read — if capture
   were added; production does not capture it today. There is no
   structured partial finding. (measured)
3. Turning a stopped run's history into findings needs a model call:
   request N+1 of a limit of N. Code alone recovers a URL list at most.
   (measured wiring + read)
4. For the request limit there is a way not to stop at all: offer only
   the answer on the last permitted request. A scripted model then ends
   normally inside the limit with verified findings; a model that ignores
   it ends exactly as today. (measured, E7b) Whether the production model
   complies is unmeasured.
5. One level up, a synthesis failure discards every sub-question's
   *finished* brief; keeping them needs no model call. (read; documented
   in `R/AGENTS.md:49-54`)
6. Nothing downstream reads the brief's content — only a digest. Its
   readers are the human at the gate, the judge, and memory. (read)
7. No local record shows any of these stops. The one failure the records
   show is grounding (2 of 5 research rows). The one recorded cap incident
   is a request-limit stop, before fan-out existed. (cited)

## The five design questions

| # | Question | Outcome | Tier |
|---|---|---|---|
| 1 | What partial state exists at death-time? | Answered: message history (complete, if captured), page files (not self-describing), no structured brief. | measured |
| 2 | Raise vs return in the activity | **No change.** Cap and refusal stops already return; a model dead end with no refusal and transient errors keep raising and being retried. | read |
| 3 | The stage-level drop | **Fix, queued** for synthesis failure: keep the findings via the existing pure merge, verify, and fall back to today's brief on any violation. **Decline** for planner failure (nothing to keep). | read |
| 4 | Salvage cost and comparability | **Declined: no extra model call, and no salvage of a stopped sub-question at all.** Part 3, when built, is mechanical and is marked by a fixed summary, a stage-level gap and a BENCHMARK.md note. | measured + read |
| 5 | Replay determinism | Part 3 is workflow code behind a patch marker. Never a new activity on an old branch. Pinned by the research replay fixture. (Part 2, if reopened, is activity-side only.) | read |

## Scorecard

| Criterion | 1. After-the-fact salvage | 2. Conclude on last request | 3. Keep findings on synthesis failure |
|---|---|---|---|
| Problem validity | **weak** — never observed; the gap already explains the shortfall | **adequate** — the one recorded cap incident is this class; the documented contract ("concludes with what it has") is not honoured for this limit | **adequate** — complete work discarded; a trap the slice's notes record |
| Evidence strength | adequate for mechanism; **unknown** for real-model behaviour | adequate for mechanism (E7b); **unknown** for real-model behaviour | **adequate** — read at file:line; not run; frequency unknown |
| Value vs. inaction | **weak** | adequate if the model complies | adequate |
| Feasibility / appetite | **weak** — medium, a request past the limit, a filter the project has declined before | **adequate** — one capability; open point on how it learns the limit | **strong** — small; a pure function to reuse |
| Strategic fit | **weak** — against OQ-B3's hard-fail ruling | **strong** — makes the request limit follow the stage's own stated contract | adequate — follows the slice's stated intent (`R/models.py:90-94`) |
| Risk posture | **weak** — model-authored quotes after a failure, into the check the stage is seen to fail | **weak** after the third pass — the self-check is not airtight and softens the fail-closed rule; without it a forced turn can fail the stage | **strong** — never worse than today, by fallback |

No constitution check was made. The scorecard is the assessor's; the
part 2 risk rating was lowered after the third skeptic pass.

## Verdict & Rationale

**1. After-the-fact salvage — kill.** The only version with content is a
model call past the configured limit, by a model that has just failed to
finish, feeding the stage's weakest check, for a stop nobody has seen.
Code alone recovers a URL list at most. The register row said it might be
declined; this is that decline. No reopening condition.

**2. Conclude on the last request — kill, with a reopening condition.**
The mechanism works on a scripted model and is harmless when the model
ignores it (E7b). What killed it at the gate:

- No request-limit stop has been observed in a fan-out run, so there is
  nothing yet to justify the cost of finding out whether the production
  model complies.
- The check that would find out is only meaningful at realistic depth
  (30+ requests, 80k+ tokens of context); the cheap version decides
  nothing.
- The option has no clean form: with a self-check it softens the
  fail-closed grounding rule for forced runs and still leaves a re-fetch
  race; without one, a forced turn can fail the stage where today's gap
  reaches the human gate.

*Reopens when* a request-limit stop is observed in a real fan-out run.
Any live check then must run at realistic depth, meet a bar of at least
90% verbatim quotes, and come with a page snapshot story that closes the
sibling re-fetch race. E8 was not run.

**3. Keep findings on synthesis failure — go, queued unscheduled, M.**
Complete work, no model call, never worse than today by fallback, removes
a documented trap. Nothing depends on it, so it waits. *Becomes urgent
when* a synthesis failure is observed in a real run.

The honest weaknesses, which stand:

- Nothing here has been seen in a real fan-out run, part 3's synthesis
  failure included.
- Part 3 is not what the register row asked for; it came out of design
  question 3.
- Part 3 pays off only when synthesis fails *and* every kept quote
  verifies. With 2 of 5 local rows failing grounding, that is a narrow
  window on a failure never seen. The skeptic would not build it.
- Part 3 adds a fallback path — code that runs rarely and is tested only
  by fakes.

## Handoff to `/speckit-specify` (part 3 — when it is scheduled)

- **Problem**: when the synthesis step fails, the research stage discards
  every sub-question's finished findings and substitutes a stage-level
  gap, and the next refine round restarts ids against spent budgets.
- **Chosen approach**: concept.md Option B. On final synthesis failure the
  stage merges the findings mechanically (fixed summary, zero confidence,
  a stage-level gap), verifies the result, and uses it if clean; on any
  violation it falls back to exactly today's gap-only brief.
- **Size**: M (one short spec, one crew run). Tests first, in
  `kroker-dev`.
- **In scope**: the synthesis-failed path in `R/step.py`; a patch marker;
  a BENCHMARK.md note; the fail-and-continue bullets in `R/AGENTS.md`.
- **Out of scope**: any model call for a stopped sub-question; which
  errors the sub-question activity raises; the planner-failed case; the
  refine loop's except branch; filtering or demoting findings; the cause
  string; cap values, attempt budgets, timeouts; D1; the register file.
- **Success metrics**: a test where synthesis fails with k successful
  sub-questions yields a brief with their findings (fails on `bcfbffc`);
  a test where one kept finding does not verify yields today's brief and
  reaches the gate; clean-run activity inputs and results byte-identical;
  the research replay fixture unchanged; an old-shape history replays.
- **The spec must rule on**: the patch marker's placement; whether the
  merged-brief path calls the verify activity once or twice on fallback
  (the command sequence under the marker); the wording of the fixed
  summary and gap.
- **Carried-forward open questions**: frequency of every path; whether a
  stored history with a synthesis failure exists; how the judge rubric
  treats a fixed summary.

## Follow-ups (accepted at the gate; filed by the orchestrator)

Nothing outside this directory was written by the assessor.

Inbox tasks, all four accepted:

- **Gaps say "Activity task failed" instead of the cause.** `str()` of
  the gathered error is generic (`R/step.py:110`, `:90-102`;
  `tests/replay/golden/context_reject.json:2`); the cause is on the
  error's cause chain. S. The string flows into activity inputs; whether
  the replay fixtures compare those was not checked (skeptic T5) — the
  task must check before it changes workflow-side text.
- **Spend of attempts that raise is unreported.** A sub-question that
  dies of a model dead end with no refusal is retried up to 6 times; no
  attempt's usage reaches the record (`R/stage.py:329-330`,
  `R/step.py:109-110`).
- **Dead configuration.** `non_retryable_error_types` at `R/step.py:64`
  names two errors the activity now always catches.
- **Output retries are 1** on the research agent (measured: "Exceeded
  maximum output retries (1)"): one malformed final brief ends an attempt
  and restarts the research.

Wording for register row C11 (the register is user-owned; the
orchestrator applies this verbatim):

> Declined 2026-10-05 — assessment `research-partial-salvage`. Salvaging a
> stopped sub-question after the fact needs a model call past the request
> limit, into the grounding check; code alone recovers only a URL list.
> Prevention ("conclude on the last permitted request") killed pending an
> observed request-limit stop in a real fan-out run; a future live check
> must run at realistic depth with a ≥90% verbatim bar and page snapshots
> that close the sibling re-fetch race. Split out and queued unscheduled
> (M): keep finished findings when synthesis fails, falling back to
> today's brief if they do not verify — urgent if a synthesis failure is
> observed in a real run.

## What would change this decision

- **Part 2 reopens**: a request-limit stop is observed in a real fan-out
  run (see the reopening condition).
- **Part 3 becomes urgent**: a synthesis failure is observed in a real
  run.
- **Part 3 is dropped**: the user takes the skeptic's reading of return
  on effort on review.
- **Part 1**: nothing in view.
