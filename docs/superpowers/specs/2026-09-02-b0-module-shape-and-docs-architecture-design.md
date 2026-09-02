# B0 — module shape, code rules, and documentation architecture

**Date:** 2026-09-02
**Status:** approved design, ready for planning
**Scope:** B0 — the convention layer. What a correct module and a correct document look like in this repo, and the mechanics that keep them that way.
**Satisfies:** no FR moves. This is repo-hardening (`ROADMAP.md` §7, "Structural / repo-hardening items").
**Baseline:** `main` at `dc02fd4`; `temporalio` 1.30.0.
**Does not cover:** (A) the surgery itself — cutting `feature.py` / `activities.py` / `models.py` / `harness/adapters.py` into slices; (C) the UI and Claude Design pipeline — the Vue design system, component docs, the showcase route. Both get their own design docs. B0 defines the target those two aim at and produces the rules, templates, and enforcement they will be measured against.

## Problem

The repository has grown files no agent can work in. `src/sdlc/workflows/feature.py` is 3673 lines; `src/sdlc/activities.py` is 1430; `src/sdlc/models.py` is 1334 and holds 73 Pydantic models plus 11 `StrEnum`s drawn from every bounded context in the pipeline at once; `src/sdlc/harness/adapters.py` is 1092. Below the ceiling but already hard to work in: `src/sdlc/assessment/activities.py` at 926 and `src/sdlc/workflows/assessment.py` at 820. An agent asked to change one stage of the pipeline must hold several of these in context simultaneously, and its edits get less reliable exactly as the file gets larger.

Three things make this worse than "some files are big".

1. **There is no agreed target shape.** Five agents told to decompose `FeatureWorkflow` will produce five incompatible paradigms — class mixins, child workflows, pure state reducers — because nothing in the repo says which is correct here. Cutting before that is settled produces a split that has to be redone.

2. **The documentation an agent reads first is already wrong.** `ARCHITECTURE.md` names the orchestrator `FactoryWorkflow` in four places — lines 36 (the §2 component diagram), 59 (the §2 responsibility table), 73 (the §3 stage DAG) and 336 — while the code has said `FeatureWorkflow` since `src/sdlc/workflows/feature.py:825`. `ROADMAP.md` is 1647 lines across 18 sections and is the single worst file in the repo to put in a context window. `CLAUDE.md` at the root is zero bytes and untracked, so Claude Code starts every session with no repo-specific instruction at all and never learns that `AGENTS.md` exists.

3. **Nothing stops it recurring.** `pre-commit` runs `ruff`, `ruff-format` and `mypy` (scoped to `^src/`), none of which has an opinion about file length. Whatever we cut today grows back.

## Decision

**Cut along the seams of the process. A stage is the unit of agent work.**

Not technical layers (`workflows/`, `activities/`, `models/` as separate homes), and not domain entities. The test for a good seam is the common closure principle: things that change together live together. When a stage's behaviour changes, its workflow step, its activities, its models, its prompt assembly, its tests, and its documentation all change — so they belong in one directory.

DDD vocabulary is permitted as a *mapping*, never as a method:

- a stage ≈ a bounded context with its own model;
- `src/sdlc/core/models.py` is the **shared kernel**: the home for types no single stage owns — configuration and envelopes such as `PipelineConfig`, `GateDecision`, `RoleConfig` and `IdeaBrief`. A shared kernel must stay small and stable, and §1.4 states the ownership rule that keeps it so;
- `harness/`, `board/`, `channels/`, `memory/`, `observability/`, `artifacts/` are generic subdomains, which is exactly why they stay horizontal packages and are *not* forced into the stage shape.

The principle is recursive. A non-pipeline domain slices by the phases of its own process, not by the feature pipeline's stages: `assessment` slices into `scan` / `discover` / `risk` / `gates`, which is close to the shape it already has.

**Cross-stage calls are banned.** A stage never imports or invokes another stage's step. The orchestrator is the sole coordinator. This is what keeps a slice reviewable in isolation and is the property the whole scheme rests on. Importing a *type* another stage produces is not a call and is not banned — see §1.4.

### Target layout of a slice

```
src/sdlc/stages/clarify/
  __init__.py     # exports step, ACTIVITIES
  step.py         # the workflow-side orchestration of this stage
  activities.py   # the @activity.defn functions this stage owns
  models.py       # the artifacts this stage produces
  prompts.py      # dynamic context assembly for this stage's role(s)
  clarify.md      # WHAT: numbered clauses, CLARIFY-1.1 [FR-xxx]
  AGENTS.md       # HOW to change this slice
tests/clarify/    # mirrored; see §5
```

