# Concept: What to carry when research stops early

- **Slug**: research-partial-salvage
- **Created**: 2026-10-05
- **Recommended option**: **D + B** — D: make the last request the limit
  allows a conclude-only turn (prevention, pending one live check);
  B: keep finished findings when synthesis fails, falling back to today's
  brief if they do not verify. **After-the-fact salvage (C) is declined.**
- **Outcome at the gate (2026-10-05)**: this file records the assessor's
  recommendation. The ruling differs on Option D — it was killed with a
  reopening condition and the live check E8 was not run; Option B is
  queued unscheduled. See decision.md, "Gate ruling".
- **Revised** after skeptic kill-case 1: Option B changed (S1, S2, S6),
  Option D promoted from the set-aside table (S5, E7b), the reopening
  condition for C dropped (S4).
- **Inputs**: problem.md (P1–P3, criteria C1–C8), research.md (E6, E6b,
  E7, E7b; advisor corrections A1–A7; skeptic S1–S10)
- `R/` = `src/sdlc/stages/research/`

## The shape of the choice

The research found that "partial work" is two different things:

- **Finished work that gets dropped** (P2): every sub-question returned a
  brief, synthesis failed, and the stage threw the briefs away. Carrying
  it needs no model call and no judgment — the merge that would have run
  anyway is pure code.
- **Unfinished work** (P1, P3): a sub-question stopped before it wrote a
  brief. What exists is raw history. Turning it into findings needs a
  model to make claims and choose quotes — one more call, by a model that
  has just failed to finish, feeding the one check the stage is known to
  fail (2 of 5 local rows).

The options below differ in how far into the second kind they go. A
third reading came out of the skeptic pass: for the request limit, the
work need not become "unfinished" at all — the run can be made to finish
inside its limit (Option D).

## Options

### Option A — Decline: keep gap-only everywhere

- **Sketch**: Nothing changes. A stopped sub-question and a failed
  synthesis both yield an explained gap; the human may ask for a refine
  round. The assessment is the record of why.
- **Appetite**: none.
- **Trade-offs**: Zero risk, zero comparability change. Leaves P2 — a
  documented trap that discards complete work and restarts refine ids
  against spent budgets — and leaves class-C gaps saying only "Activity
  task failed".
- **Rabbit holes**: none.

### Option B — Keep finished findings when synthesis fails (recommended)

- **Sketch**: When the synthesis step fails for good — model error,
  timeout or lost worker alike — the stage builds its brief from the
  mechanical merge of the sub-question briefs: sources, grounded and
  inferred findings, contradictions, gaps, with a fixed summary saying
  synthesis did not complete, confidence zero, and a stage-level gap. That
  brief is verified like any other. **If it verifies, the human at the
  gate sees everything the wave found, minus the prose. If it does not,
  the stage falls back to exactly today's gap-only brief** and reaches the
  gate as it does today. No model is asked for anything.
- **Appetite**: small (one short spec, one crew run).
- **Trade-offs**:
  - Wins: recovers the largest loss (a whole wave of complete findings)
    at no model cost. Never worse than today on any path: the fallback is
    today's behaviour (C1, answering skeptic S1). Catches every kind of
    synthesis failure because it sits where they all surface (S2). Keeps
    the findings list intact for a following refine round, so ids no
    longer restart against spent budgets — on the path where the merged
    brief verified.
  - Sacrifices: it is workflow code, so it needs a patch marker for
    replay (A2) — more ceremony than an activity-side change.
  - It is all-or-nothing by design: findings that fail verification are
    not filtered or demoted, in line with the project's earlier ruling
    (BENCHMARK.md OQ-B3).
  - Benchmark: a synthesis-failed run that verifies now produces a
    different brief, digest, judge input and retain set. No local row has
    ever taken that path.
- **Rabbit holes**:
  - *The planner-failed case* has no findings and cannot be helped.
  - *The refine loop's* own except branch already keeps the last good
    brief; whether it should also keep newly gathered findings is a
    separate question — leave it.
  - *Synthesis spend*: the failed attempts' usage is lost today and stays
    lost; do not try to fix that here.

### Option C — Wrap-up call after a sub-question has stopped (declined)

- **Sketch**: When a sub-question stops at its request limit or a tool
  budget (classes A, A2 — and B only if evidence supports it), the
  activity makes one further request from the captured history: "stop
  researching, conclude with what you have fetched". The resulting brief
  is checked against the fetched pages inside the activity; grounded
  findings that fail are dropped rather than returned. What survives is
  returned with the usual gap and a marker saying it was concluded after
  an early stop.
- **Appetite**: medium (full spec; touches the activity, the merge and the
  brief or finding model; needs a live-model check first).
