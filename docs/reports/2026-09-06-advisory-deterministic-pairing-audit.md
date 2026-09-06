# Advisory LLM passes and the deterministic mechanisms behind them

| | |
|---|---|
| Date | 2026-09-06 |
| Commit | `6daefae` |
| Register row | C4, `docs/reports/external-ideas-2026-09.md` |
| Method | Census by grep over `src/sdlc` (reproduced in full below), then a two-prong scope criterion applied to every hit. |

## What this audits, and what "behind it" means

The C4 register row states a rule: every advisory LLM check ships with a
deterministic enforcement path behind it — the playbook's "skill makes
violations rare, hook makes them near-impossible". This document is the audit
that rule asked for.

"Behind it" is two questions, not one, and every row below is asked both:

- *If it blocks, what makes the block stick?* An LLM's rejection must be
  reified into deterministic machinery that cannot be configured or prompted
  away, or the block is a suggestion.
- *If it wrongly passes, what catches it?* A sycophantic or lazy "approve"
  must meet a deterministic backstop somewhere downstream, or the pass is the
  last line of defense wearing a reviewer's badge.

The next auditor should re-run those two questions against the table rather
than trusting it. The census commands that produced the rows are printed
verbatim in [Census method](#census-method).

## Scope criterion

Scope is drawn by criterion, not by stage list. A pass is in scope iff either
prong holds:

- **Prong A — judgment.** Its output is, or contains, a verdict about work it
  did not itself produce: approve, findings, severity, or a self-reported
  confidence that an admission decision consumes.
- **Prong B — evidence.** Its output is retained or derived evidence about
  work that a gate, a fix loop, or a later admission decision reads.

Generators — architect, planner, clarify, research, the code task prompt —
are **out**. Their artifact *is* the work; their defects are the jurisdiction
of the judgment passes that consume them, and those passes are rows below.
Asking "what deterministic check stands behind the Architect" is answered by
pointing at the rows.

The non-obvious precision: **a generator's self-reported confidence is in
scope under Prong A even though the generator is not**, because it
short-circuits a human gate. The unit of the audit is the judgment, not the
stage.

The verification surface, enumerated: task admission in the code stage
(`code/step.py:797-836`, plus the budget-exhausted human task gate at
`:858-906`), the merge gate, the evidence extractors feeding both, and the
confidence short-circuits on gates. Scoping to merge alone would miss where
most of the binding actually happens, one stage earlier.

## Verdicts

| Verdict | Meaning |
|---|---|
| **PAIRED** | A deterministic twin covers the pass's jurisdiction and can block without the LLM. |
| **ENFORCED** | The LLM's block is reified into deterministic machinery, but a wrong-yes has no deterministic backstop inside the pass's own jurisdiction. |
| **FILTERED** | A deterministic mechanism sanitizes what the pass sees or what it can credibly claim, and nothing it says blocks. |
| **UNPAIRED** | The output influences admission with nothing deterministic behind it. |

## The census

| # | Pass (file:line) | Failure mode if wrong | Enforcement | Backstop | Verdict |
|---|---|---|---|---|---|
| 1 | MergeVerdict — `merge/models.py:21`, consulted `merge/step.py:399` | approves a build the human should have seen (SOFT only, post-clean-gate) | `evaluate_quality_gate` (`gate.py:133`) runs first and cannot be bypassed | the twin *is* the backstop; residual: its confidence skips the human — see row 8 | PAIRED |
| 2 | Primary reviewer — `code/step.py:797`, `merge/step.py:287-292` | wrong-approve admits unreviewed code at task admission and merge | the block is a conjunct of the done path (`code/step.py:797`) and the `review_severity` ADVISORY check (`merge/step.py:287-292`) | absolute merge checks cover code-level dimensions only; design-quality jurisdiction has the human alone | ENFORCED |
| 3 | Adversary lens — invoked `code/step.py:802`, consulted `:812` | a blocking rejection is missed; a wrong rejection stalls the loop | rejection skips the done path (`:812`), feeds the fix loop (`:838`), reaches the human gate on exhaustion (`:867`) | runs only after `task_passed and review_ok` (`:800`), so tighten-only — but its fail-open legs have nothing | ENFORCED (fail-open leg UNPAIRED) |
| 4 | deep_review — `code/step.py:813`, `:894` | fabricates findings or misses signal; either way it never blocks | none needed for blocking — never in the success condition (post-decision at both sites) | output-side: `handoff.py:99-124`, `:127-149` drop ungrounded flags/deviations (E-43/E-83); input-side: the E-38 scrub (`memory/scrub.py:18`, applied `harness/session.py:59`) | FILTERED |
| 5 | Handoff extractor — `code/step.py:417` | hallucinated claims enter the durable handoff record | never gates; recorded for the next task's context | `handoff.py:60-84` `cross_check_claims` drops claims outside the diff or ungrounded in the transcript; fail-open degrades to a mechanical files-only `HandoffSummary` (`code/step.py:459-465`) | FILTERED |
| 6 | Analyst — `analyze/step.py:121` | "everything traces" hides untested acceptance criteria | deterministic `untraced_criteria` reduction (`analyze/step.py:136`) feeds the merge `traceability` ADVISORY check (`merge/step.py:293-302`) | none in its own jurisdiction for a wrong-yes; merge-time human waiver is the catch | ENFORCED |
| 7 | QA LLM pass — `qa/step.py:175` | "no issues" on a defective diff passes the task | `qa.issues` is a conjunct of `task_passed` (`code/step.py:750`) | deterministic twin `run_test_suite` (`qa/step.py:137-141`) holds the wrong-yes for test-detectable issues; the LLM conjunct is tighten-only | PAIRED |
| 8 | Confidence auto-approve — `role_host.py:55-75`, consumed `:224` | a mis-calibrated confidence removes the human gate | none — SOFT + `confidence >= threshold` synthesizes the APPROVE (`role_host.py:68-75`) | guards only: `None` confidence never auto-approves (`role_host.py:64-65`); exhausted rounds force a final gate (`:236-239`) | UNPAIRED |

### Row 1 — MergeVerdict, PAIRED

Defined at `merge/models.py:21` with the docstring that states its ceiling:
"It can approve an already-clean build; it can never bypass the gate." The
consult site (`merge/step.py:391-399`) sits in the `else` branch after the
deterministic gate passed clean (`:316-318` evaluates; `:382` branches), and
only under `GatePolicy.SOFT`. The deterministic twin — `evaluate_quality_gate`
(`gate.py:133`) — covers the pass's entire jurisdiction and blocks without
any LLM.

The one-line cross-reference the verdict owes row 8: while MergeVerdict
cannot bypass the *gate*, its `confidence` feeds `_auto_decision_for` at
`merge/step.py:399` and can skip the *human*. Without that cross-ref this
row reads cleaner than reality.

### Row 2 — Primary reviewer, ENFORCED (with a fail-open leg)

The primary binds twice. At task admission, `code/step.py:797`
(`review_ok = review is None or review.approve`) gates the done path; the
pass itself runs at `review/step.py:127`. At
merge, the `review_severity` ADVISORY check (`merge/step.py:287-292`) encodes
`all(r.review is None or r.review.approve ...)` — waivable via an audited
`GateOverride` at the human merge gate. The block direction is fully
reified: a rejection forces the fix loop (`code/step.py:838`) and, on budget
exhaustion, the human task gate (`:867`).

The wrong-yes direction has no deterministic backstop inside its
jurisdiction: the absolute merge checks cover code-level dimensions only
(tests, lint, security); design-quality judgment has the human alone.

Its own fail-open leg must be annotated: `review/step.py:114-115` returns
`None` when `review_enabled` is false or no agent is configured, and
`code/step.py:797` reads `review is None` as approval. The failure is
*compound* — `code/step.py:801` runs the adversary only `if review is not
None`, so the primary's fail-open silently disarms the backstop lens too.

### Row 3 — Adversary lens, ENFORCED with an UNPAIRED fail-open leg

This corrects the brief this audit started from, which called the adversary
"signal only". It is not. The pass runs at `review/step.py:195` (via the
`code/step.py:802` wrapper); `code/step.py:812` reads
`if adversary is None or adversary.approve or not adversary.blocking_findings:`
and guards the done-return at `:826`; a blocking rejection skips the done
path, feeds the fix loop (`:838`), and on budget exhaustion reaches the human
task gate (`:867`). It runs only after `task_passed and review_ok` (`:800`),
so it can only tighten.

The honest gap is the fail-open leg: an exception, a disabled
`adversarial_review_enabled`, or a missing agent yields `None`, which is read
as agreement, with no tombstone (`review/step.py:179-183`, `:234-240`; the
code-stage wrapper repeats the pre-check at `code/step.py:335`). **That is
C3's hole one layer up — a check that did not run, read as a check that
passed — and the C3 fix does not reach it, because these lenses never travel
through `evaluate_quality_gate`.** Filed as register row C8.

### Row 4 — deep_review, FILTERED

Defined at `review/step.py:243`, its run_role site at `review/step.py:289`,
invoked at `code/step.py:813` (done path)
and `:894` (human-gate path) — both post-decision, never in the success
condition, as its docstring requires (`review/step.py:257-261`). Nothing it
says blocks, so the pairing question reduces to output hygiene, and there the
mechanisms are deterministic. Output-side: `handoff.py:99-124`
`verified_integrity_flags` and `:127-149` `verified_plan_deviations` (E-43 /
E-83) drop any flag or deviation whose evidence quote is not verbatim in the
transcript. Input-side: the E-38 scrub (`memory/scrub.py:18`, applied to
sessions at `harness/session.py:59`) sanitizes what it reads. A filter that
never gates — FILTERED.

### Row 5 — Handoff extractor, FILTERED

Invoked at `code/step.py:417`. Its output is deterministically cross-checked
by `handoff.py:60-84` `cross_check_claims`: claims naming files outside the
diff are dropped, quotes absent from the transcript are dropped. It never
gates. Its fail-open leg is the only one in the census that lands on a
deterministic artifact: on exception the stage returns the mechanical
files-only `HandoffSummary` fallback (`code/step.py:459-465`).

A second site exists at `workflows/feature.py:340` — a `_run_role("handoff",
...)` twin with the same prompt shape at `:345-349`. It is cited as found;
whether it is live or vestigial is a question about `FeatureWorkflow`'s
in-flight surgery that this audit records rather than resolves.

### Row 6 — Analyst, ENFORCED

The analyst (`analyze/step.py:121`) reads criteria, QA lines, and the diff,
and produces the analysis the merge gate grades. Behind it stands the
deterministic `untraced_criteria` reduction (`analyze/step.py:136`), which
computes the untraced set from the authoritative criteria rather than
trusting the analyst's framing, and feeds the merge `traceability` ADVISORY
check (`merge/step.py:293-302`) — waivable, so the human merge gate is the
wrong-yes catch. A wrong-yes ("everything traces") has no deterministic
backstop inside the analyst's own jurisdiction; that is what ENFORCED, not
PAIRED, means here.

### Row 7 — QA LLM pass, PAIRED

`qa/step.py:175`; its docstring disclaims gating (`qa/step.py:129-131`,
"Never calls a gate"). The disclaimer is not the whole truth:
`code/step.py:750` is
`task_passed = bool(qa_raw.tests_passed and not qa.issues and not drift.found)`
— `qa.issues` is the QA LLM's output, and an empty issue list is a conjunct
of the pass verdict. The LLM blocks.

The verdict still stands, on corrected grounds. The deterministic twin
`run_test_suite` (`qa/step.py:137-141`) holds the wrong-yes direction for
test-detectable issues, and the LLM's conjunct is tighten-only — it can fail
a passing build, never pass a failing one. Residual, named: a wrong-yes on a
*non-test-detectable* issue has no deterministic backstop in QA's own
jurisdiction and is caught only by the reviewer, adversary, and human rows.

### Row 8 — Confidence auto-approve, UNPAIRED

`role_host.py:55-75` `_auto_decision_for` (FR-301), consumed at `:224`
inside `_revisable_stage` (`:212-239`) for the architecture
(`architecture/step.py:188`) and plan (`plan/step.py:109`) gates, plus
MergeVerdict's copy at `merge/step.py:84-100`, consulted `:399`. SOFT policy
plus a self-reported confidence at or above threshold synthesizes an APPROVE
the gate short-circuits on — the human wait never happens.

Real guards exist and the row is fair to them: a `None` confidence never
auto-approves (`role_host.py:64-65` — missing data falls through to the
human), and exhausted rounds force a final gate where even SOFT waits
(`:236-239`). What is missing is any deterministic evidence that the
confidence is calibrated — nothing scores past confidences against realized
outcomes before honouring the next one. Filed as register row C7.

## Row 8 is the headline

The confidence short-circuit is the most interesting finding because it runs
in the direction the pairing principle does not anticipate. Every other row
asks what stands behind an LLM *adding* a judgment; row 8's LLM output
*removes* a human check. The failure mode is not "a bad verdict ships" but
"the verdict's self-assessed quality quietly ends the review that would have
caught it" — and via the memory channel below, a single mis-calibrated
confidence that skips a gate can shape every later run's proposers.

## The memory channel

Retained LLM text — GOTCHA (`review/step.py:227`, `:345`;
`code/step.py:910`; `analyze/step.py:166`), STAGE_SUMMARY
(`analyze/step.py:155-162`), GATE_FEEDBACK (`merge/step.py:329`, `:424`;
`workflows/feature.py:256`) — is recalled into later runs as a declared,
hashed, watermark-frozen stage input (`memory/activities.py:52-60`, FR-402;
the memoization key includes the recall watermark at `role_host.py:122`).
Past LLM judgments shape future *proposers*, which are then gated by the
gates already audited above.

The deterministic guard on this channel is **replayability, not judgment**:
the same watermark yields the same recall, so a run is reproducible, but
nothing deterministic vets whether a retained judgment was *right*. That is
why this is a section rather than a row — it is the mechanism by which an
UNPAIRED pass's wrongness compounds across runs, which is exactly the
blast-radius question a "signal only" justification would have to answer.

Also recorded here: **retro has no LLM pass of its own.** `retro/step.py:34`
onward is deterministic orchestration, fully trapped so the run outcome is
never modified. It triggers the `reflect` activity (`memory/activities.py:107`),
which is memory-domain consolidation and sits outside the admission surface.

## Out of scope

Every `run_role` line the census grep returned is either a row above or a
row here. Nothing is unaccounted for.

| Pass (file:line) | Why out |
|---|---|
| Architect — `architecture/step.py:138` | generator (Prong A/B fail: its artifact is the work). The best-backed generator: `check_brownfield_delta` (`context/delta.py` `DELTA_CHECK`, consumed `architecture/step.py:162-184`) deterministically grounds its delta, with retries and a terminal failure. The plan stage has nothing analogous — E4's plan-drift signal is computed and read by nothing, and is already its own register row. |
| Planner — `plan/step.py:88` | generator; no delta-check analogue (see above, E4) |
| Clarify router — `clarify/step.py:78` | generator (routes the clarification loop) |
| Clarify answer ×2 — `clarify/step.py:84`, `:146` | generator (produces the clarification artifact) |
| Clarify final — `clarify/step.py:161` | generator (returns the artifact) |
| Handoff twin — `workflows/feature.py:340` | duplicate of row 5's extractor at the workflow layer (same prompt shape, `:345-349`); cited as found, liveness not chased |
| The capability itself — `workflows/role_host.py:133`, `core/context.py:33` | the `run_role` mechanism and its `StageContext` protocol stub, not passes |

Ruled explicitly, so a reader need not wonder whether they were missed or
dodged:

- **`ctx.judge`** (`core/context.py:54`) — benchmark quality scoring; an LLM
  verdict retained as evidence, which Prong B arguably reaches via C5's
  calibration loop. It scores runs for the benchmark; it admits nothing and
  blocks nothing, so it is off this audit's admission surface.
- **The crew workflow's roles** (E-88, `CrewTaskWorkflow`) — a separate
  workflow with its own gate wiring, not on the single-run verification
  surface this audit enumerates.
- **Research** — a generator, and not a `run_role` site at all (it is passed
  as `research_agent` at `workflows/feature.py:537`), hence its absence from
  the grep is a property of the mechanism, not a census miss.
- **The code task prompt** — goes to the coding harness, not through
  `run_role`; its defects are the jurisdiction of the QA, reviewer, and
  adversary rows.
- **`reflect`** (`memory/activities.py:107`) — memory-domain consolidation
  triggered by retro; see the memory channel above.

**Intake and deploy have no `run_role` sites at all** — recorded so this
census dates itself: a stage added later, or a pass moved, changes the grep
output and with it this table.

## Census method

Run from the repo root, against commit `6daefae`; output transcribed verbatim
from the executed commands:

```
git rev-parse --short HEAD
rg -n "run_role\(" src/sdlc -g "*.py"
rg -n "run_adversary|run_deep_review" src/sdlc/stages -g "*.py"
rg -n "revisable" src/sdlc -g "*.py"
rg -n "GOTCHA|GATE_FEEDBACK|STAGE_SUMMARY" src/sdlc -g "*.py"
```

```
6daefae
src/sdlc\stages\code\step.py:417:            await ctx.run_role(
src/sdlc\stages\review\step.py:127:    role_res = await ctx.run_role(
src/sdlc\stages\review\step.py:195:        role_res = await ctx.run_role(
src/sdlc\stages\review\step.py:289:        role_res = await ctx.run_role(
src/sdlc\workflows\role_host.py:133:    async def _run_role(
src/sdlc\core\context.py:33:    def run_role(
src/sdlc\stages\architecture\step.py:138:                res = await ctx.run_role(
src/sdlc\stages\analyze\step.py:121:    res = await ctx.run_role(
src/sdlc\stages\clarify\step.py:78:    route = (await run_role(route_agent, route_prompt)).output
src/sdlc\stages\clarify\step.py:84:            await run_role(
src/sdlc\stages\clarify\step.py:146:            await ctx.run_role(
src/sdlc\stages\clarify\step.py:161:            return await ctx.run_role(
src/sdlc\workflows\feature.py:340:                await self._run_role(
src/sdlc\stages\plan\step.py:88:            res = await ctx.run_role(
src/sdlc\stages\merge\step.py:391:            role_output = await ctx.run_role(
src/sdlc\stages\qa\step.py:175:    role_res = await ctx.run_role(
```

```
src/sdlc/stages\code\__init__.py:19:    _run_adversary,
src/sdlc/stages\code\__init__.py:20:    _run_deep_review,
src/sdlc/stages\code\__init__.py:36:    "_run_adversary",
src/sdlc/stages\code\__init__.py:37:    "_run_deep_review",
src/sdlc/stages\code\step.py:325:async def _run_adversary(
src/sdlc/stages\code\step.py:338:    from ..review.step import run_adversary as review_run_adversary
src/sdlc/stages\code\step.py:340:    return await review_run_adversary(
src/sdlc/stages\code\step.py:353:async def _run_deep_review(
src/sdlc/stages\code\step.py:371:    from ..review.step import run_deep_review as review_run_deep_review
src/sdlc/stages\code\step.py:373:    return await review_run_deep_review(
src/sdlc/stages\code\step.py:802:                adversary = await _run_adversary(
src/sdlc/stages\code\step.py:813:                deep = await _run_deep_review(
src/sdlc/stages\code\step.py:894:            deep = await _run_deep_review(
src/sdlc/stages\review\__init__.py:7:from .step import run_adversary, run_deep_review, step
src/sdlc/stages\review\__init__.py:14:    "run_adversary",
src/sdlc/stages\review\__init__.py:15:    "run_deep_review",
src/sdlc/stages\review\step.py:159:async def run_adversary(
src/sdlc/stages\review\step.py:243:async def run_deep_review(
```

```
src/sdlc\core\context.py:46:    def revisable_stage(
src/sdlc\core\context.py:81:    revisable_stage: Callable[..., Awaitable[tuple[Any, Any]]]
src/sdlc\workflows\role_host.py:212:    async def _revisable_stage(
src/sdlc\workflows\feature.py:220:            revisable_stage=self._revisable_stage,
src/sdlc\stages\architecture\step.py:5:delta checks, obtains human gate approval via revisable_stage, judges and records outcome,
src/sdlc\stages\architecture\step.py:72:    Runs the architect agent with memoization and revisable review loops,
src/sdlc\stages\architecture\step.py:188:    arch, gate = await ctx.revisable_stage("architecture", cfg, _run_architect)
src/sdlc\stages\plan\step.py:4:memoization caching, obtains human gate approval via revisable_stage, judges and records outcome,
src/sdlc\stages\plan\step.py:58:    Runs the planner agent with memoization and revisable review loops,
src/sdlc\stages\plan\step.py:109:    plan_obj, gate = await ctx.revisable_stage("plan", cfg, _run_plan)
```

```
src/sdlc\memory\models.py:17:    STAGE_SUMMARY = "stage_summary"
src/sdlc\memory\models.py:18:    GOTCHA = "gotcha"
src/sdlc\memory\models.py:19:    GATE_FEEDBACK = "gate_feedback"
src/sdlc\workflows\feature.py:256:            MemoryKind.GATE_FEEDBACK,
src/sdlc\workflows\feature.py:563:            MemoryKind.STAGE_SUMMARY,
src/sdlc\stages\analyze\step.py:157:        MemoryKind.STAGE_SUMMARY,
src/sdlc\stages\analyze\step.py:166:            MemoryKind.GOTCHA,
src/sdlc\stages\code\step.py:910:            MemoryKind.GOTCHA,
src/sdlc\stages\architecture\step.py:213:        MemoryKind.STAGE_SUMMARY,
src/sdlc\stages\merge\step.py:329:            MemoryKind.GATE_FEEDBACK,
src/sdlc\stages\merge\step.py:424:        MemoryKind.GATE_FEEDBACK,
src/sdlc\stages\review\step.py:227:                MemoryKind.GOTCHA,
src/sdlc\stages\review\step.py:345:                MemoryKind.GOTCHA,
src/sdlc\stages\plan\step.py:134:        MemoryKind.STAGE_SUMMARY,
```

`rg` does not sort results on this platform, so the *order* of lines within
each block is not stable across runs — diff the hit sets, not the sequence.

## What remains open

Two gaps found by this audit are filed as register rows in
`docs/reports/external-ideas-2026-09.md`; recommendations live only there:

- **C7** — nothing stands behind self-reported confidence (row 8); candidate
  shape: score confidence against retained outcomes before honouring it.
- **C8** — a lens that did not run is indistinguishable from a lens that
  approved (row 3's fail-open legs, compounded by row 2's); candidate shape:
  an explicit absence tombstone the task's success condition must see.

## A note on timing

C3 landed between this census and publication (`6daefae`, on this branch),
and hardened exactly the quiet-green hole row 3's analogy names:
`evaluate_quality_gate` now synthesizes a failing `MISCONFIGURED` check for
every `MERGE_REQUIRED_CHECKS` name absent from its input, and re-asserts
`ABSOLUTE_FLOOR` on input. Row 1's mechanism is therefore stronger than it
was when the C4 register row was written. Rows 2 and 3's fail-open legs are
untouched by C3 — those lenses never travel through the gate evaluator —
which is precisely why C8 exists.
