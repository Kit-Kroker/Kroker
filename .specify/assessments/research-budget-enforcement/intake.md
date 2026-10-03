# Idea Intake: Research budget-enforcement defect cluster

- **Slug**: research-budget-enforcement
- **Created**: 2026-10-03
- **Source**: pasted text (orchestrator TASK BRIEF) + repo path
  `.workspace/tasks/2026-10-03-research-budget-exhaustion-defects.md`
- **Type**: fix
- **Baseline**: main `269fa29`

## Idea (as captured)

### Inbox card (verbatim, `.workspace/tasks/2026-10-03-research-budget-exhaustion-defects.md`)

> | From | 006 exec run, T011 SG-5 (gotcha verification surfaced live defects; filed by orchestrator) |
> | Size | M (assess first; the five interact — one assessment covers the cluster) |
> | Status | open |
>
> ## Research budget-enforcement defect cluster (five candidates, unfixed by 006)
>
> Found while verifying the B4 Gotchas bullets against the code; 006's SG-5
> correctly documented instead of fixed them:
>
> 1. **Exhaustion zeroes usage — spend under-reported.** When the research
>    budget is exhausted, the recorded usage for the stage reads zero, so the
>    stage's real token spend disappears from pricing/records.
> 2. **Exhaustion discards partial work.** Partial sub-question results
>    produced before exhaustion are dropped instead of carried.
> 3. **Non-atomic budget write.** The budget counter is written without an
>    atomicity guard (replay/retry can double-count or lose a decrement).
> 4. **Run counter not rolled back on scope refusal.** A scope refusal burns a
>    run from the counter without a compensating rollback.
> 5. **`retain` re-runs the verifier in workflow context.** The retain path
>    re-executes verification inside workflow code — a determinism/hazard
>    smell in the E-77 sense.
>
> First step: /speckit-bug-assess or an assess-intake pass on the cluster;
> each defect needs a repro before any fix. Related surface:
> `src/sdlc/stages/research/` (budget enforcement corners are also B4's
> Gotchas subject — `AGENTS.md` gotchas section from f7bf90c).

### Orchestrator TASK BRIEF (verbatim, the five as hypotheses)

> H1 Exhaustion zeroes usage — stage.py's budget/usage-exhaustion handler
>    returns failed=False with zeroed usage; the spend before the cap is
>    lost from the benchmark record.
> H2 Exhaustion discards partial work — partial sub-question findings are
>    dropped for a gap-only brief instead of carried.
> H3 Non-atomic budget write — budget_store.py writes in place (no
>    tmp+replace like write_page); a truncated budget-<scope>.json wedges
>    that scope until manually cleared.
> H4 Run counter not rolled back on scope refusal — charge_scoped charges
>    the run counter first and never compensates a refused scope charge.
> H5 retain re-runs the verifier — retain.py calls verify_brief (real page
>    I/O) from workflow context.

Adjacent traps the brief asks to fold in (not headline defects):

> the budget-lock TimeoutError the exhaustion handler does not catch
> (uncapped retry class); activity retries inheriting the spent allowance
> (attempt N is not a fresh budget); the two stale docstrings (deps.py
> "Task 8 concern", toolset.py "(deferred)").

Scope candidate the brief asks to rule on explicitly:

> defect 6.2 "architect research sub-runs unpriced" (D1 out-of-scope note in
> .workspace/tasks/2026-09-30-model-forwarding-and-single-retry-layer.md,
> Decision D1). The architect's research tool is the registry research_agent
> fan-out. Decide in or out of this cluster's scope WITH reasoning; do not
> silently absorb it.

The D1 note itself (verbatim, lines 61-64 of that file):

> ### Out of scope everywhere here (Decision D1)
>
> Defects 6.2 (architect research sub-runs unpriced) and 6.3 (oversized prompt
> hangs the run) stay out of both 003 and this follow-up unless re-ruled.

## Restated

Five suspected defects in how the research stage enforces and records its
budget (usage reporting on exhaustion, partial-work handling, budget-file
write safety, run-counter compensation, and verifier re-execution in the
retain path) are to be re-verified against main and assessed as one cluster.
The assessment must also fold in three adjacent traps and rule explicitly on
whether defect 6.2 belongs in the cluster.

## Origin & Context

- **Raised by**: the 006 exec-run orchestrator (filed the inbox card); this
  assessment commissioned by the current orchestrator via TASK BRIEF.
- **Trigger**: 006 task T011 / SG-5 — verifying the B4 "Gotchas" bullets in
  `src/sdlc/stages/research/AGENTS.md` against code surfaced live defects,
  which 006 documented rather than fixed.
- **Evidence base named by the brief**: `src/sdlc/stages/research/AGENTS.md`
  section "Gotchas" (code-verified on the 006 branch; to be re-verified on
  main — 007 is said not to have touched this slice).
- **Constraints carried from the brief**: assess-only (no fixes, no test or
  AGENTS.md edits, no commits); writes confined to this directory, with
  consultation answers under `.workspace/tmp/research-budget-enforcement-*.md`;
  any test run only in the `kroker-dev` container; register rows are proposed
  in the decide artifact, never written to
  `docs/reports/external-ideas-2026-09.md`.

## First-Glance Unknowns

- [NEEDS CLARIFICATION: do all five hypotheses still hold on main `269fa29`?
  Each needs a file:line mechanism or a code-verified "not a defect".]
- [NEEDS CLARIFICATION: H3 is stated two ways. The inbox card says the
  counter lacks an atomicity guard so "replay/retry can double-count or lose
  a decrement"; the brief says the file is written in place and a truncated
  file wedges the scope. Are these one mechanism, two, or is only one real?]
- [NEEDS CLARIFICATION: H1 — which record actually loses the spend (stage
  result, benchmark record, pricing), and is any of it recoverable from
  another source?]
- [NEEDS CLARIFICATION: H2 — is dropping partial findings on exhaustion an
  oversight or a deliberate design choice recorded somewhere?]
- [NEEDS CLARIFICATION: H5 — does `verify_brief` really execute in workflow
  context on the retain path, or inside an activity?]
- [NEEDS CLARIFICATION: how do the five interact (the card says they do) —
  shared code paths, ordering constraints between fixes?]
- [NEEDS CLARIFICATION: are the three adjacent traps defects, documented
  behaviour, or doc-only cleanups?]
- [NEEDS CLARIFICATION: 6.2 — does the architect's research fan-out share the
  budget/usage code paths of this cluster, and has D1 been re-ruled since
  2026-09-30?]
- [NEEDS CLARIFICATION: is anything in this cluster already fixed or
  superseded by work landed after the 006 branch point?]