Prompts have two sources of truth and they do not overlap: `agents/<role>/instructions.md` is the role's persona and belongs to the product's runtime registry (loaded by `src/sdlc/agents/loader.py`; untouched by this work), while `stages/<stage>/prompts.py` assembles the dynamic context handed to that role for this stage.

## 1. The seam contract

This is the part that decides whether piecemeal migration works or rots. With two stages moved and thirteen still inside `feature.py`, an agent that cannot tell where a stage lives will hallucinate imports and duplicate activities in both locations. The stitch has to be specified exactly.

### 1.1 The step contract

A migrated stage exports one async function:

```python
async def step(ctx: StageContext, ...) -> Artifact: ...
```

`_pipeline` calls it where its inline block used to be. `StageContext` is an explicit Protocol defined once in `src/sdlc/core/`, carrying the orchestration services a stage may use. The point of the object is not that it is small — it is that the surface is **fixed, named, and reviewable**, so "a stage does not reach into the workflow class" becomes a checkable claim rather than an aspiration. Passing `self` would expose everything; passing a dozen loose callables would bloat every call site. The coupling already exists inside the workflow today; `StageContext` is what makes it visible.

**The service inventory.** Eleven services in five groups:

| Group | Services | Anchors |
|---|---|---|
| Reporting | `emit`, `stage` | `feature.py:1226`, `:1234` |
| Role execution and memoization | `run_role`, `cached_stage`, `revisable_stage` | `:1283`, `:1145`, `:1773` |
| Benchmark and memory | `record`, `judge`, `recall`, `retain` | `:1012`, `:1026`, `:1062`, `:1080` |
| Human decisions | `gate` | `gates.py:168` |
| Human questions | `ask_and_wait` | `feature.py:2845-2887` |

`gate` is not optional, and omitting it is the natural mistake — it reads like workflow-class business until you count the call sites. `self._gate(...)` is called at ten sites, seven of them inside `_pipeline` and `_dev_task` (including `:2026` and `:2287`, both in the `qa` pilot); the remaining three sit in `_revisable_stage` and `_record_escalation`, which themselves become services. Any context lacking `gate` forces a stage to reach back into the class on day one.

`ask_and_wait` exists because the `clarify` block does something no other service covers: it sets `self._status`, populates `self._pending`, and blocks on `workflow.wait_condition` reading `self._question_answers`. That is a distinct capability — *open questions to a human and block until answered* — and it is encapsulated behind one call. A stage must never touch those three attributes directly; they are workflow-class state.

**Run context reaches a step as parameters, not context fields.** Values like the codebase map (`self._codebase_map`, read at `:2827` and `:2836`), the integration head, the brief digest, and the seeded work are *data the orchestrator holds*, not services. They are passed explicitly into `step(...)`, which keeps `StageContext` a stable protocol rather than a bag that grows a field per stage. If a step needs a value, the signature says so.

**State ownership.** A step owns no run state across calls. It receives parameters, returns an artifact, and any state it would have mutated is either returned or set through a service. The worked example is `self._escalation_round`, instance state declared at `:865` and incremented at `:2025` inside `_dev_task`: this must become a per-task local or an explicit parameter when `qa` migrates. It is not merely a style point — `gates.py:84-88` already documents exactly this hazard for gate confidence ("gates interleave. Wave mode runs `_dev_task` concurrently … a second gate opening while this one awaits a human would overwrite a stashed value"), and `_escalation_round` is the same shape of latent defect. Migrating `qa` fixes it rather than carrying it across.

### 1.2 What Temporal actually constrains

Code motion is replay-safe on its own: replay validates the *sequence of commands* — activity, timer, and signal ordering — against history, not the source location of the code that issued them. The genuine constraints are narrower, and naming them precisely is what lets the rest be done freely. These rules are the substance every slice's `AGENTS.md` repeats locally.

**Rule 1 — handlers live on the workflow class's MRO, never in a step module.** The obvious phrasing — "handlers stay on the single `@workflow.defn` class" — is falsified by this repo's own code: `GateHost` (`workflows/gates.py:54`) is a mixin carrying `@workflow.signal submit_gate_decision` (`:98`) and three `@workflow.query` handlers (`:108`, `:112`, `:116`), inherited by `FeatureWorkflow` and others, and `temporalio` handles that correctly. Mixins are a blessed way to organise handlers. What is forbidden is a handler in a step module, which is not on any workflow class's MRO and would simply never be registered.

