# Feature Specification: Research Cap Handling

**Feature Branch**: `008-research-cap-handling` (spec directory only; the branch is cut in the `D:\own\Kroker-007` worktree at exec)

**Created**: 2026-10-04

**Status**: GATE 1 cleared 2026-10-04; all four questions ruled A (see [GATE 1 rulings](#gate-1-rulings)); consult amendments A1-A8 added the same day

**Input**: M-1 of assessment `research-budget-enforcement`: defects H1, N4 and H4. Source of truth: `.specify/assessments/research-budget-enforcement/decide.md` (USER GATE outcome 2026-10-03: go for M-1). Measured evidence: E1/E2 in `.workspace/tmp/research-budget-enforcement-experiments.md`; E3 (this spec phase) in `.workspace/tmp/research-cap-handling-e3.md`.

**Base**: main `c2d9b12`.

## Context and verified findings

When a research sub-question hits one of its bounds, three things go wrong together. The model spend it already incurred is recorded as zero. If the model keeps retrying a refused tool call, the run ends in an error the stage does not handle, and the activity is retried up to six times against a cap that stays exhausted. Every refused call also charges the run ceiling that all sub-questions share. All three sit in one handler and one counter.

Every claim below was checked by reading the code on main `c2d9b12` and the installed packages (`pydantic-ai-slim` 2.51.0). E3 was run in `kroker-dev`; nothing else was run. `R/` = `src/sdlc/stages/research/`. Line numbers are for `c2d9b12` and differ slightly from `decide.md`, which was written on `269fa29`.

| # | Claim (from the brief or decide.md) | Verified state | Consequence for this spec |
|---|---|---|---|
| V1 | H1: exhaustion returns zero usage | **True.** A zero `RoleUsage` is built before the run (`R/stage.py:244`) and returned unchanged by the exhaustion handler (`:278-283`). The workflow skips a zero-token usage entirely (`R/step.py:140-141`): no pricing, no tokens, no call counted. | FR-001, FR-002. |
| V2 | A caller-owned usage object holds the spend across an abort | **Measured** (E2; again in E3 under CodeMode: 4 requests held in every probe). | The fix primitive exists. FR-001. |
| V3 | N4: `UnexpectedModelBehavior` is not handled | **True.** The handler catches `BudgetExceeded` and `UsageLimitExceeded` only (`R/stage.py:278`). The error is raised by the library when a tool exceeds its retries (`pydantic_ai/tool_manager.py:299-308`), and separately when output retries run out (`pydantic_ai/_agent_graph.py:396-399`). | FR-003. The same error class has two library sources; see Q3. |
| V4 | The escaped error is retried six times, then recorded as failed with zero usage | **Read, not run.** `maximum_attempts=6` (`R/step.py:63`); the error is not in the non-retryable list (`:64`); an exception result becomes `failed=True` with default usage (`R/step.py:109-110`, `R/models.py:98`). | FR-003, FR-004. |
| V5 | H4: a refused scope charge leaves the run counter charged | **True.** `charge_scoped` commits the run charge, then the scope charge may refuse (`R/budget_store.py:137-138`); nothing compensates. Measured in E1 (run 5 vs scope 1; 12 vs 1) and again in E3 (5 and 12 tool calls for 1 real search). | FR-006, FR-007. |
| V6 | Hypothesis: the non-retryable list lives only at `R/step.py:64` | **True.** It is the only `non_retryable_error_types` naming these errors in `src/` and `agents/`. The only other such list is unrelated (`src/sdlc/workflows/crew.py:106`). The graph path calls the same `research.step` (`workflows/graph_nodes/precode.py:90`), so there is no second activity configuration. | One list, one place. Q4. |
| V7 | Hypothesis: what must the handler catch so that nothing NEW becomes a workflow failure | **Nothing new can.** Today the escaped error already ends as a failed finding, not a workflow failure: the fan-out gathers with `return_exceptions=True` (`R/step.py:193-209`) and the whole fan-out sits inside the stage's `try` (`:254-271`). Pricing a usage cannot fail the stage either (`R/step.py:143-156`). The change moves one case from "six attempts, then failed" to "one attempt, degraded". | FR-005 keeps every other error on today's path. |
| V8 | Hypothesis: `SubQuestionFinding.usage` needs a constructor-level guard against the zero default | **No, and a guard would be harmful.** The zero default is correct for a finding built from an exception (`R/step.py:110`): the attempts raised, so no usage ever came back. The model also crosses the activity boundary, so a validator that rejects zero usage would refuse to decode findings in histories recorded before this change, where a capped sub-question carries exactly that. | No guard. The rule is enforced at the handler and by test (FR-002). Stated in Assumptions. |
| V9 | `calls` counts sub-questions, not model requests | **Roughly true; more exactly it counts priced activity results.** Each run reports `calls=1` (`R/stage.py:67`) and the workflow adds 1 per folded usage (`R/step.py:157`), so a research row's `calls` is the planner, plus each sub-question that reported tokens, plus synthesis. | Q2. A capped sub-question will add 1, like any other. |
| V10 | How a budget-caused retry exhaustion can be told from any other | **Measured (E3).** The exception type does not survive the code sandbox: the chain is `UnexpectedModelBehavior` -> `ModelRetry` -> a sandbox error whose text starts `Exception: search budget exhausted`; no link is a `BudgetExceeded`. Only the text of the LAST failed call survives. The tool does run in-process with the caller's own deps object, and a record owned by the caller saw every refusal (4 and 11) and none for an unrelated tool failure. | Q3. Type-based chain inspection is ruled out by measurement. |
| V11 | Exhaustion keeps `failed=False` | **Pinned.** `tests/research/test_research_subquestion_activity.py:62-79`. | FR-004. |
| V12 | The non-retryable names are pinned by a test | **True**, and only by membership: `tests/research/test_research_fanout_wiring.py:64-69` asserts the two existing names are present. | Q4. |

**Additional findings (not in the brief).**

- **N1 — the refused-charge fix also changes the architect path.** The architect's research tool charges through the same `charge_scoped` with `scope="architect"` (`R/toolset.py:16-70`, `R/AGENTS.md:104-107`). After FR-006 a refused architect-scope charge no longer charges the run counter either. This is a correction to shared code, not a change to the architect surface (6.2, N2, N3 stay out; D1 is in force).
- **N2 — the architect path keeps its own version of N4.** `research_subquery` catches `BudgetExceeded` only (`R/toolset.py:60`). A retry exhaustion there still escapes the architect's tool activity. Out of scope with the rest of the architect surface; named so nobody reads this feature as fixing it.
- **N3 — a lock timeout can also end in retry exhaustion.** Under CodeMode a tool-side `TimeoutError` becomes a retry prompt first (inferred from E1's mechanism, not run). It is transient, so retrying the activity is right, and FR-005 leaves it on today's path.
- **N4 — the slice's own notes will be wrong after this lands.** Two Gotchas bullets in `R/AGENTS.md` describe the defects as current behaviour (`:58-62` zeroed usage; `:99-103` run counter never rolled back). FR-011.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A capped sub-question reports what it spent (Priority: P1)

Someone reads the benchmark row for a research run in which one sub-question ran out of requests or budget. The row includes the tokens that sub-question used before it stopped. Today it shows none for that sub-question.

**Why this priority**: This is the only defect of the three that silently corrupts a record on an ordinary run, and research is switched on in exactly the benchmark cases where the record is the product.

**Independent Test**: Run one sub-question with a scripted model against a request limit it exceeds; assert the returned finding is degraded, not failed, and carries the tokens of every completed request.

**Acceptance Scenarios**:

1. **Given** a sub-question that exceeds its request limit after N completed model requests, **When** it ends, **Then** the finding is a degraded brief with `failed` false and its usage holds the tokens of those N requests.
2. **Given** a sub-question whose run ends on a refused budget charge, **When** it ends, **Then** the same holds.
3. **Given** a capped sub-question that reported tokens, **When** the stage records its row, **Then** those tokens and their price are in the research spend, and the sub-question counts as one call.
4. **Given** a sub-question that completes normally, **When** it ends, **Then** its finding and usage are exactly as today.

---

### User Story 2 - A refused charge costs the run nothing (Priority: P2)

A sub-question that has used its own allowance keeps asking for more searches. Each request is refused. The run ceiling shared with its siblings does not move.

**Why this priority**: The leak is what turns one stubborn sub-question into a problem for the others: E1 measured 4 phantom run charges for 1 real search, 11 with a three-way gather. It must land before or with US3, so that degrading instead of retrying does not leave the leak in place.

**Independent Test**: Charge a scope at its cap, directly and through three concurrent calls; assert the run counter equals the number of calls that were accepted.

**Acceptance Scenarios**:

1. **Given** a sub-question scope at its cap, **When** a further charge is refused, **Then** the run counter is unchanged.
2. **Given** the run ceiling reached, **When** a charge is refused, **Then** the sub-question scope counter is unchanged (today's behaviour, kept).
3. **Given** three concurrent charges against a scope with room for one, **When** they settle, **Then** exactly one is accepted and both counters show one.
4. **Given** the E1 scenarios S1, S2 and S3, **When** re-run, **Then** the run counter shows 1 search, equal to the scope counter.

---

### User Story 3 - A sub-question that keeps hitting a refused bound degrades once (Priority: P3)

A sub-question's model ignores the refusal and retries until the tool gives up. The sub-question ends in one attempt as a degraded brief that names the bound it hit and reports its spend. It is not retried five more times against the same exhausted cap.

**Why this priority**: On the production path this is where the budget-cap loss actually goes (E1 S4). It comes third only because it depends on US1 for the usage and on US2 for the leak.

**Independent Test**: Run one sub-question through the real stage handler with a scripted model that retries a refused call until the tool's retries run out; assert one degraded finding with non-zero usage and no raise. Repeat with a tool that fails for an unrelated reason; assert the error still propagates.

**Acceptance Scenarios**:

1. **Given** a run that ends in tool-retry exhaustion after at least one refused budget charge, **When** the handler sees it, **Then** it returns a degraded finding with `failed` false, non-zero usage, and a gap that names the refused bound.
2. **Given** a run that ends in the same error with no refused charge, **When** the handler sees it, **Then** the error propagates and the activity is retried as today.
3. **Given** scenario 1, **When** the stage continues, **Then** the sub-question made one activity attempt, not six.

### Edge Cases

- **EC1** A run that is refused before any model request completed has zero tokens. It is still skipped by the fold, as today; nothing is priced.
- **EC2** The model sees the refusal and concludes with a valid brief: nothing changes except that the run counter no longer carries the refused charge (US2).
- **EC3** A refusal is followed by a different terminal error — an output the model cannot get valid, or a script that swallowed the refusal and then failed. Which side of FR-003 this falls on is Q3. E3's probe for it did not measure it (the sandbox rejected the script before any tool ran).
- **EC4** A lock timeout that ends in retry exhaustion is not exhaustion (N3): it propagates and is retried.
- **EC5** An attempt that fails for a reason other than exhaustion still loses its spend, because a raised activity returns nothing. Known residual (decide.md); not fixed here.
- **EC6** A crash between the two counter writes of one accepted charge can leave the counters one call apart. The plan states which direction is possible and why; it must never be the direction that hands budget back.
- **EC7** Charge-before-work: an accepted charge whose provider call then fails stays charged. "Real work done" in the success metrics means accepted charges, not successful provider calls. Unchanged.
- **EC8** Every sub-question degrades: the stage goes on to synthesis over gap-only briefs, as it does today for exhaustion. The all-failed shortcut does not fire, because degraded is not failed.
- **EC9** A history recorded before this change holds capped findings with zero usage. Replay takes them from history and is unaffected.
- **EC10** The architect's research tool: refused charges stop leaking (N1); its own uncaught errors are untouched (N2).

## Requirements *(mandatory)*

### Functional Requirements

**Spend at the cap (H1)**

- **FR-001**: A sub-question run MUST account its model usage in an object owned by the caller, so that the usage survives a run that ends in an exception.
- **FR-002**: Whenever a sub-question ends in exhaustion — request limit, a refused budget charge, or the case in FR-003 — the returned finding MUST carry the usage of every model request completed in that attempt. A test MUST fail on `c2d9b12` for this.

**Retry exhaustion caused by a refusal (N4)**

- **FR-003**: When a sub-question run ends in `UnexpectedModelBehavior` and a budget charge was refused during that run, the handler MUST return a degraded finding instead of raising. How "a budget charge was refused during that run" is established is Q3; it MUST NOT depend on the exception type surviving the sandbox (V10).
- **FR-004**: A finding degraded under FR-003 MUST have `failed` false, MUST name the refused bound in its gap (not only the library's retry message), and MUST be logged. A test MUST fail on `c2d9b12` for this.
- **FR-005**: Every other error MUST behave as today: it propagates, the activity is retried under the existing policy, and a final failure becomes a failed finding. In particular an `UnexpectedModelBehavior` with no refused charge MUST NOT be treated as exhaustion. A test MUST cover this.

**The run counter (H4)**

- **FR-006**: A charge refused by either counter MUST leave both counters unchanged. This MUST hold for concurrent charges within one run. A test MUST fail on `c2d9b12` for the scope-refuses direction.
- **FR-007**: The existing guarantees MUST hold: a sub-question is not billed for work the run ceiling refused; the single-counter path for `scope == "run"` charges once; counters are written atomically and an unreadable counter is never reset.
- **FR-008**: FR-006 MUST land before or in the same change as FR-003.

**What new runs record**

- **FR-009**: A capped sub-question that reported tokens is priced and counted like any other: one more pricing activity, one more call, more tokens and more cost on the research row, and a higher total for the run budget gate to read (Q1, Q2). This MUST be stated where benchmark readers will find it, with the commit from which it applies. Rows recorded before it are not rewritten.
- **FR-010**: Runs that hit no cap MUST be unchanged in behaviour, spend, records and scheduled activities. Existing replay and golden suites MUST pass unmodified and MUST NOT be re-recorded.
- **FR-011**: The slice's notes MUST describe the code after the change: the two Gotchas bullets in N4 and any docstring that states the old behaviour. Edits to `AGENTS.md` need orchestrator approval.

**Boundaries**

- **FR-012**: Out of scope, binding (decide.md): the retain path (M-2 / H5); salvaging partial work (H2 residual); the architect research surface (6.2, N2, N3 — D1 is in force); cap values; attempt budgets and timeouts; the other fail-and-continue Gotchas; the register file. This feature MUST NOT change what the model is told at a cap.
- **FR-013**: Repository constraints apply: the 1000-line ceiling per file (`R/step.py` 387, `R/stage.py` 414 today); tests run only in `kroker-dev`, never the host venv, never alongside a live pipeline run; the user's uncommitted files are not touched (`agents/dev/agent.yaml`, `agents/devops/agent.yaml`, `src/sdlc/core/models.py`, the 2026-09-22 retro, the two canvas HTML files).

### Key Entities

- **Sub-question finding**: one sub-question's result — a partial brief, its model usage, and whether it failed.
- **Degraded finding**: a finding whose brief is a single gap explaining why research stopped early; `failed` is false.
- **Exhaustion**: a sub-question ending because a bound was hit — the request limit, a budget cap, or (FR-003) tool retries spent on a refused charge.
- **Run counter / scope counter**: the persisted tallies of accepted tool charges for the whole run and for one sub-question.
- **Refused charge**: a charge that would cross a cap; it is not accepted and, after this feature, leaves no trace on either counter.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A sub-question that exhausts a bound shows non-zero research tokens in its finding and in the stage's research spend (baseline: zero).
- **SC-002**: Each of the three defects has at least one test that fails on `c2d9b12` and passes after the change.
- **SC-003**: The E1 scenarios leave the run counter equal to the accepted charges: 1 search in S1, S2 and S3 (baseline: 5, 2 and 12).
- **SC-004**: A sub-question that ends in retry exhaustion after a refusal makes 1 activity attempt (baseline: 6) and returns a degraded finding.
- **SC-005**: A retry exhaustion with no refusal behaves exactly as on the baseline.
- **SC-006**: Clean-run replays and golden suites pass unmodified.
- **SC-007**: A benchmark reader can find, in one place, that capped research runs record more spend from this change on, and from which commit.

## Assumptions

- Production research runs with the `exa` provider under CodeMode (`agents/research/agent.py:49-54`). With `fake` or `tavily` no budget is charged, so FR-003 and FR-006 are reachable only on `exa`.
- No constructor-level guard is added to `SubQuestionFinding.usage` (V8).
- The experiments use a scripted model and a plain function tool, not the Exa toolset. How often a real model retries a refusal rather than concluding is not known and is not measurable without live runs.
- The E1 and E2 scripts are reused as the starting point for the failing tests; E3's script is kept beside them.
- All verification runs happen in `kroker-dev`, bound to the `D:\own\Kroker-007` worktree.
- Commit messages carry a subject and a body and no attribution trailers.

## GATE 1 rulings

User rulings relayed by the orchestrator, 2026-10-04. No open questions remain.

- **Q1 = A, a written note only.** FR-009 and SC-007 stand.
- **Q2 = A, `calls` keeps its meaning.** A capped sub-question adds 1.
- **Q3 = A, the caller-owned refusal record.** FR-003 stands. The EC3 consequence (any `UnexpectedModelBehavior` after a refusal degrades and is not retried) is accepted knowingly.
- **Q4 = A, the non-retryable list does not change.**
- **FR-011 is pre-approved**, bounded to the two Gotchas bullets that turn false (`R/AGENTS.md:58-62` zeroed usage, `:99-103` run-counter rollback) and any docstring that states the old behaviour. Nothing else in `AGENTS.md` is edited.

## Post-GATE-1 consult amendments

From the advisor (`.workspace/tmp/advisor-008-1.md`) and skeptic (`.workspace/tmp/skeptic-008-1.md`) consults and probe E4 (`.workspace/tmp/research-cap-handling-e4.md`), each re-checked in code or by probe by the spec lead. They correct facts and wording. No GATE 1 ruling changes; A2 widens what the Q3 ruling was described as accepting and is carried to GATE 2.

- **A1 (FR-004) — the summary carries the reason too.** A degraded brief's `summary` is what the synthesis prompt embeds (`R/stage.py:355`); the gap's text is what a refine replan embeds (`:86`). FR-004 is read as: both the gap and the summary name the refused bound, both come from one text, and the library's advice and docs URL are cut from it.
- **A2 (EC3, Q3) — a transient failure after a refusal also degrades.** If a charge is refused and a later tool call then fails for a passing reason (a provider outage, a sibling call in the same gather), the run still ends in `UnexpectedModelBehavior` with a non-empty record, so it degrades instead of being retried. This is inside the EC3 class GATE 1 accepted, but EC3's examples did not show it. The gap names both the refusal and the terminal error.
- **A3 (FR-010, SC-006) — the replay suites do not run a sub-question activity.** `research_greenfield` fakes the planner into an empty decomposition (`tests/replay/scenarios.py:135-146`). FR-010 is therefore carried by: no workflow code and no activity configuration changes; the activity input is byte-identical (a new test pins it); a clean run's usage is unchanged (measured in E4, pinned by a new test). SC-006 is read as a regression check on the wire and the workflow, not as evidence about the sub-question activity.
- **A4 (FR-009, SC-007) — the note names the date and the feature, not a commit.** The place is `BENCHMARK.md`, beside the 005 cost-history marker (`BENCHMARK.md:20-32`), in the same form. A commit cannot contain its own hash; "from which commit" is read as "from feature 008, dated".
- **A5 (FR-003) — the record says which counter refused.** A cost refusal's message does not say whether the run ceiling or the sub-question's allowance tripped (`R/deps.py:92`). The record adds that. The exception text the model sees is not changed (FR-012).
- **A6 (EC6) — the crash leftover is "scope one ahead of run".** Counters are written scope first, run last. The charge precedes the work, so a crash between the writes leaves one phantom charge on that sub-question's own allowance and nothing on the shared ceiling. Real work is always covered by both counters.
- **A7 (FR-013) — `CLAUDE.md` is not a user file here.** Its uncommitted change is the spec-kit plan pointer, like `.specify/feature.json`. It is removed from the list of the user's uncommitted files; no implementation task edits it.
- **A8 (FR-011) — one more docstring.** `charge_scoped`'s docstring says the run counter is charged first (`R/budget_store.py:111-117`); that goes stale and is rewritten. It is inside the pre-approval (a docstring stating the old behaviour).

## Open Questions — GATE 1 (as asked)

Kept for the record. Each was written into the spec at its recommended answer, and each was ruled at that answer on 2026-10-04.

- **Q1 — How is the break in benchmark history named?** After this change a capped sub-question is priced: one extra pricing activity, and higher `calls` and `cost_usd` on the research row, which the run budget gate reads. A run that used to pass that gate can now stop at it. Replay of existing histories is unaffected (the change is activity-side; replay takes activity results from history). Recommended **A: a written note only** — in the benchmark-facing docs and the slice notes, with the landing commit (FR-009, SC-007). *B: mark the rows themselves* (a field or tag on research rows recorded after the change) makes the break machine-readable but changes the record schema for a case seen once. *C: say nothing beyond the commit message* — rejected by the brief.
- **Q2 — What does `calls` mean?** Recommended **A: keep it** — one per priced activity result, so a capped sub-question adds 1 (V9, FR-009). *B: count model requests* would make `calls` comparable with other roles' request counts but changes every research row, capped or not, and breaks FR-010.
- **Q3 — How is a budget-caused retry exhaustion told from any other `UnexpectedModelBehavior`?** E3 rules out the exception type (it does not survive the sandbox). Recommended **A: a record owned by the sub-question run.** The tool notes each refused charge in an object the handler owns; the handler degrades when the run ends in `UnexpectedModelBehavior` and that record is non-empty. Measured to see every refusal, including under a three-way gather, and none for an unrelated tool failure. It matches no library text. Consequence to accept knowingly: any `UnexpectedModelBehavior` after a refusal degrades, including an output the model could not get valid (EC3) — the gap then names both the refused bound and the terminal error, so nothing is hidden, but that attempt is not retried. *B: match the message text* ("budget exhausted" in the cause chain) needs no new plumbing but sees only the last failed call and ties the handler to our own wording and the library's chain shape. *C: A, narrowed to tool-retry exhaustion only* keeps output-retry failures on the retry path, at the price of matching the library's message to tell the two apart. *Not offered: returning the refusal to the model as data instead of raising* — it removes the problem at the source but changes what the model is told at a cap, which is the deferred H2 question (FR-012).
- **Q4 — Does the non-retryable list change?** Recommended **A: no.** Under FR-003 the handler returns a finding, so the error never reaches the retry policy; the list at `R/step.py:64` and the test that pins it stay as they are. *B: add `UnexpectedModelBehavior` to the list* would stop the six retries without a handler change, but for every cause, and it turns each into a failed finding with zero usage — it hides unrelated model failures behind one attempt and fixes neither H1 nor the record.

Stated to the gate, not a question: **the skeptic's kill of M-1 stands on the record** (research is off by default; no fan-out run has shown a cap hit). The user ruled go on 2026-10-03; this spec does not reopen it.
