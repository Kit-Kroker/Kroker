# Research agent — grounded briefs (FR-107, **new scope**)

**Date:** 2026-07-17
**Roadmap:** §1 (new stage), §2 FR-107 *(proposed)*, FR-103, FR-701, FR-703, §3 NFR-5, §9.1, §9.4 E-18
**Requirements:** **FR-107 does not exist yet** — this spec proposes it (see *PRD amendment*). Gated on that change.
**Depends on:** `2026-07-17-agents-as-folders-design.md` (E-1/E-2), which in turn builds on the
shipped `2026-07-16-registry-drives-every-role-design.md` (`022d524`…`c33c42e`). Ships third.
**Design input:** [Schema-Guided Reasoning](https://abdullin.com/schema-guided-reasoning/); [`pydantic-ai-harness`](https://pydantic.dev/docs/ai/harness/); [`vercel/eve`](https://github.com/vercel/eve)

## Problem

Every proposer in the pipeline reasons from model priors. The architect is told to "prefer boring
technology" and "ground every decision in the provided codebase map", but nothing supplies evidence
about the world outside the repo — which library actually handles a requirement, what its known
failure modes are, what prior art exists. That grounding is currently whatever the model happened to
memorize.

Adding it is not free, and the danger is structural rather than incidental: a research stage sits
**upstream of everything**, so a false claim propagates into `clarify`, `architect`, the planner's
`ValidationContract`, and finally into a QA pass that validates a diff against contracts derived from
a fiction. Every gate goes green. An ungrounded research agent is worse than none, because it
launders a false claim into ground truth wearing a calibrated confidence score.

## Findings

Discovered while tracing this design against the codebase, in the order found.

1. **This is new scope, and nothing anchors it.** §1's 14-stage DAG is intake, constitution, context,
   requirements, clarify, architecture, planning, code, review, analyze, qa, quality_gate, deploy,
   retro. A research stage before `clarify` is a **fifteenth stage**. The nearest neighbour is stage 2
   *context (Cartographer)*, but that is brownfield codebase mapping under FR-102 — claiming web
   research anchors there is precisely the retrofit §9's scope discipline exists to prevent. Per that
   rule this is **(new scope)** and needs a PRD change before it is real.

2. **Research is the first outbound network egress in the pipeline.** §2 records FR-703 as "env
   allowlist ✅ only; no `pre_tool` hook, no OS-user/container tier, **no egress policy**." Every
   existing role either runs a subprocess with a curated env (`harness/adapters.py:ENV_ALLOWLIST`) or
   talks only to the model provider. This spec does **not** satisfy E-18; it is what makes E-18 stop
   being theoretical. Stated plainly: the egress arrives before the egress policy.

3. **Naïvely wiring the brief into `clarify` destroys memoization for the whole pipeline.**
   `content_key` (`memoization/cache.py:17`) takes `input_json`. Research cannot be memoized (finding
   4), so every run yields a *fresh* brief; two runs that discover identical facts still differ in
   prose, ordering and `confidence`. Clarify's key therefore moves every run — and so do architect's
   and planner's. FR-103 keeps working exactly as specified while never hitting again. Nothing fails;
   you silently pay full price forever. This is the same shape as the registry spec's finding 2
   (`model_id` missing from the key), one layer up.

4. **The research stage must be excluded from memoization, and that follows from the grounding rule,
   not from taste.** A served memo means the pages were *not* fetched this run, so its
   `grounded_findings` would carry a label they have not earned. Consequence worth recording so nobody
   later "fixes" the inconsistency: `PROMPT_SHAS["research"]` feeds benchmark records only. E-3's
   payoff is not merely already-banked here (registry spec, finding 1) — it is inapplicable.

5. **Recall-demotion needs no mechanism.** A finding recalled from the corpus was never fetched this
   run, so its page file does not exist, so placing it in `grounded_findings` fails the verifier's
   *source-never-fetched* check. The demotion rule enforces itself through the check that already
   exists.

6. **Research is the first role that gives agents-as-folders a real argument.** The registry spec's
   finding 1 killed E-1/E-2 on memoization grounds, correctly: for a role that is a prompt and a
   model, a folder holds one file and is filing. Research holds instructions, four tools, a provider
   choice, a fake corpus and a budget. Finding 1 does not refute that, because the case did not exist
   when it was written. This finding is why `2026-07-17-agents-as-folders-design.md` exists as its own
   increment and ships before this one — letting research land as a directory beside eleven YAML
   entries would reopen the registry spec's finding 4 in the codebase whose last five commits existed
   to close it.

7. **`ReviewReport` and `MergeVerdict` have an SGR ordering defect. Out of scope; recorded here
   because this spec is where it was found.** `ReviewReport` is `approve` → `findings` → `confidence`:
   the reviewer commits to a verdict **before writing a single finding**, while `REVIEWER_PROMPT`
   instructs "Set 'approve' to false if ANY finding is 'critical' or 'high'" — a rule the field order
   makes impossible to follow. `MergeVerdict` is worse: `approve` → `confidence` → `rationale` →
   `concerns`, rating its own confidence two fields before listing what concerns it. By contrast
   `AnalysisReport` and `ArchitectureSpec` are already evidence-first. This is a one-line-per-contract
   fix that deserves its own change and its own benchmark run — folding it in would make a green suite
   prove neither.

8. **Two mechanisms are assumed, not verified.** That `@agent.output_validator` raising `ModelRetry`
   survives `TemporalAgent` temporalization, and that the validator executes **activity-side**.
   `verify.py` reads files; if output validation runs in workflow context that is file I/O inside the
   Temporal sandbox — exactly what `test_factory_purity.py` exists to prevent. First task is a spike.

## Scope

**In:**

- A `research` stage before `clarify`, human-gated, emitting a `ResearchBrief`.
- An SGR full-cascade `ResearchBrief` contract; evidence-before-conclusion field ordering.
- `src/sdlc/research/`: `SearchProvider` protocol, `TavilyProvider`, `FakeProvider`, `verify.py`.
- `agents/research/`: `agent.yaml`, `instructions.md`, `tools/` (four thin tool files).
- Code Mode (`pydantic-ai-harness[codemode]`) wrapping the research tools.
- Quote verification against bytes fetched this run, stored under `runs/<run_id>/research/pages/`.
- The corpus: `MemoryKind.research_finding` retained to `project_bank`, verified findings only.
- Stage-scoped bounds in `PipelineConfig.research`; `research_enabled: bool = False`.
- `brief_digest` as the brief's contribution to downstream `content_key` (finding 3).
- The PRD / SDLC-spec amendment proposing FR-107 and taking the DAG 14→15.

**Out:**

- The `ReviewReport` / `MergeVerdict` ordering fix (finding 7) — separate change.
- Egress policy (E-18 / FR-703). This spec is its first consumer, not its implementation.
- Run-level budget generalisation (E-19 / FR-701). Bounds here are stage-scoped.
- Codebase research / `CodebaseMap` / brownfield delta (FR-102, stage 2) — a different stage.
- A judge rubric for brief quality. The quote check grades facts; a judge would grade vibes.
- Retaining `gaps` or `contradictions` to the corpus. Findings only. Noted as follow-up.
- `Cycle`-pattern iterative research. `Cascade` for the stage, `Routing` for the toolset.

## Design

### 1. Registry entry

Per the amended registry spec, the directory **is** the registry:

```
agents/research/
  agent.yaml         # {kind: research, model: anthropic:glm-5.2, provider: tavily}
  instructions.md    # the SGR cascade prompt
  tools/
    web_search.py
    fetch_page.py
    read_repo.py
    recall_leads.py
```

`RoleConfig.kind` gains `'research'` (`Literal['proposer', 'harness', 'research']`) and `RoleConfig`
gains `provider: Literal['tavily', 'fake'] | None`.

**`research` is the first entry in the agents-as-folders spec's `OPTIONAL_ROLES` seam**, not a
twelfth `REQUIRED_ROLES` name — the pipeline must boot without it, since `research_enabled` defaults `False`.
It is still a *known* directory, so the unknown-directory check keeps biting; this spec extends
`KNOWN_ROLES` rather than weakening the check. Like a proposer, a `kind: research` directory MUST
carry `instructions.md`; unlike one, it MAY carry `tools/`, and it is the only role that may.

**ADR-6 does not constrain research.** It reviews nothing, so model-family inequality is irrelevant.
`validate_registry` gains one rule instead: a `kind: research` role MUST name a provider, and
`provider: tavily` with no reachable `TAVILY_API_KEY` raises `RegistryError` at boot — fail closed,
consistent with the registry and schedule loaders. `provider: fake` is the explicit opt-out and is what
CI uses.

### 2. Assets are what you edit to change behaviour; code is what makes them work

`src/sdlc/research/` (`protocol.py`, `tavily.py`, `fake.py`, `verify.py`) stays code and mirrors
`src/sdlc/memory/`'s protocol + real-client + fake shape. A Tavily HTTP client is not an authoring
surface — nobody edits it to change agent behaviour, and burying it in an agent folder would make
`agents/` half-registry, half-library. `tools/*.py` stay thin: bind a provider call to a typed
signature, enforce the budget, return.

**Tool loading fails closed at boot, never at import.** The registry spec's finding 3 is that
`roles.py` calls `load_registry()` at *import* time, so a bad registry dies with a raw `KeyError`
before `validate_registry()` runs; dynamic imports make that easier to reintroduce. The directory
loader validates each `tools/*.py` — module imports, function name matches filename, signature fully
annotated — and raises `RegistryError`. Nothing imports a tool module as a side effect of importing
`roles`.

### 3. Bounds

`PipelineConfig.research` carries `max_searches`, `max_fetches`, `max_cost_usd` — per-run,
stage-scoped, enforced **inside the tool functions**, not in the prompt. A prompt-level bound is a
suggestion; these are the same philosophy as the deterministic quality gate versus the advisory
`merge_verdict_agent`. Exceeding one raises an ordinary error the sandbox handles, and the shortfall
lands in the brief's `gaps`.

`research_enabled: bool = False` mirrors `review_enabled` / `memoization_enabled`: the stage rolls out
per project, and the default pipeline is unchanged until a key exists.

### 4. The `ResearchBrief` cascade

Field order is reasoning order. SGR assumes true constrained decoding; structured output here is
tool-call shaped, where property order is followed by convention rather than enforced by a grammar —
so expect a real but softer effect than the article's numbers. That is an argument for testing the
ordering (§Testing), not for skipping it.

```python
class ResearchBrief(BaseModel):
    sub_questions:      list[SubQuestion]      # decompose
    sources_consulted:  list[ConsultedSource]  # gather
    grounded_findings:  list[GroundedFinding]  # what the bytes say
    inferred_findings:  list[InferredFinding]  # what I concluded (flagged)
    contradictions:     list[Contradiction]    # where sources disagree
    gaps:               list[Gap]              # what I could not answer
    summary:            str
    brief_ref:          ArtifactRef | None
    confidence:         float                  # last, as in AnalysisReport
```

```python
class GroundedFinding(BaseModel):
    source_url: str
    quote: str                  # verbatim span from bytes fetched THIS run
    claim: str                  # what the quote supports
    sub_question_ids: list[str]
```

**`quote` before `claim` is the design in one field ordering.** Claim-first means the model states a
conclusion then produces a quote to justify it — the motion that manufactures citations. Quote-first
forces commitment to a span actually in context, then a statement of what it supports. The verifier
catches invented quotes either way; the ordering makes them less likely to be written.

The same rule recurses: `ConsultedSource` is `url → title → assessment → relevance` (judgment before
label); `InferredFinding` is `reasoning → claim → based_on → fetched_at` (`fetched_at` set when the
lead came from the corpus); `Contradiction` is `topic → positions → assessment → unresolved`; `Gap` is
`sub_question_id → what_is_missing → why_it_matters`.

### 5. Grounding, verification, and the invariant

**The rule: `grounded` means verified against bytes fetched in this run.** One rule, one meaning
everywhere, no TTL to tune and no clock to trust.

Fetched pages are written to **`runs/<run_id>/research/pages/<sha256(url)>.txt`** rather than held on
`deps`. `TemporalAgent` moves tool calls across activity boundaries and a live provider handle plus a
page cache is not trusted to survive that trip; the filesystem is durable across boundaries, survives a
retry, is inspectable when a brief looks wrong, and matches §9's filesystem-first direction. `runs/`
already exists.

`verify.py` is pure: for each `grounded_finding`, read the page file and assert `quote` is a substring.
**Whitespace runs collapse to a single space before comparison; case is preserved.** HTML extraction
mangles whitespace and nothing else. Every further loosening is a hole in the check — no normalisation
may be added without a test proving the specific false-failure it fixes.

Two violation classes: *quote-not-found* and *source-never-fetched*.

Violations raise `ModelRetry` carrying the list, so the model corrects the quote or moves the claim to
`inferred_findings` where it honestly belongs. **After retries are exhausted the stage fails closed.**
A model that cannot quote its own fetched pages twice is malfunctioning, and auto-demoting would leave
a `confidence` computed under a premise the brief no longer holds.

### 6. The corpus, and why demotion is free

Flow: `recall_leads` (watermark-pinned, `filters={"stage": "research"}`) → Code Mode fans out
search/fetch inside one `run_code` activity, writing pages → output validator verifies → human gate →
retain each **verified** `grounded_finding` as `MemoryKind.research_finding` to `project_bank` via
`memory/scrub.py`.

Nothing unverified enters the corpus, so poisoning cannot compound. And per finding 5, a recalled lead
placed in `grounded_findings` fails *source-never-fetched* automatically — the corpus is a **lead
generator**: it tells the agent where to look, never what is true. To promote a lead the agent
re-fetches, at which point it is grounded on today's bytes and the invariant holds by construction. The
existing nightly `reflect` can dedupe the bank without ever being on the critical path.

`MemoryKind` gains `research_finding`.

### 7. `brief_digest` — the FR-103 fix

The brief contributes a **canonical digest** to downstream `content_key`, never its bytes:

```
brief_digest = sha256(canonical_json(sorted(
    (f.source_url, f.claim) for f in brief.grounded_findings)))
```

Prose, ordering and `confidence` drop out; facts remain. Two runs that find the same things memoize;
a run that finds something new correctly invalidates `clarify`, `architect` and `planner` — which is
exactly what research *should* do. Without this, finding 3 bites.

### 8. Two entry points, one core

1. **Stage** — `research` before `clarify`, gated through the existing `_gate` (hard/soft per
   `GateConfig`). Adds `"research"` to `PROMPT_SHAS` and `STAGE_MODELS`. **Not** routed through
   `_cached_stage` (finding 4).
2. **Toolset** — `architect_agent` gains a `research(question) -> ResearchBrief` tool sharing the same
   per-run budget counter; SGR's `Routing` pattern picks local vs. web. **This is the last task in the
   plan**, so the stage ships and is benchmarked before an architect can call research mid-run.

## Error handling

| Condition | Behaviour |
|---|---|
| `kind: research` registered, no reachable provider | `RegistryError` at boot — fail closed |
| `research_enabled=False` | Stage skipped; role not required; pipeline unchanged |
| Provider 5xx / timeout | Tool raises; sandbox sees an ordinary error; agent proceeds with fewer sources, records a `gap` |
| Budget exceeded | Tool raises; agent concludes with what it has; shortfall lands in `gaps` |
| Quote violations | `ModelRetry` with the list → after retries, stage fails closed |
| `run_code` activity timeout | Temporal retries the whole script |

Code Mode collapses N retry boundaries into one, so a failure at source 18 re-runs the script. Pages
are content-addressed by `sha256(url)`, so a retry re-fetches nothing it already has: the cache that
exists for verification is also what makes the coarse retry cheap. Degradation is bounded and
**visible** — a run that hits its budget produces a brief with honest `gaps`, not a silently thin one.

## Testing

Everything runs offline against `FakeProvider` over a canned corpus in `tests/fakes/research_corpus/`.
No test may require `TAVILY_API_KEY`.

Ordinary coverage: `verify.py` substring matching and whitespace normalisation; both violation classes;
budget caps raising; loader fail-closed on a missing provider, an unannotated tool signature, and a
filename/function mismatch; `research_enabled=False` skipping cleanly.

Three tests carry the design:

1. **A recalled lead placed in `grounded_findings` fails verification.** Proves demotion needs no
   mechanism (finding 5).
2. **Same facts → same `brief_digest` → clarify's memo hits; different facts → different digest →
   misses.** The FR-103 regression test (finding 3). This is the one that catches a later
   "simplification" of the digest back to raw brief bytes silently zeroing the pipeline's hit rate.
3. **`ResearchBrief` field order is asserted** via `model_fields`. `ReviewReport` drifted into
   verdict-before-findings with nothing to catch it (finding 7); SGR ordering is load-bearing here, so
   it gets a guard.

Plus e2e through `tests/fakes/` (`TestModel` stubs + fake activities) driving research→clarify, and
`test_factory_purity.py` staying green.

**Task 1 is the spike** (finding 8): prove `@agent.output_validator` + `ModelRetry` survives
`TemporalAgent`, and that the validator runs activity-side. If it runs workflow-side, verification moves
to a post-run activity and the fallback is failing the stage rather than retrying it. Either outcome is
workable; discovering it in task 9 is not.

## PRD amendment (required — this spec is gated on it)

Per §9's scope discipline, the following must land before the spec is real:

**`PRD.md` §6, Pipeline (FR-100)** — add:

> **FR-107 — Grounded research.** The pipeline MAY run a research stage before clarification that
> produces a `ResearchBrief` grounding downstream stages in fetched evidence. Every claim presented as
> grounded MUST carry a source URL and a verbatim quote verified against bytes fetched during that run;
> claims that cannot be so verified MUST be presented as inferred, or not at all. Research findings
> retained to memory are leads, not grounded claims: recall MUST NOT restore grounded status without
> re-verification. The stage MUST be bounded by explicit per-run limits and is off by default.

**`SDLC-spec-v2.md` §1** — DAG goes 14→15 stages; `research` is inserted before `clarify` as the new
stage 4, renumbering 4–13 to 5–14. Rationale recorded: the existing stage 2 *context (Cartographer)*
covers brownfield codebase mapping (FR-102) and is not a research stage.

**`ARCHITECTURE.md`** — no ADR change. Research introduces no new architectural decision: it is a
proposer with tools, under existing ADR-2, and its clean-context discipline is ADR-12's.

## Roadmap amendments

- **§1** — add stage `research` to the DAG, unchecked; the count becomes "8 of 15 stages live".
- **§2 FR-100** — add **FR-107**, unchecked, marked **(new scope)** pending the PRD change.
- **§2 FR-103** — note that `brief_digest` is what keeps memoization alive once a non-memoized stage
  feeds memoized ones.
- **§2 FR-701** — note the stage-scoped `max_searches`/`max_fetches`/`max_cost_usd` as the first
  run-level counters in the codebase; E-19 remains the general version.
- **§2 FR-703 / §3 NFR-5 / §9.4 E-18** — record that research is the pipeline's first outbound egress,
  and that it arrives before the egress policy. **This raises E-18's ranking**: §8 item 4 currently
  ranks harness containment fourth on the strength of `pre_tool`; an unpoliced egress is a second,
  independent argument.
- **§9.1** — record that research is the first role a folder *describes* rather than decorates, which
  is the argument that reopened E-1/E-2 (finding 6). The memoization argument finding 1 killed stays
  dead.
- **§7 / new** — record finding 7 (`ReviewReport` / `MergeVerdict` SGR ordering) as its own item.