**Rule 2 — mutable run state has exactly one owner: the workflow instance.** See §1.1's state-ownership paragraph. Aliased mutable state is the classic route to replay divergence, and under wave-mode concurrency it is a live defect, not a theoretical one.

**Rule 3 — the passthrough principle.** A step module is imported inside the sandbox. Inside it, `workflow.unsafe.imports_passed_through()` covers **anything carrying host-shared identity or import-time effects**; ordinary sandboxed import is for *pure workflow-side helpers only*. Stated as a principle rather than a list, because enumeration kept missing categories the pilots cannot avoid. The categories it resolves to today:

- *Third-party and IO-adjacent modules* — the uncontroversial case.
- *Model modules* (`core/models.py`, a slice's `models.py`, `benchmarks/models.py`) — **identity, not serialization, is the reason.** Payload flow would survive a sandboxed duplicate, since payloads are untyped JSON (see the payload paragraph below), but `X is EnumCopy.MEMBER` across a host/sandbox duplicate pair is silently always `False`. `feature.py` performs nine such enum identity comparisons, and three of them are load-bearing for the pilots: `:1891` and `:1927` are inside `_dev_task` itself (`role_cfg.harness is HarnessKind.CREW`) and `:2293` is the task gate (`decision.outcome is GateOutcome.REVISE`). This is exactly why today's block passes `..models` through.
- *The agent registry* (`agents/roles.py`) — it constructs agent objects at import time (`:73-80`), and a step cannot reference `t_clarify` / `t_qa` / `resolve_role_model` without importing it. Re-executing that construction inside the sandbox is an import-time effect.
- *Workflow classes used as child-workflow handles* — see Rule 3a.

Note that this is a **new, stricter discipline** than what `feature.py` does today, and the spec says so rather than pretending it is the status quo: the existing block spans lines 20-223 and passes through roughly thirty internal modules, including pure helpers (`..pricing`, `..prompts`, `..gate`, `..handoff`, `..context.classify`) that the principle would have imported normally.

**Rule 3a — workflow-class references used as child-workflow handles are passed through.** `_dev_task` starts `CrewTaskWorkflow.run` (`:1938`) and the deploy stage starts `DeploymentWorkflow.run` (`:3601`); the `qa` pilot needs the crew reference. Importing a `@workflow.defn` module *inside* the sandbox re-executes it sandboxed and yields a duplicated class identity, which is precisely what the current passthrough avoids. Called out separately from Rule 3 because it is the case an implementer is most likely to get wrong.

**Rule 4 — a step module's module level is constants only.** No clock, no environment reads, no I/O at import time. `feature.py`'s own module level is the model to copy: `ActivityConfig` blocks and constants from `:225` onward and nothing else. Rule 3 says *where* a module is imported; Rule 4 says what is safe to execute *when* it is.

**Payload identity is a non-issue here, and the residual is stated.** The worker and client use `pydantic_data_converter`, whose `PydanticPayloadConverter.to_payload` writes only `metadata={"encoding": "json/plain"}` and reconstructs from the *current* signature's `type_hint` (`temporalio/contrib/pydantic.py:66-99`). No class or module identity is recorded in a payload, so relocating a Pydantic model between modules is transparent to in-flight histories. The residual risk is unchanged by this work and worth restating: a model's *field shape* must not change mid-deploy. There is also no `workflow.patch` / `workflow.deprecated` anywhere in `src/`, so no versioning machinery interacts with any of this.

### 1.3 Activity registration

`worker.py` currently imports activities by name from roughly twenty modules across lines 29-131 — a 103-line import block that every new activity extends. Instead: each slice exports `ACTIVITIES: list[Callable]`; `src/sdlc/stages/__init__.py` holds a `STAGE_MODULES` tuple; the worker composes `[a for m in STAGE_MODULES for a in m.ACTIVITIES]`. Explicit, not auto-discovered — import order and registration must stay deterministic and greppable — with one place to edit when a stage is added.

### 1.4 Ownership of types, and the transition rule

**The producer owns its artifacts.** A stage's `models.py` holds the types that stage *produces*: `ClarifiedRequirements` belongs to `stages/clarify/`, `QAReport` to `stages/qa/`. Downstream stages import those types directly, mirroring the DAG's dependency direction. A type import is not a stage call, so this does not weaken the cross-stage ban in the Decision.

`core/` holds only the types **no stage produces**: configuration and envelopes that the orchestrator or several stages own jointly — `PipelineConfig`, `GateDecision`, `RoleConfig`, `IdeaBrief`, `RunSummary`, `RunState`.

The alternative reading — "any type two stages touch belongs in `core/`" — was considered and rejected. In a pipeline nearly every artifact crosses stages (`ClarifiedRequirements` is referenced in six `src/` files), so that rule would empty every slice's `models.py` back into `core/models.py`, recreating the 73-class every-context-at-once file the Problem section opens with, and the §2 ceiling would then block the migration that produced it. Producer-owns is the only reading under which the slice layout and the ceiling are mutually coherent.

**Transition rule: call sites re-point; no re-export shims.** While migration is in flight, a symbol that has moved has exactly one home. A shim would create two legal import paths for one symbol — precisely the "two homes, agent guesses wrong" failure that §7's discovery table exists to prevent — and it would hold `models.py` and `activities.py` at their current size, defeating the §2 ratchet. Moving a stage is one commit that relocates its symbols and updates every importer; the test suite is the check.

## 2. The size rule

**A single hard ceiling of 1000 lines per file.** No soft target, no docstring waiver.

The reasoning matters, because a lower number is the obvious counter-proposal and was in fact proposed during design. Module size is governed by the seam, not by a number: a slice is whatever its process step needs. A soft target of ~400 lines *competes* with the seam principle and pushes an agent to split cohesive stage logic to satisfy an integer. A single hard 1000 needs no judgment and no escape hatch. The cost is real and accepted: it tolerates a 900-line file that ought to be smaller — which is why the Problem section names `assessment/activities.py` (926) and `workflows/assessment.py` (820) as readability problems the *seam principle* must fix, not as ceiling violations. The ceiling catches monsters; the seam catches everything else.

### 2.1 Scope

The ceiling applies to **authored source and living documents**: `src/**`, `tests/**`, `scripts/**`, `interfaces/**`, `agents/**`, `crew/**`, `blueprints/**`, `policy/**`, root-level `*.md`, and `docs/**` except where exempted below. Including `docs/**` is deliberate: B0's own outputs (`docs/features/<area>.md`, `docs/roadmap/tier-*.md`) are living documents, and a documentation architecture whose products escape its own ceiling would be self-defeating.

Exempt, each for a stated reason:

- `docs/superpowers/**` — plans, specs and reviews are **write-once historical records** describing work at a moment in time. Splitting a finished record serves no reader, and the largest are large because the work was (`2026-08-13-scan-phase-signals-plan-3.md` is 4883 lines). More decisively: the ratchet in §2.3 only functions over files that can shrink, so baselining ~50 immutable records would permanently break the "monotonically decreasing to zero" signal the whole mechanism relies on.
- `records/**` — verbatim Claude Design exports. Not authored here; splitting them would corrupt them.
- **Verbatim vendored data** — third-party schemas, payloads and reference implementations checked in unmodified as input. Two instances today: `tests/fixtures/hindsight-openapi.json` (13,422 lines) and `benchmarks/cases/**`, the measurement instrument's corpus, which holds vendored reference implementations and their data (`…/deveval-geotext/reference/geotext/data_file/cities15000.txt` is 23,355 lines). Same reasoning as `records/`: none of it is authored here, none can be split without ceasing to be the thing it vendors, and baselining it would park unmovable five-figure entries at the top of the file that is supposed to measure migration progress. The exemption is by nature, not by path, so a plan adding such data states why it qualifies. Note that `src/sdlc/benchmarks/` — the code that *reads* the corpus — is in scope via `src/**`. This is not a new judgment: `pyproject.toml`'s `[tool.ruff]` already carries `extend-exclude = ["benchmarks/cases"]`, commented "vendored fixtures … data, not product code". The ceiling adopts the boundary the linter already draws.
- Generated and machine-managed artifacts: `docs/*.html` (schema pages), `build/**`, `interfaces/**/dist/**`, `interfaces/**/node_modules/**`, `.venv/**`, `uv.lock`, `*-lock.json` (which is what keeps `interfaces/dashboard/frontend/package-lock.json`, 3656 lines, out).

Applying that scope, today's baseline is exactly six files:

| Lines | File |
|---|---|
| 3673 | `src/sdlc/workflows/feature.py` |
| 1647 | `ROADMAP.md` (leaves the baseline when deliverable 7 lands) |
| 1430 | `src/sdlc/activities.py` |
| 1334 | `src/sdlc/models.py` |
| 1177 | `tests/test_assessment_workflow_e2e.py` |
| 1092 | `src/sdlc/harness/adapters.py` |

`design/support.js` (1687) does not appear because `design/` is not an in-scope path, and it ceases to exist as a question when `design/` dissolves into `records/` (§8).

### 2.2 Measurement

**Physical lines** — newline-terminated lines plus a final unterminated one. Not logical lines, not statements, not "lines excluding blanks and comments": any of those would reward compressing code rather than splitting it.

The final-unterminated-line clause is not pedantry, and `wc -l` is **not** an implementation of this definition — it counts newlines only. The vendored fixture above is the worked example: it ends in `}` with no trailing newline, so `wc -l` reports 13,421 while this definition gives 13,422. An implementer who reaches for `wc -l` introduces a silent off-by-one that lets a file sit at exactly 1001 physical lines and pass.

### 2.3 The ratchet

`scripts/check_file_size.py` runs as a `pre-commit` hook against a checked-in `.file-size-baseline.json` mapping repo-relative path → line count at the time of baselining.

- a file **not** in the baseline that exceeds 1000 lines → **reject**;
- a file **in** the baseline that has **grown** → **reject**;
- a file **in** the baseline that has **shrunk** → the hook lowers its entry (or deletes it, once under 1000), rewrites the file, and fails once with *"baseline tightened — stage `.file-size-baseline.json` and re-commit"*. This is the standard `pre-commit` fixer contract, the same shape as `ruff --fix`, and it makes the ratchet advance automatically instead of relying on anyone to remember.

`feature.py` is not required to lose weight today. It is required never to gain any.

**Two modes, because a hook cannot see the whole tree.** `pre-commit` passes only staged filenames, so the hook (default mode) checks and tightens exactly those. Entries whose file was deleted or renamed cannot be noticed that way, so `--full` enumerates and prunes stale entries, and exits non-zero if the baseline is out of date. CI runs `--full`.

`--full` enumerates via `git ls-files`, not a filesystem walk: the ceiling governs what the repository carries, and enumerating tracked files alone keeps every untracked working artifact — `runs/`, `artifacts/`, `.venv/`, `build/`, `.worktrees/`, `__pycache__` — out by construction rather than by an exemption list that must be maintained. It also skips files whose first 8 KB contain a NUL byte, since a line count is meaningless for binary content.

This does **not** replace the path exemptions above, and one trap deserves naming: `.gitignore` lists `docs/superpowers/*` with a negation for `specs/`, but roughly thirty plan files predate that rule and remain tracked, because ignoring a path does not untrack what is already in the index. They would land in the baseline on the first `--full` run. The `docs/superpowers/**` exemption is what actually keeps them out. A stale entry is never a correctness failure — it only lets a deleted file's allowance linger — so it is reported, not enforced at commit time.

The baseline shrinks monotonically as (A) proceeds and reaches zero when the surgery is done. That is the honest measure of whether the migration is still moving.

## 3. Documentation architecture

**Three files per slice, one job each. They do not collapse into two.**

| File | Question | Reader |
|---|---|---|
| `stages/<stage>/<stage>.md` | **WHAT** — the contract, as numbered clauses | anyone |
| `stages/<stage>/AGENTS.md` | **HOW** to change it here — local invariants, §1.2's rules applied to this slice, how to run just this slice's tests | an agent about to edit |
| module docstring | **WHY** this file exists | someone reading the code |

Collapsing the first two couples things with different lifetimes: `<stage>.md` is evergreen product documentation, while `AGENTS.md` carries tool-specific guardrails that change when the tooling does. The third layer already exists as house style and is good — `src/sdlc/dashboard/api.py:1-16` is the model: it explains why the module lives under `src/` at all, why there are three write routes and not five, and what its security posture is and where that stops being acceptable.

Documentation lives at **both** levels. Co-located slice docs ride in the same diff as the code they describe, which is the only mechanism that reliably keeps a document honest. Central area docs give an agent macro-context without reading fifteen directories.

**The `docs/` tree:**

```
docs/
  documentation-rules.md    # how to write documents in this repo
  framework.md              # the stack's own conventions: Temporal, Pydantic AI, harnesses
  features/
    AGENTS.md               # rules for writing and maintaining area docs
    <area>.md               # narrative across the DAG
  modes/
    feature-clause-writing.md
    slice-migration.md
    focused-specs.md
  roadmap/
    tier-*.md               # ROADMAP.md §§9-17, split by tier
  reference/                # durable companions, still true:
                            #   foundation.md, architecture-review-2026-07.md,
                            #   presentation-pipeline-temporal.md
  reports/                  # dated one-offs, true when written:
                            #   feature-coverage-audit-2026-07-05.md,
                            #   deveval-import-report-2026-08-09.md,
                            #   external-ideas-2026-09.md
  schemas/                  # generated HTML: agents-schema, architecture-schema,
                            #   benchmark, benchmark-analysis, research-stage-schema, roadmap
  superpowers/{specs,plans,reviews}/   # unchanged
```

`reference/`, `reports/` and `schemas/` are where the twelve files currently loose in `docs/` land — three, three and six respectively. Naming their homes is part of B0's job: an architecture that leaves a fifth of the existing tree unaccounted for is not an architecture. The `reference` / `reports` split is by *durability*, not by date: a reference document is maintained when it goes stale, a report is a snapshot that is never updated. `docs/superpowers/reviews/` exists today alongside `specs/` and `plans/` and is listed so the tree is complete.

**The root monoliths.** `ROADMAP.md` splits into `docs/roadmap/tier-*.md` behind a thin root index. `ARCHITECTURE.md` and `PRD.md` stay whole: both are read end-to-end and both serve as a single-grep anchor for "what is true on main", and neither is large enough to be the problem `ROADMAP.md` is. The existing convention that `ARCHITECTURE.md` and `ROADMAP.md` describe **main only** — in-flight work lives in its design doc until merge — is preserved and stated explicitly in `documentation-rules.md`, because it is currently tribal knowledge.

The `FactoryWorkflow` → `FeatureWorkflow` drift is fixed at **all four sites** (`ARCHITECTURE.md:36`, `:59`, `:73`, `:336`), not only in §3. Two of them are in §2, ahead of §3 — fixing §3 alone would leave the doc wrong in its first diagram, which is the very thing this fix exists to prevent.

## 4. Clauses

Slice docs carry locally numbered clauses — `CLARIFY-1`, `CLARIFY-1.1` — and **each clause anchors to an existing requirement id: an `FR-xxx`, an `NFR-x`, or an `E-xx` epic.**

Both halves are load-bearing. That vocabulary already spans `PRD.md`, `ROADMAP.md` and `ARCHITECTURE.md`; a second, unanchored ID namespace would be a shadow taxonomy competing with it. But those ids are too coarse to describe an atomic state transition, which is precisely what a test needs to cite. Local clauses under a global anchor give both: the granularity to test against, and traceability upward.

Restricting the anchor to `FR-xxx` alone would leave much of the pipeline unclausifiable, since a good deal of recent work (the crew, memory, the assessment port) is `E`-numbered and has no `FR` of its own. `ADR-xx` is deliberately *not* an anchor: an ADR records a decision, not a requirement, and a clause that cites one is describing rationale rather than obligation.

We are not inventing a second ID system. We are giving the existing one a level of detail it lacks.

`docs/modes/feature-clause-writing.md` carries the method. Whether pytest gains a marker that cites clause IDs is deliberately left to (A), where there will be a real migrated slice to try it on.

**Where clauses sit among the other things this repo writes down.** Three artifacts answer three different questions, and conflating them is how a specification quietly overwrites behaviour that was a contract:

| Artifact | Question |
|---|---|
| a design spec under `docs/superpowers/specs/` | what we **intend** |
| a slice's numbered clauses | what **behaviour** matters |
| the test suite | what we **verify** |

The distinction that earns its place here is the second against the first. A spec describes a system as someone means it to be; a system that already exists is defined by what it does, and some of what it does is load-bearing precisely because nobody designed it. Clauses are written from observed behaviour, not from intent — which is why they live beside the code and a spec does not.

A fourth question — *what actually happened* when an agent worked on this repository — has no artifact here, and B0 does not add one. It is recorded as deferred rather than answered. Note that Kroker the product implements telemetry, evals and golden cases for the pipelines it runs on other repositories (`src/sdlc/observability/`, `src/sdlc/eval/`, `benchmarks/cases/`); those are product features and are not this repository's development harness. The two must not be conflated in either direction: nothing in B0 or its successors adds product functionality, and the product's machinery is not repurposed as our own tooling without a decision that says so.

## 5. Test placement

Tests move to `tests/<stage>/`, mirroring `src/sdlc/stages/<stage>/`. Cross-cutting tests — including the 42 that exercise `FeatureWorkflow` across several stages — live in `tests/integration/`.

The mechanics were verified against the real layout. `pyproject.toml` sets `pythonpath = [".", "src"]`, so the package-qualified `from tests.fakes.… import …` style every test uses keeps working from a nested directory, and `tests/conftest.py` applies recursively to subdirectories. `testpaths = ["tests"]` and the marker-gated default run are unaffected.

Two mechanics the plan must honour:

1. **Test basenames stay globally unique.** There is no `tests/__init__.py`, so pytest's rootdir-based collection requires unique module basenames once files scatter into subdirectories. The current naming already satisfies this (`test_clarify_routing.py`), and the rule is: keep the full descriptive name when the file moves — `tests/clarify/test_clarify_routing.py`, not `tests/clarify/test_routing.py`. Renaming for brevity during a move is how this breaks.
2. **`tests/` root stays legal.** It does not have to end up empty. `tests/conftest.py`, `tests/fakes/`, `tests/fixtures/` and `tests/helpers_risk.py` belong there permanently, and a test that belongs to no stage and is not an integration test may stay at the root. The migration table in §7 tracks stages, not every test file.

Two alternatives were rejected:

- **Tests inside the slice** (`src/sdlc/stages/<stage>/tests/`) is the purest reading of the seam principle, but it ships test code and fixtures into the installed wheel, and the cross-cutting tests would have no honest home without inventing an "orphan tests" slice.
- **Flat, with naming as the only link** leaves the agent doing exactly the directory-hopping this whole design exists to end.

## 6. The agent layer

**`AGENTS.md` at every level** — root, slice, and infrastructure package. It is the cross-tool convention, the root already uses it (103 lines), and `AGENT.md` in the singular was rejected because no tool discovers it automatically.

**The root `AGENTS.md` is a router, not an encyclopedia, and carries a 250-line ceiling to keep it one.** It indexes: where things live, which commands to run, which rules bind, where the depth is. It never inlines a stage's contracts, schemas, or business logic — those live in the slice, which is the entire reason the co-located layer exists. The failure this guards against is specific: a root instruction file that grows without bound spends context budget on every session and flattens everything it contains to the same priority, so the one rule that mattered reads like the twenty that did not. The 250-line ceiling is deliberately far below the repo-wide 1000 — a router that needs a thousand lines has stopped being a router. The migration table in §7 is the shape to imitate: paths and statuses, pointing outward.

**Root `CLAUDE.md` becomes a pointer, not a symlink** (symlinks are unreliable on Windows, which is this repo's primary platform), and it must carry one explicit directive:

> Before editing files in a subpackage or stage, read the nearest `AGENTS.md` in that directory.

That directive is load-bearing and belongs there regardless of tooling: nested-`AGENTS.md` auto-discovery varies by assistant and by version, and an explicit instruction makes the co-located layer work under every one of them rather than depending on a behaviour that may or may not be present. (`CLAUDE.md` is also currently untracked — it must be committed, not merely written.)

Note the standing hazard the root `AGENTS.md` already documents and which this work must not blur: the `agents/` directory is the **product's** runtime role registry, loaded by `src/sdlc/agents/loader.py`. `AGENTS.md` files are instructions for whoever is editing the repo. Adding `AGENTS.md` files throughout makes that distinction more important, not less, so it is restated in `documentation-rules.md`.

**Two role rules, both in force.**

*The sandbox boundary — who may.* Orchestrator agents working in the primary checkout (Claude Code, advisor, reviewer) may edit specs, stage contracts, and schemas. Sandboxed coding harnesses (`claude -p`, `opencode run`, running inside a per-task worktree) may modify only code and tests, and are forbidden from editing `<stage>.md` files or root specs. This is not hypothetical: when Kroker's own pipeline runs against Kroker, a harness is editing this repository, and a harness that can rewrite the contract it is being judged against has no contract.

*The artifact boundary — what is owed.* Whoever changes a stage's behaviour updates its clauses in the same diff. A clause without code and code without a clause are both defects.

The first rule says who is allowed to touch what; the second says what anyone who touches it owes. Tool-name silos of the form "tool X never touches file type Y" were rejected as inapplicable — that constraint existed in the reference stack because two specific agents were colliding over CSS, and Kroker has no equivalent collision.

## 7. Migration

Piecemeal, never big-bang. `clarify` and `qa` are the pilots and are moved **whole** — step, activities, models, prompts, both documents, and tests.

They are chosen because between them they falsify the easy version of the seam contract. `clarify` is the only stage that opens questions to a human and blocks on `workflow.wait_condition`, so it forces the `ask_and_wait` service and the rule that `_status` / `_pending` / `_question_answers` are workflow-class state. `qa` sits inside the per-task loop, calls `_gate` directly, mutates `_escalation_round`, performs enum identity comparisons at `:1891` and `:1927`, and starts a child workflow — so it forces the gate service, the state-ownership rule, and Rules 3 and 3a. A pair of easy stages would have let a thinner context — reporting, roles and memory, and nothing else — look sufficient; these two are what prove the inventory in §1.1 is the real one.

After the pilots the rule is **"you touched a stage, you move it."**

During the transition the root `AGENTS.md` carries a table — **stage → where it lives → status** — and that table is declared the authoritative discovery map. An agent looking for a stage reads the table; it does not guess, and it does not search two locations. Keeping the table current is part of moving a stage, not a follow-up.

## 8. Claude Design and `records/`

Design exports live in `records/<YYYY-MM-DD>-<topic>/`, at the repository root, tracked in git, deliberately outside `docs/` so that raw visual artifacts never dilute evergreen documentation. Full dates, not month granularity: a topic can be revisited twice in a month, and a date-ordered listing is the whole point of the directory.

The `design/` directory is dissolved: `design/Factory Console.dc.html` (46 KB), `design/support.js` (61 KB) and `design/.thumbnail` move to `records/2026-07-12-factory-console/`, dated by the commit that added them (`2e7b6c0`). That export predates this scheme and becomes its first record rather than an orphan at the root.

B0 fixes the location and the principle only. The Vue design system, the component documents, and the showcase route are (C)'s work, and the one thing B0 asserts about them is that a UI component's document is a feature-clause document under §4's rules like any other.

## 9. Deliverables

1. `AGENTS.md` (root) — rewritten: the cutting principle, the size rule, both role rules, the stage migration table.
2. `CLAUDE.md` (root) — pointer plus the "read the nearest `AGENTS.md`" directive; committed, not just written.
3. `docs/documentation-rules.md`, `docs/framework.md`, `docs/features/AGENTS.md`, `docs/modes/{feature-clause-writing,slice-migration,focused-specs}.md`.
4. Templates for `<stage>.md` and a slice's `AGENTS.md`, the latter carrying §1.2's rules.
5. `StageContext` (eleven services), the `step` signature, the parameter-vs-service rule, the producer-owns ownership rule, and the `ACTIVITIES` / `STAGE_MODULES` registration contract — specified here as contracts; the code lands in (A).
6. `scripts/check_file_size.py` (default and `--full` modes, physical-line measurement per §2.2), `.file-size-baseline.json` seeded with the six files in §2.1, the `pre-commit` hook entry, and the CI step.
7. `ROADMAP.md` split into `docs/roadmap/tier-*.md` plus a thin root index.
8. `ARCHITECTURE.md` drift fix at lines 36, 59, 73 and 336.
9. `docs/` reorganised: `reference/`, `reports/`, `schemas/` created and the twelve loose files rehomed.
10. `records/` created; `design/` dissolved into `records/2026-07-12-factory-console/`.

## Risks

**The permanent hybrid.** The failure mode of piecemeal migration is that it stops after the pilots, leaving thirteen stages in `feature.py` and two outside it forever, with agents unsure which location is canonical. The mitigations are structural rather than exhortative: the discovery table in the root `AGENTS.md` is authoritative, the no-shims rule (§1.4) means a symbol never has two homes, the `.file-size-baseline.json` ratchet makes the debt visible and monotonically decreasing, and "you touched a stage, you move it" attaches migration to work that was going to happen anyway. The risk is not eliminated, and (A)'s plan should carry an explicit checkpoint on it.

**`StageContext` accreting.** A protocol with eleven members is defensible; one with thirty is a god object. The guard is §1.1's parameter-vs-service rule — data flows through the signature, only *capabilities* go on the context — and the review question for every future addition is "is this a service the orchestrator provides, or a value it holds?".

**The passthrough principle is a judgment call at each import.** Rule 3 trades an enumerable list for a principle precisely because enumeration kept missing categories, but the cost is that "does this carry host-shared identity or import-time effects?" must be answered per import rather than looked up. The mitigation is that the answer is nearly always yes for anything internal that is not a pure function, and each slice's `AGENTS.md` records the answers that slice arrived at, so the judgment is made once per module rather than once per reader.

**Documentation volume.** Three documents per slice across ~15 slices is ~45 new files. The mitigation is that each answers exactly one question and the templates are short; the anti-mitigation to watch for is `AGENTS.md` files that grow into restatements of `<stage>.md`. `docs/documentation-rules.md` should state the failure explicitly so a reviewer can name it.

**The 1000-line ceiling is deliberately loose.** Accepted, with the reasoning in §2. If (A) finds that slices routinely land near 900 lines, that is evidence the seam was drawn wrong, not evidence the number should change.
