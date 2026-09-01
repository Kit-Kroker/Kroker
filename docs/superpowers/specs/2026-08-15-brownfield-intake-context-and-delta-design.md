# Brownfield intake, context, and the architecture delta

**Date:** 2026-08-15
**Status:** approved design, ready for planning
**Scope:** E-84 (new item), FR-102's remainder
**Satisfies:** FR-102 (greenfield/brownfield classify + `CodebaseMap` + delta); DAG stages 0 and 2; closes P2's brownfield half
**Depends on:** E-46 (scan S1–S5), E-40 (`Measurement`), FR-301's `_revisable_stage`
**Does not cover:** E-56 (`/enrich`), E-59 (repo connection), E-53 (spec seeds), stages 1 and 3

## Problem

FR-102 asks for three things: greenfield/brownfield classification, a
`CodebaseMap`, and a brownfield delta. E-47a/b/c and E-48 built the map's
inputs — the roadmap says so outright ("together they satisfy FR-102's
`CodebaseMap`", §11 E-47) — and §15 ranks that chain first precisely because it
"unblocks P2 brownfield whether or not the audit ships". That chain closed with
E-48 on 2026-08-15. What remains is the half the roadmap now describes as
"intake classification + brownfield delta, no longer E-47".

Today the pipeline has no brownfield behaviour at all. Three facts, each
verified against code rather than against this tracker:

1. **`brief.mode` is written and never read.** `ProjectMode` is a required
   field on `IdeaBrief` (`models.py:226`), set by the CLI (`cli.py:334`), by
   `TidyUpWorkflow` (`tidyup.py:215`), and by the benchmark harness
   (`benchmarks/workflow.py:161`). No branch in `src/sdlc/` reads it. The DAG's
   stage 0 row is therefore a field, not a stage.
2. **The repository is a string with a fallback.** `feature.py:1694` reads
   `repo_path = idea.repo_url or "/var/sdlc/repo"`, with the comment "prepared
   by a setup activity IRL". Nothing establishes that the path is a repository,
   that it matches the declared mode, or that it contains anything.
3. **The delta field exists, is documented, and is unenforced.**
   `ArchitectureSpec.affected_modules` (`models.py:259`) is annotated
   `# brownfield` and `docs/agents-schema.html:892` documents it as "Brownfield
   delta (added / modified / removed)". It is written by `tidyup/backlog.py:103`
   and by benchmark seeds. It is read by nothing.

The consequence worth stating plainly: `TidyUpWorkflow` already starts feature
children declaring `mode=BROWNFIELD` against a real repository, and
`FeatureWorkflow` treats them exactly as greenfield. The mode is decoration.

Two properties make this more than wiring:

- **A second extraction path would be a second answer.** The assessment tier
  already extracts modules, contracts and members from a pinned tree. Building
  a `cartography.py` that re-walks the same tree yields two maps that can
  disagree about one repository, and no rule for which is right. This design's
  central constraint is that there be exactly one extraction path.
- **A delta nothing checks is a delta nothing can trust.** The roadmap's own
  framing of the BrownKit port is that its value is enforceability — gates
  "graded by the model that produced the artifacts" become "`CheckResult`s
  computed by pure code" (§ 2026-07-25 note (b)). An `affected_modules` list
  the Architect writes about files it never read is the same defect FR-914 and
  SC-7 exist to prevent, one stage earlier.

## Decision

Thirteen decisions, numbered for the plan and for later citation.

### D1 — one extraction path, shared by both tiers

`AssessmentWorkflow._scan`'s body (`workflows/assessment.py:373`) moves to a
shared workflow-context helper:

```python
async def scan_tree(repo_dir: str, commit_sha: str,
                    triage: RepoTriage | None = None) -> ScanOutcome
```

`AssessmentWorkflow._scan` becomes a call to it. `FeatureWorkflow._context`
calls the same function. Both get the same thirteen signals, the same two-wave
fan-out through `run_or_degrade`, the same per-signal degradation, and the same
memo keyed on `(tree_hash, signal_version, rules_sha)`.

This is the whole point of sourcing the map from the scan, so it is decision
one: the audit tier and the pipeline tier physically cannot produce two
different maps of one tree, because they run the same code over the same memo.
A brownfield feature run on a tree an assessment already scanned pays nothing.

The rejected alternatives are recorded because both are locally reasonable. A
`ContextWorkflow` child would match the deploy/triage/tidy-up pattern and keep
the fan-out out of the parent's history — but it puts new multi-workflow
fan-out on the host that has already deferred `TidyUpWorkflow`'s e2e for
contention (P5's note), i.e. it ships with verification debt on day one. A
single `build_codebase_map` activity would be the smallest parent code — but it
swallows per-signal memoization and per-signal degradation, so one unreadable
blob either fails the whole map or vanishes inside the activity. That is the
conflation FR-915 forbids.

### D2 — placement: `src/sdlc/context/`, and what stays in root `models.py`

Following the package convention every subsystem since E-40 has used
(`triage/`, `capability/`, `tidyup/`, `assessment/`, `board/`, `deploy/`):

| Module | Contents | Purity |
|---|---|---|
| `context/models.py` | `CodebaseMap`, `MapModule`, `MapContract`, `HotSpot`, `RepoObservation`, `IntakeVerdict` | pure |
| `context/classify.py` | `classify(observed, declared) -> IntakeVerdict` | pure |
| `context/project.py` | `project(scan, tree_hash, commit_sha) -> CodebaseMap` | pure |
| `context/delta.py` | `check_delta(delta, paths) -> CheckResult` | pure |
| `context/render.py` | `render_for_prompt(map) -> str` (D12) | pure |
| `workflows/scanning.py` | `scan_tree()` — the D1 extraction | workflow-context |

`BrownfieldDelta` is the one contract that does **not** live here: it is a field
of `ArchitectureSpec`, so it goes in root `models.py` beside it. The dependency
direction is one-way and must stay so — `context/` imports `models.py`,
`models.py` never imports `context/`. Putting `BrownfieldDelta` in `context/`
would invert it and risk the import cycle `models.py → context → assessment →
triage → models.py`.

### D3 — intake verifies the declaration; brownfield fails closed, greenfield warns

`IdeaBrief.mode` is already required and operator-declared, so stage 0 does not
infer a mode — it **verifies** the declared one against the repository, which is
what the spec's deterministic, no-LLM row (`SDLC-spec-v2.md:37`, success
criterion "mode ∈ {greenfield, brownfield} resolved") can actually mean when the
field is mandatory.

One activity observes, one pure function decides:

```python
@activity.defn
async def classify_repo(inp: RepoProbeInput) -> RepoObservation
```

`RepoObservation` carries `is_git_repo`, `base_branch_resolves`, `commit_sha`,
`source_file_count`, and a `reason` when any of those could not be established.

"Source file" means `scan/sources.py`'s `SOURCE_EXTENSIONS` — the same
definition E-47b's coverage denominator uses. Reusing it rather than writing a
second rule matters for one reason: intake decides a repository is mappable, and
the scan decides what it can map. Two different definitions of "has code" would
let a repository pass intake and then produce an empty map.

The rules, and the asymmetry between them:

- **Declared `brownfield`, tree absent / not a repository / no source files →
  fail closed**, before any model call.
- **Declared `greenfield`, tree populated → record a warning, continue.**

The asymmetry is deliberate and load-bearing, so it is stated rather than left
to be discovered. The brownfield claim is a precondition for everything
downstream — the map, the delta, the check — and a brownfield run without a tree
is not a weaker run but an ungrounded one (ADR-18's reasoning about
capability-mapping an unbuildable repo, applied one tier down). The greenfield
claim carries no such weight: greenfield means only that "the Architect owns
stack + file tree" (`ARCHITECTURE.md:85`), which stays coherent against a repo
holding a README, a licence, CI config, or a previous run's work. Failing it
would break existing greenfield runs and benchmark cases for no invariant.

### D4 — the pin is the integration head

Context runs **after** `setup_integration_branch` (`feature.py:1701`) and pins
`integration.head_sha`. That SHA is the branch point the work will actually be
based on, so the map describes the tree the Architect is planning against — not
`base_branch`'s tip at some other moment. It also means the worktree already
exists when context runs, and that `_context` needs no path arithmetic of its
own (the workflow never computes worktree paths — `feature.py:1698-1700`).

Pinning a commit rather than a branch is what makes the map reproducible and the
memo sound, which is the same reason `assessment_resolve_tree` exists.

### D5 — no triage, and the degradation is honest rather than hidden

`scan_tree` is called with `triage=None` from the feature path. This is
legitimate rather than a shortcut, and `inherit.py` is why: every inherited
category has an explicit absent branch (`_absent`, lines 35-37) that yields
`not_collected` naming the missing triage signal. Five signals (SS1, SS2, SS3,
QS1, QS4) lose an inherited half and say so; S1–S5 — the capability family that
*is* the map — take no inherited half at all and are unaffected.

So a triage-free scan produces a complete extraction layer and five honestly
degraded security/QA categories. The map reads only S1–S5 plus the testability
and coverage records, so nothing the map needs is degraded by the absence.

Requiring a triage would have meant requiring `admits(triage,
require_human=True)` (`assessment.py:622`) — a human-approved Tier 2 admission
before any brownfield feature run, making P2 depend on P6. §15 is explicit that
P5 and P6 do not depend on later phases; this keeps that true for P2.

### D6 — a map that did not collect fails the run

If `CodebaseMap.collected` is not `MEASURED` — no tree hash, S5 absent, the
scan degraded past usefulness — the brownfield run **fails closed at stage 2**
with the reason.

The alternative is worse in a specific way. Proceeding with an unmeasured map
means the delta check silently stops running, because there is nothing to
resolve against — so the grounding guarantee disappears at exactly the moment
the ground is weakest, and the run is indistinguishable from a healthy one.
That is the shape of the defect the roadmap records for SARIF: "a broken
scanner reads as a passing security floor" (FR-915 note (b)), and it is why
`security_scan_collected` sits in `ABSOLUTE_FLOOR` beside
`security_no_critical`. A brownfield run whose defining input could not be
collected gets the same treatment.

A useful consequence: because D6 fails before the check, `check_delta` never has
to represent "the path set is unknown". It only ever runs against a measured
tree, so its `CheckResult` is a real pass/fail rather than a third state
`CheckResult` cannot express.

**Partial** degradation is different and does not fail: individual signals that
did not collect leave their sections `not_collected` with reasons, the map is
still `MEASURED`, and the run proceeds. The delta check is unaffected, because
D8 resolves against the tree rather than against the scan's attributions.

### D7 — the delta is typed three ways; `affected_modules` becomes derived

```python
class BrownfieldDelta(BaseModel):
    added: list[str] = []
    modified: list[str] = []
    removed: list[str] = []
```

added to `ArchitectureSpec` as `delta: BrownfieldDelta | None`, expected in
brownfield and absent in greenfield.

**Where "expected" is enforced: at the stage, not on the contract.**
`ArchitectureSpec` carries no mode — it cannot, since the mode belongs to the
`IdeaBrief` — so a model validator has no way to know a delta is required. A
brownfield spec arriving with `delta is None` is therefore treated by
`check_delta` as a failing `CheckResult` ("no delta proposed"), which routes it
through D10's re-prompt exactly like an unresolvable path. One failure path for
one class of problem, rather than a contract error and a check that disagree
about whose job it is.

A flat `affected_modules` list cannot express three classes, and the three
classes have opposite grounding rules (D8) — a `modified` path must exist, an
`added` path must not. So the typed delta becomes the authority, and
`affected_modules` is **derived** from it by a model validator (`modified +
removed`) when a delta is present. Existing writers keep working unchanged:
`tidyup/backlog.py:103` and the benchmark seeds set `affected_modules` directly
on specs that carry no delta, and those still validate.

Deriving rather than deprecating is the choice here because the field is
documented in the public schema page as the delta; giving it one authority is
cheaper than removing a documented field and leaves exactly one place that can
state what changed.

### D8 — the delta resolves against the tree, activity-side

```python
def check_delta(delta: BrownfieldDelta,
                paths: frozenset[str]) -> CheckResult          # pure
```

with a thin activity supplying `paths` from `git ls-tree -r --name-only` at the
pinned commit.

Two decisions are folded in here, both consequential.

**The resolution set is every file in the tree — not the map's attributed
files.** E-47b's denominator lesson applies directly: attribution is
best-effort, its coverage floor defaults to 0.90, and its regex reference table
has a pinned known false positive
(`test_known_false_positive_a_dynamic_reference_reads_as_dead`). Resolving
against attributed files would fail the Architect for naming a real config file
the scan never attributed — a false accusation of fabrication, which is the
most expensive possible error for a check whose whole purpose is trust.

**The path set does not travel in workflow history, and not in the map.** A
large repository's full path list carried inline would bloat every brownfield
run's history against ADR-10's claim-check discipline, and would push
`CodebaseMap` past what the Architect's `context_budget_tokens` (FR-801) can
take. Keeping resolution activity-side means the workflow sees one
`CheckResult`, and the map stays prompt-sized by construction.

The rules, by class:

| Class | Rule | Rationale |
|---|---|---|
| `modified` | MUST resolve | modifying a file that does not exist is fabrication |
| `removed` | MUST resolve | removing a file that does not exist is fabrication |
| `added` | MUST NOT resolve | adding a file that exists contradicts the tree |

`added` is checked rather than exempted because the contradiction is the same
species and the check is free. It is also what makes the three classes real
rather than "two meaningful classes and a free-form list".

### D9 — normalization is conservative, and basename matching is forbidden

Both sides normalize to repo-relative POSIX paths: forward slashes, no leading
`./`, no leading separator, no `..` segments. A path that still does not match
after that is a failure.

What normalization must **not** do is match on basename or suffix. `src/app.py`
and `tests/app.py` are different files, and a check that accepts either has
stopped verifying the claim it reports on. This is FR-914's rule about the two
grounding profiles that "must never be merged", in its cheapest form: a
normalization aggressive enough to rescue a wrong path is a normalization that
launders fabrication into a pass.

The forward-slash rule is not incidental — the development host is Windows and
git reports POSIX paths, so a `\`-vs-`/` mismatch is the most likely way this
check fails for a reason that has nothing to do with the Architect.

### D10 — one bounded re-prompt, then fail closed — and why it is not a gate round

The check runs inside `_run_architect`, on the spec `_cached_stage` returns,
before the gate. On failure the unresolvable paths become machine-generated
guidance and the producer re-runs, bounded by a new
`PipelineConfig.max_delta_retries: int = 1`. Past the bound, the stage fails
closed.

Placing it before the gate rather than inside `_revisable_stage`'s loop is
deliberate. `_revisable_stage`'s rounds are FR-301 *gate* rounds — a human
asking for a revision, bounded by `max_gate_rounds` and escalating to a hard
human gate on exhaustion. A deterministic check re-prompting a model is FR-202's
*validation retry*. Spending gate rounds on machine retries would mean a repo
that triggers two path typos arrives at the human gate with its revision budget
already consumed, and the calibration signals SC-6 reads (`RunSummary.gates[]`)
would count machine retries as human rounds.

The retry composes with memoization for free: guidance is already part of the
architect memo key (`feature.py:2019`, `reqs.model_dump_json() + (guidance or
"")`), so the retry has a distinct key and re-prompts rather than re-serving.

`max_delta_retries` is scoped narrowly on purpose. FR-202's general
`validation_retries` knob stays open; this design does not claim to close it.

### D11 — memoization: the map digest enters the architect key, greenfield unchanged

The architect's `_cached_stage` input gains the `CodebaseMap` digest in
brownfield — a canonical digest, never the map's prose, following `brief_digest`
(FR-103) and `context_digest` (E-48 DD10) exactly. A changed tree invalidates
architecture and nothing else.

In greenfield the key is byte-identical to today's, so no existing memo is
invalidated by this work. The one unavoidable invalidation is D13's prompt edit.

### D12 — the map has two renderings, and the prompt one is bounded

`CodebaseMap` is persisted complete. What reaches the Architect's prompt is a
bounded rendering: modules ranked by member count, contracts grouped by kind,
hot spots capped, each truncated list carrying an explicit `… N more` marker so
the model is told it is seeing a subset rather than left to assume completeness.

`ARCHITECTURE.md:169-171` requires this in as many words — high-volume
exploration "uses programmatic access — tools that filter and extract — rather
than streaming the corpus through the context window" — and FR-801 enforces a
per-role `context_budget_tokens` at prompt assembly regardless.

Truncation is deterministic (a total sort, ties broken by path) because a
rendering that varies across identical inputs would make the architect memo key
unstable and NFR-10's reproducibility claim false.

### D13 — seeded runs skip both stages, and the prompt edit invalidates once

Seeded runs enter at stage 4 (`feature.py:1715`) and continue to skip stages 0
and 2. `TidyUpWorkflow`'s children declare `BROWNFIELD` and carry a mechanical
finding that already answers what to build; they have no Architect call to
ground and would pay for a map nothing reads. E-44's D1 reasoning is unchanged
by this work.

The Architect's `agents/architect/instructions.md` gains a brownfield branch:
given a map, emit a delta. Because prompt bytes hash into `PROMPT_SHAS` and from
there into `content_key` (FR-806, §9.1), this edit invalidates **every**
project's architect memo once, greenfield included — the loader reads one
`instructions.md` per role, so the greenfield and brownfield instructions share
a file and a hash. The cost is one-time and correct rather than avoidable; it is
recorded here so it is not discovered as a surprise cache miss.

## Contracts

```python
# context/models.py
class RepoObservation(BaseModel):
    is_git_repo: bool
    base_branch_resolves: bool
    commit_sha: str = ""
    source_file_count: int = 0
    reason: str = ""


class IntakeVerdict(BaseModel):
    mode: ProjectMode
    ok: bool
    warning: str = ""
    reason: str = ""


class MapModule(BaseModel):  # from ScanResult.candidates (S5-merged)
    name: str
    member_paths: tuple[str, ...]
    confidence: Confidence


class MapContract(BaseModel):  # from contract-kind CandidateMembers
    kind: MemberKind
    value: str  # "POST /api/payments"
    path: str
    line: int | None = None


class HotSpot(BaseModel):  # from testability + coverage records
    path: str
    reason: str
    metric: Measurement


class CodebaseMap(BaseModel):
    tree_hash: str
    commit_sha: str
    modules: tuple[MapModule, ...] = ()
    contracts: tuple[MapContract, ...] = ()
    hot_spots: tuple[HotSpot, ...] = ()
    modules_collected: Measurement
    contracts_collected: Measurement
    hot_spots_collected: Measurement
    collected: Measurement
    # _unmeasured_carries_no_payload, per CapabilityMap's validator
```

```python
# models.py, beside ArchitectureSpec
class BrownfieldDelta(BaseModel):
    added: list[str] = []
    modified: list[str] = []
    removed: list[str] = []
```

`ArchitectureSpec` gains `delta: BrownfieldDelta | None = None`;
`affected_modules` becomes derived from it when present (D7).
`PipelineConfig` gains `max_delta_retries: int = 1`.

New check name: `brownfield_delta_grounded`. It is **not** added to
`ABSOLUTE_FLOOR` — that frozenset governs the merge gate's checks, and this
check fails its own stage before a plan exists (D10).

## Failure modes

| Failure | Behaviour | Why |
|---|---|---|
| brownfield declared, path is not a repo | run fails at stage 0 | D3 — precondition, not a degradation |
| brownfield declared, tree has no source files | run fails at stage 0 | D3 |
| greenfield declared, tree populated | warning recorded, run continues | D3 — no invariant depends on it |
| tree hash will not resolve | run fails at stage 2 | nothing can be memoized or reproduced |
| S5 did not collect | run fails at stage 2 | D6 — the map has no modules to ground against |
| one signal did not collect | section `not_collected` with reason; run continues | D6 — partial ≠ absent |
| Architect names a non-existent `modified` path | re-prompt once, then stage fails | D10 |
| Architect names an existing `added` path | re-prompt once, then stage fails | D8 |
| delta absent on a brownfield spec | `check_delta` fails; re-prompt once, then stage fails | D7 — enforced at the stage; the contract cannot see the mode |
| seeded (tidy-up) run | stages 0 and 2 skipped | D13 |

## Testing

TDD throughout; every pure module carries the order-independence assertion this
repo now requires (NFR-10, per E-47b/E-47c).

**Pure units.** `classify()` over the observation matrix, including both D3
asymmetry cases. `project()` — byte-identical across input order; a
`not_collected` signal yields a `not_collected` section and never an empty list.
`check_delta()` — the three classes' opposite rules; a basename-only match
**fails** (D9's forbidden rescue, pinned as a test so a future normalization
cannot quietly add it); Windows-style separators normalize and match.
`render_for_prompt()` — deterministic truncation, `… N more` present when
truncated.

**Seam.** `scan_tree`'s extraction is proven by `AssessmentWorkflow`'s existing
tests staying green — the refactor is behaviour-preserving by construction, and
that is the assertion.

**Workflow.** A `FeatureWorkflow` brownfield test drives intake → context →
architecture against a fixture repo, with an Architect stub naming a fabricated
module, and asserts the run fails closed rather than proceeding to plan. This is
the SC-7-shaped case that justifies the design, so it is the test that must
exist. A second asserts a greenfield run's behaviour and memo key are unchanged.

## Scope

### Not covered

- **Repo acquisition.** The path is local. E-59 owns app install, short-TTL
  repo-scoped tokens, and PR-only delivery. Note that `IdeaBrief.repo_url` is
  misnamed for what it carries — `tidyup.py:216` passes `inp.repo_dir`, a local
  directory — recorded as OQ-B2 rather than renamed here.
- **`CapabilityMap` consumption.** The map is projected from the scan (D1), not
  from `discover`'s output. E-56 owns `/enrich` as a declared hashed input, and
  taking it here would take scope from a planned item.
- **Stages 1 and 3.** No `Constitution`, no standalone `Requirements`. Both are
  separate unbuilt stages and neither is needed for the brownfield path.
- **Brownfield deploy.** `SDLC-spec-v2.md:50` wants "PR merged + env deploy" and
  `open_pull_request` already exists, but that is a stage 13 change and does not
  belong in this increment.
- **FR-202's general knob.** `max_delta_retries` is scoped to this check (D10).
- **SC-8.** Still a corpus problem, unchanged by this work.

## Roadmap deltas

| Item | Change |
|---|---|
| E-84 | new item — this spec |
| FR-102 | `[ ]` → `[x]` — classify, `CodebaseMap`, and delta all land |
| §1 stage 0 (intake) | `[ ]` → `[x]` — mode branches, verified deterministically |
| §1 stage 2 (context) | `[ ]` → `[x]` — `CodebaseMap` from the shared scan |
| §1 header | 9 of 15 stages → **11 of 15** |
| P2 | brownfield-mode half closes; dashboard backend (E-75) remains the other half |
| FR-202 | unchanged ⚠️ — a scoped retry bound is not the general knob (D10) |
| FR-913 | unchanged — this consumes the scan, not `discover` |
| SC-7 | the "zero fabricated path refs" clause becomes computed for architecture, one stage before any finding-producing stage |
| NFR-9 | context adds **no** execution of repository code: `git ls-tree` plus blob reads at the pinned commit. (The feature run's later stages execute the repo's build and tests, as they already did under E-44.) |
| NFR-10 | five more pure modules under the order-independence assertion |
| ADR-11 | deterministic DAG now holds for 11 of 15 stages |
| §7 | `_pipeline` grows by one stage — E-72's accretion concern, unchanged in kind |

**Unrelated observation, recorded not fixed:** E-82 (the promptfoo prompt gate)
is shipped code referenced by `README.md:95`, `pyproject.toml:29`, and all of
`src/sdlc/eval/`, but appears nowhere in `ROADMAP.md`'s E-item lists. E-83 is
referenced only via OQ-P5..P8. Worth a tracker pass; not this work.

## Open questions

- **OQ-B1 — should D6 escalate rather than fail?** A map that did not collect
  currently ends the run. The factory has gate machinery that could instead ask
  a human to admit a brownfield run without a map. Deferred until real
  repositories show how often D6 fires: designing an override for a failure
  nobody has seen yet is how advisory checks become permanently advisory.
- **OQ-B2 — `IdeaBrief.repo_url` carries a local path.** Every live caller
  passes a directory. Renaming touches the CLI, the benchmark case schema, and
  the dashboard's `types.ts`, so it belongs with E-59's connection work, where
  a real URL first appears.
- **OQ-B3 — hot spots are the weakest projection.** Modules and contracts come
  from S1–S5 with defined semantics; "hot spots" is the spec's word and maps
  onto testability plus coverage records by judgement. If it proves thin in
  practice, SS4's size/duplication outliers are the obvious next source.