- **Trade-offs**:
  - Wins: the only option that addresses the register row as titled.
    Wiring is proven with a scripted model: one request, verifiable
    findings, spend countable (E6 W1a–W1d, W2, W3).
  - Sacrifices: the call is request N+1 of a limit of N — the configured
    bound stops being the bound. Briefs on capped paths change, so
    benchmark rows across the change need a marker (008 precedent) and
    the brief needs a provenance mark that the judge will also see.
  - Risks: whether the production model concludes validly on a long
    history is unmeasured; with tools still offered it may call a tool
    instead of concluding (A5); with no tools offered, the provider may
    reject the history (unmeasured); the drop-what-fails filter is the
    softer-partial behaviour OQ-B3 declined; class B is attributed by
    "a refusal happened", not by cause (A4), and is the case where the
    model has already shown it will not conclude.
- **Rabbit holes**: forcing a conclude turn under CodeMode — the obvious
  hook does not hide `run_code` (E7); a second variant that hands a fresh
  no-tools agent the page texts needs a record of which URLs each
  sub-question fetched, which does not exist (M3); class C would need the
  activity to know it is on its last attempt.

### Option D — Conclude on the last request (recommended, pending one live check)

- **Sketch**: The research agent's final permitted request offers only
  the answer, not the tools. A model that has been researching up to its
  limit is, on its last turn, able to do one thing: write its brief from
  what it has read. The run then ends normally, inside the limit, with an
  ordinary brief that takes the ordinary path. A model that ignores this
  ends exactly as today, with a gap. This is prevention, not salvage: it
  makes the request limit behave the way tool budgets are already
  documented to — "the agent concludes with what it has"
  (`R/deps.py:32-34`).
- **Appetite**: small-to-medium (one spec; one new capability on the
  research agent; no change to the activity's result, the merge, the
  models or the workflow).
- **Trade-offs**:
  - Wins: no request beyond the limit; no second run; no provenance
    marker to invent, because the result is a normal brief; replay-safe
    (activity-side only); costs clean runs nothing, since a tool call on
    the last request can never be read back today. Measured with a
    scripted model (E7b): 3 grounded findings, verified, on request 4 of
    4, where today there is one gap. It addresses the one cap class with
    a recorded incident.
  - Sacrifices: covers the request limit only. Stops caused by tool
    budgets already give the model a chance to conclude; a model dead end
    (class C) is untouched.
  - Risk, and its answer (added after skeptic kill-case 2): a brief
    written on a forced last turn can carry a bad quote, and one
    violation fails the stage where today's gap would have reached the
    gate. So the option includes a **self-check**: when a run ends on its
    conclude-only turn, the sub-question checks that brief against the
    fetched pages before returning it, and if anything fails it returns
    exactly today's gap-only result instead. All or nothing — no finding
    is filtered or demoted. Briefs from runs that conclude on their own
    are not self-checked; nothing changes for them.
  - What the self-check does not settle (skeptic kill-case 3):
    - *Not airtight.* A sibling re-fetching the same URL between the
      self-check and the stage's check can change the page bytes (A6), so
      a forced brief can still fail the stage. The same race exists for
      every clean run today.
    - *A double standard.* A run that concludes on its own with a bad
      quote fails the stage; a run forced to conclude with the same bad
      quote is turned back into a gap. That softens the fail-closed rule
      for one class of run (BENCHMARK.md OQ-B3). Dropping the self-check
      restores the rule and re-opens the "worse than gap-only" path. The
      option cannot have both — this is a ruling for the user.
    - *No room for an output retry.* A brief that fails schema validation
      on the last request cannot be retried inside the limit; it ends as
      today's gap. Reserving two requests instead of one would allow the
      retry at the cost of one request of research.
  - Unknown: whether the production model concludes validly when offered
    only the output tool, and whether it must be told it is on its last
    turn. One live sub-question run with a low request limit answers
    both.
