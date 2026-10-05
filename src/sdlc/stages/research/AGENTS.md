# AGENTS.md — research

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned. The research stage does not call other stages.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- The step interacts with the human research gate through `ctx.gate("research", ...)` and does not bypass it.
- Research executes fan-out activities (`plan_research`, parallel `research_subquestion`, `synthesize_brief`).
- Grounding verification is enforced via `verify_brief_activity`; ungrounded briefs degrade the stage and are not retained.
- The slice exports `step` and `ACTIVITIES = [plan_research, research_subquestion, synthesize_brief, verify_brief_activity]`.

## Temporal notes for this slice

- Activities: `plan_research`, `research_subquestion`, `synthesize_brief`, `verify_brief_activity`.
- Rule 3 passthrough set: this slice passes through `core/models.py`, `workflows/models.py`, and upstream artifact models.
- Single retry layer (004): the planner and synthesis agents constructed in
  `stage.py` are built through `sdlc.agents.model_ids.single_retry_layer()`
  (a fresh `ResolveModelId` per construction), so every activity-side model
  request runs with the provider SDK's retries off — the activity's own
  attempt budget is the only retry layer. The registry `research_agent`
  (sub-question fan-out, architect tool) gets the same capability via
  `build_agents`.
- Model forwarding (004): the sub-question fan-out passes `model=inp.model`
  when it differs from the registry `research` model (D7a; `inp.model` is
  already an activity input, so the wire is unchanged). The architect's
  research tool receives the run's forwarded `research` override on
  `ResearchDeps.research_model` (populated by the architecture slice only
  under an override; omitted from serialization while None) and passes it
  as `model=` — no-override deps and calls are byte-identical to before.
  The tool also bounds its inner run with `ResearchDeps.max_requests` (the
  architecture slice passes `cfg.research.max_requests`; omitted from
  serialization at the default) and returns the inner run's usage beside
  the brief as `ToolReturn` metadata, which the model never sees.

## State

- `StageContext` capabilities provide access to `stage`, `gate`, `record`, and `retain`.
- No state is retained on workflow instances by this slice.

## Gotchas

Traps verified in code on the 006 branch. Each is a behaviour an editor of
this slice can trip over; none is a bug report — where behaviour looks like
a defect, it is listed for the orchestrator, not fixed here (006-B4).

### Fail-and-continue (E-29)

- One `try` in `step.py` wraps BOTH the fan-out and `synthesize_brief`: a
  synthesis failure discards every successful sub-question finding and
  degrades the whole stage, even when all investigations succeeded.
- That degradation poisons the next refine round: `id_offset=len([])` is 0,
  so sub-question ids restart at `sq-0` while `budget_store.py`'s persisted
  per-run counters still hold the already-spent allowance.
- A degraded brief has no grounded findings, so it verifies clean and
  digests non-empty — after human approval the stage records PASS with a
  judged quality score (`step.py`).
- Budget/usage exhaustion in `stage.py`'s handler still returns a finding
  with `failed` False and still drops the partial work for a gap-only
  brief (the all-failed check and `merge.py`'s failed-gap branch never
  fire), but the usage up to the cap is now returned and priced instead
  of zeroed. A run that ends in retry exhaustion after a refused charge
  degrades the same way, in one attempt (`UnexpectedModelBehavior` with a
  refusal noted on the run's own deps record); any other error is
  retried as before, and an attempt that raises still loses its spend.
- REVISE past `max_refine_rounds`, or any exception during refine, breaks
  out with the last good brief — which is then retained, judged and
  recorded PASS (`step.py`).
- `verify_brief_activity` is the one non-fail-soft call: outside every
  `try`, `maximum_attempts=1` (`step.py`) — a verifier raise fails the
  workflow, not the stage.
- A human rejection returns immediately (`step.py`): no benchmark row is
  recorded for the rounds of spend already incurred.

### Verifier rules

- Only `grounded_findings` are verified and hashed (`verify.py`):
  inferred findings and gaps are never checked against pages.
- Pages are written only by `get_page` and keyed by sha256 of the EXACT
  URL string (`exa_wrapper.py`, `verify.py`): a quote sourced from a
  search snippet, or whose URL is any variant of the fetched one
  (trailing slash, scheme), fails `source_unavailable`; a failed page
  write is only logged, the fetch still succeeds.
- Pages and budgets live under `runs/<run_id>/research`, rooted at
  `$SDLC_RUNS_ROOT` (default: CWD-relative `runs/`) — a restart with the
  same workflow id inherits both, and fetch and verify must share
  environment and CWD or every quote fails (`verify.py`, `budget_store.py`).
- `brief_digest` hashes `(source_url, claim)` pairs while `merge.py`
  dedupes exact `(url, quote, claim)` triples — two quote-variants of one
  fact both survive the merge and double-count in the digest; and any
  brief without grounded findings (every degraded one) digests to the
  same constant, with `""` the only ungrounded sentinel (`verify.py`,
  `merge.py`, `step.py`).
- Retention does not verify: `retain.py` takes the violations list
  `verify_brief_activity` returned for that brief and reads no file; the
  step retains the brief that was verified (`step.py`), so a replay does
  not depend on the page files.

### Budget enforcement

- Caps price TOOL use from constants (`deps.py`'s per-search/per-fetch
  estimates): LLM tokens are priced separately and never enforced against
  the budget.
- Both counters are checked before either is written (`charge_scoped`), so
  a charge refused by the scope allowance or the run ceiling writes
  nothing to either; the run counter still enforces cost only (count caps
  pinned unbounded). The two publishes are separate atomic writes, so a
  crash between them can leave the scope counter one charge ahead — never
  the shared ceiling short of real work. Being disk-persisted per
  run+scope, activity retries still inherit the already-spent allowance —
  attempt N is not a fresh budget (`budget_store.py`).
- The `scope == "run"` collapsed branch in `charge_scoped`
  (`budget_store.py`) is correct and tested but dead in production: the
  architect charges `scope="architect"` (`architecture/step.py`), the
  stage fan-out charges `sq-<id>` scopes — only tests and the default
  scope reach it. `toolset.py` catches `BudgetExceeded` and
  `UsageLimitExceeded` and degrades both to a gap-only brief, reporting
  the spend made so far, so a lock `TimeoutError` escapes the catch and
  is retried — bounded
  (6 attempts on the sub-question activity, 3 on agent activities), not
  uncapped; under CodeMode a tool-side timeout surfaces to the model as
  a retry prompt first.
- A budget lock older than 10 s is stolen; acquire timeout raises
  `TimeoutError`, which the exhaustion handler in `stage.py` does not
  catch (`budget_store.py`).
- A truncated or garbage `budget-<scope>.json` wedges that scope until
  someone clears it by hand. This is deliberate: `budget_store.py` never
  auto-resets an unreadable counter, because that would hand the spent
  budget back. The write itself is atomic (temp file + `os.replace`, like
  `write_page`), so a crash mid-write leaves the previous counter intact;
  only external damage to the file produces the wedge.

## Tests

    pytest tests/research/ -q