- **Rabbit holes**: how the capability learns the limit (the experiment
  used a constant; the limit is an activity input today, not on deps);
  the architect's mid-run research call uses the same agent with the
  library's default limit — the capability must do nothing unless the
  sub-question run hands it a limit (D1; skeptic 2 showed a constant
  would cut the architect's run short); benchmark rows
  for runs that hit the request limit change from a gap to findings.

### Options considered and set aside

| Option | Why not |
|---|---|
| Mechanical URL list (record fetched URLs, return them as sources on the gap-only brief) | No model call, but the rows carry no assessment and no reader beyond the human's eye; needs a new record on deps for little value. Could ride along with C; not worth doing alone. |
| Record findings as the run goes (a tool that takes quote + claim and verifies on the spot) | The only shape that creates real structured partial state, and it would make stop-time salvage mechanical. But it changes the agent's contract and prompt for every run, so every research benchmark row moves. That is a different, larger idea than this register row; named here so the reader sees why every in-scope salvage option is model-call-shaped. |

## Recommendation

**D, then B. Decline C.** In criteria order (problem.md):

- **C6 grounding unchanged** — D, B: the same verifier, untouched, no
  filtering. C needs a drop-what-fails filter to be safe.
- **C1 never worse than gap-only** — B: holds on every path, by fallback.
  D: holds when the model ignores the conclude turn, and — with the
  self-check — when it concludes with a bad quote. C: fails without a
  filter.
- **C3 replay-safe** — D: activity-side only. B: workflow code behind a
  patch marker.
- **C2 retries** — neither changes which errors are raised or retried.
- **C4 spend** — D and B make no request beyond today's bounds. C is
  request N+1 of N.
- **C5 distinguishable** — B: fixed summary and stage-level gap. D: an
  ordinary brief; the benchmark record needs a marker for runs that hit
  the request limit (008 precedent).
- **C8 blast radius** — D: one capability. B: one except branch plus a
  marker. C: the activity, the merge, a model field.
- **C7 worth carrying (the gate)** — no path here has been observed in a
  fan-out run. D and B pass only on the other leg: each is small. C does
  not pass.

**Why not C.** It is a model-authored brief written after a failure, one
request past the configured limit, feeding the one check the stage is
observed to fail. D reaches the same content for the request limit
without any of that. For the remaining stop classes the model has already
been offered the chance to conclude and did not take it. Draft 1 kept C
alive behind a reopening condition; the skeptic showed that condition
could never be met (S4). It is dropped: C is declined outright. If
structured partial state is ever wanted for the other classes, the
findings-as-you-go idea in the table above is the sound route, and it is
a different, larger proposal.

**The live check D waits on (E8)**: one real sub-question run on the
production model with the conclude-only last turn, ten repetitions, **at
realistic depth** — the configured limit of 40 on a question broad enough
to reach it, or failing that a limit of at least 20 — recording the
context size each run concluded on. (An earlier draft proposed a limit of
6; the skeptic showed that quoting from two pages says nothing about
quoting from thirty.) Because the self-check turns a bad
forced brief back into today's gap, the check measures *value*, not
safety. Pass: at least half the repetitions end normally with a
schema-valid brief whose grounded findings all verify, and every other
repetition ends as today's gap. Fail: fewer than half — then D is declined
and the request limit stays gap-only. The rate is reported either way.
Cost: ten full-length sub-question runs — up to 400 model requests plus
their searches and fetches, no longer "a few short runs". This needs the user's permission; no
live call was made in this pass. (Draft 2 said "verifies in most
repetitions" with no self-check; the skeptic showed that was too soft for
a four-way fan-out where one violation fails the stage.)

**The five design questions**

| # | Question | Answer |
|---|---|---|
| 1 | What partial state exists at death-time? | **Answered (measured).** The full message history, including every fetched page's text, via message capture around the existing call; the page files on disk (not self-describing); no structured partial brief. |
| 2 | Raise vs return in the activity | **Commit: no change.** Request-limit, tool-budget and refusal-then-dead-end stops already return. A model dead end with no refusal keeps raising so it is retried; transient errors keep raising. Salvaging the raising classes is declined. |
| 3 | The stage-level drop | **Commit: fix it** for the synthesis-failed case (Option B), with fallback to today's brief if the kept findings do not verify. Decline for the planner-failed case (nothing to keep). |
| 4 | Salvage cost and comparability | **Decline after-the-fact salvage**: a mechanical fold yields only a URL list; a fold with content costs request N+1. **Commit instead to no extra spend**: D concludes inside the limit; B is mechanical. Marking: B by summary + gap; both by a BENCHMARK.md break marker. |
| 5 | Replay determinism | **Commit**: D is activity-side only. B is workflow code behind a patch marker. Never a new activity on an old branch. Both pinned with the research replay fixture 009 left. |

## Out of Scope (for the recommended options)

- Any model call after a sub-question has stopped (Option C).
- Changing which errors the sub-question activity raises or returns.
- The planner-failed case; the refine loop's except branch.
- Naming the real cause in gaps instead of "Activity task failed" — a
  real defect found here, but unrelated to either option (skeptic S6).
  Proposed as its own small inbox task.
- Reporting the usage of attempts that raise (class C spend, A4) —
  proposed as an inbox task.
- Filtering or demoting findings that fail verification.
- Cap values, attempt budgets, timeouts; the architect research surface
  (D1); the register file.

## Assumptions to Validate

- D: the production model concludes with a valid, verifiable brief when
  offered only the output tool (the live check E8).
- D: the capability can learn the request limit without changing the
  serialized deps of no-override runs, and stays inert on the architect's
  call path.
- B: the pure merge is safe to call from workflow code (it is pure and
  its module does no I/O; the sandbox import marker in `R/step.py:21`
  must cover it).
- B: a merged brief with a fixed summary is acceptable input to the
  research judge rubric (it will score low on summary; that is the honest
  result).
- B: recording PASS for a synthesis-failed-but-merged brief after human
  approval is acceptable — it is what a clean run records, and today the
  same path records PASS for an empty brief.
