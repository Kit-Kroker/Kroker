# Verified handoff and decorrelated verdict (design)

| | |
|---|---|
| Status | Design — approved in brainstorming 2026-08-05 |
| Roadmap item | New scope. Repairs FR-805 (structured handoff) and E-39 (`deep_review` record path); adds a second review lens and its instrument |
| Design input | `neo4j-labs/ai-governor` @ `dcea697` + the "AI Governor: Quality gates for agentic workflows" Neo4j Live transcript — specifically *validate the executor's self-report against the diff* and *two judges, disagreement triggers rework* |
| Anchors | FR-805 / ADR-13 (task-to-task continuity); ADR-6 / ADR-12 (clean-context validators, model-family inequality); ADR-16 / E-38 (`HarnessSession`); E-36 (heatmap, matrices) |
| Depends on | E-38 (`load_session`, `SessionDigest`), E-39 (advisory-lens precedent), E-37 (`resolve_role_model`, `check_adr6_families`) |

---

## 1. Why now

Two mechanisms in the factory are wired end-to-end and carrying nothing.

**The handoff channel is a constant.** `HandoffSummary` is collected across
tasks (`workflows/feature.py:1801`) and injected into the next dev prompt
(`feature.py:1072-1083`). But the injection reads **only** `open_concerns`, and
`open_concerns` is hardcoded `[]` at `feature.py:1258`:

```python
handoff = HandoffSummary(
    task_id=task.id,
    what_changed=[task.title],      # the task's own title, echoed back
    files_touched=diff["files"],    # populated, never injected anywhere
    open_concerns=[],               # injected — and always empty
)
```

Every downstream task therefore reads `- task-N: no concerns`, on every run,
forever. `decisions_made` is neither populated nor injected. FR-805 and
ADR-13's "fresh session seeded with a structured handoff" are plumbing around
a literal.

**The `deep_review` lens is silently dead.** `QualityScore.judge` is
`Literal["contract","llm_judge","human_override","error","oracle"]`
(`benchmarks/models.py:53`), but `_run_deep_review` passes `judge="deep_review"`
(`feature.py:869`) into `_stage_record`, which feeds it unchecked into
`QualityScore(...)` (`feature.py:507`). That raises `ValidationError`. The
entire `_run_deep_review` body is wrapped in `except Exception: return None`
(`feature.py:882`), so when E-39 is enabled the factory pays for the LLM call,
throws the report away, records nothing, and retains no gotcha. Verified:

```
OK   contract
FAIL deep_review -> ValidationError
FAIL adversary   -> ValidationError
FAIL handoff     -> ValidationError
```

**And the instrument cannot attribute rework.** There is no `stage="review"`
record anywhere — `grep 'stage="review"'` returns nothing; the only reviewer
records are at the merge stage (`feature.py:1979,2037`). The per-task `code`
and `qa` records derive `outcome` from `task_passed` (`feature.py:1224,1245`), which
**excludes** the review verdict. So a review rejection produces two `PASS`
records and a retry, and the heatmap shows `fix_attempts` on `code`/`qa` with
no cause row. The instrument reports that rework happened, never why.

These three are one seam: all are about *the agent's account of its own work
being unverified, unrecorded, or unattributable*.

### Non-goals

- **No graph substrate.** ai-governor's Neo4j audit graph answers questions
  Temporal history + the artifact store already answer; a fourth store is not
  on the table.
- **No agent-requested transitions.** ADR-11 keeps pipeline shape in code.
  Governor's guards exist because the agent asks to transition; ours doesn't.
- **No self-scoring rubric anchoring.** Kroker's judges score *artifacts*
  against rubrics; no agent scores itself, so the "anchor at 85" trick has no
  referent here.
- **No blocking `deep_review`.** It stays advisory (ADR-6/E-39). This spec
  repairs its record path and nothing else about it.
- **No hotspot rollup, no economics arm.** Those are spec B.

---

## 2. Part 1 — the verified handoff

### 2.1 Contract

New in `src/sdlc/models.py`:

```python
class HandoffClaim(BaseModel):
    """One assertion about the work, carrying its evidence. Evidence-first,
    mirroring IntegrityFlag (models.py:399)."""
    text: str
    evidence: str      # quote from the scrubbed HarnessSession
```

`HandoffSummary` becomes:

| Field | Type | Source |
|---|---|---|
| `task_id` | `str` | workflow |
| `files_touched` | `list[str]` | **deterministic** — `diff["files"]` |
| `what_changed` | `list[HandoffClaim]` | extracted |
| `decisions_made` | `list[HandoffClaim]` | extracted |
| `open_concerns` | `list[HandoffClaim]` | extracted |

The split follows one rule: **compute what the diff already states, ask only
for what it cannot.** A diff shows *which* files changed; it does not show why
the author chose cookie sessions over JWT, or what they knowingly left
unfinished.

### 2.2 The extractor

New role `agents/handoff/` — `kind: proposer`, small fast model per
ARCHITECTURE §4 tiering (narrow extraction, not judgment). Built with the
existing `agents/<role>/{agent.py,agent.yaml,instructions.md}` layout.
`handoff` is a Temporal activity name: fixed at creation, never renamed.

Orchestrator-assembled inputs:

- the materialized diff (`diff["patch"]`),
- the scrubbed `HarnessSession`, read via the existing `load_session` activity
  (same call E-39 makes at `feature.py:852`),
- the frozen contract assertions.

It emits every field **except `files_touched`** — the workflow fills that from
`diff["files"]` itself, so the extractor structurally cannot misreport which
files changed.

**Why extraction rather than self-report.** The dev role is a harness, not a
typed proposer, so a structured self-report means either a sentinel block
parsed from free text (format compliance across three adapters) or a file in
the worktree (pollutes the diff validators read). Both produce a
*retrospective* account, which is the most fabricable input there is.
The session is *contemporaneous*: an agent that hit a wall and worked around
it said so mid-run ("I'll skip the empty-list case for now"). Extraction from
the transcript is faithful largely by construction, which is why this design
does not need the separate governor-style verification lens.

### 2.3 Deterministic cross-check

Pure function in `src/sdlc/handoff.py`, no LLM, no I/O, unit-tested directly:

> Any file path appearing in a claim's `text` or `evidence` must be in
> `files_touched`. Violating claims are dropped and counted.

This is the "compute what's in the diff" half doing real work — it catches the
extractor attributing a change to a file the task never touched. The surviving
fraction becomes the handoff's quality score (§4.2).

### 2.4 Invocation and failure behavior

Once per task on the success path, beside `_run_deep_review` at
`feature.py:1252`. **Best-effort**: any failure falls back to today's
mechanical handoff rather than failing a task that passed. A context-and-
observability lens must never fail delivery.

The prompt assembly at `feature.py:1072-1083` is fixed to inject
`what_changed`, `decisions_made` and `open_concerns` — not just the
always-empty `open_concerns` — bounded by the role's declared context budget,
last-5-tasks as today.

### 2.5 The invariant

> The handoff flows to **downstream tasks only**, never to this task's
> validators.

The reviewer stays clean-context on contract + diff + tests (ADR-6/ADR-12).
The extractor reads the dev's session, so routing its output into the reviewer
would correlate the judge with authoring context — the exact hazard E-39's
guardrails exist to prevent. `TaskResult.handoff` is consumed by
`feature.py:1801`'s accumulator and nothing else.

---

## 3. Part 2 — the adversarial second reviewer

### 3.1 Role

New role `agents/adversary/` — `kind: proposer`, `output_type: ReviewReport`.
Reusing the primary's output type means its findings merge into the fix loop
with no new plumbing. `instructions.md` carries a deliberately hostile stance:
assume the diff is incomplete, hunt for contract assertions with no
corresponding change, prefer rejecting.

**Same clean-context inputs as the primary reviewer**: contract assertions +
materialized diff + test output. Deliberately *not* the session — that is
`deep_review`'s job and it stays advisory. Identical information for both
reviewers is what makes disagreement interpretable: it measures family and
persona variance, not information asymmetry.

**Decorrelation is structural — and by model identity, not provider prefix.**

`model_family()` (`agents/loader.py:71-75`) splits on the first `:` or `/`, so
it compares *providers*. Against the shipped registry that check is wrong in
both directions:

| Role | Model | `model_family()` |
|---|---|---|
| `dev` | `zai-coding-plan/glm-5.2` | `zai-coding-plan` |
| `reviewer` | `anthropic:glm-5.2` | `anthropic` |
| `deep_review` | `anthropic:glm-5.2` | `anthropic` |

It **accepts** dev vs reviewer — different prefixes, but the same underlying
`glm-5.2` weights on both sides of the anti-collusion boundary, so ADR-6 is
satisfied nominally and void substantively. And it would **reject**
`anthropic:claude-sonnet-4-6` against `anthropic:glm-5.2` — genuinely
different models sharing a prefix.

So the adversary's constraint compares **model identity** (the segment after
the provider prefix), not the prefix: `model_id(adversary) ∉ {model_id(dev),
model_id(reviewer)}`. This is a new function, `model_id()`, used by a new
check for a new role. `check_adr6_families`'s existing dev/reviewer clause is
deliberately **left untouched** so no existing benchmark baseline shifts.

Enforced at load via `validate_run_roles` and per-cell at benchmark expansion,
where E-37 already validates per run. Persona alone does not break shared
training priors — that is ADR-6's whole argument — so the hostile prompt rides
on top of model inequality, not instead of it.

The adversary ships as `anthropic:claude-sonnet-4-6`: different weights from
both `dev` and `reviewer`, and per ARCHITECTURE §4's tiering table, adversarial
instruction-following is exactly the capability this role needs.

### 3.2 Invocation — the approve-side asymmetry

```python
review_ok = review is None or review.approve
if task_passed and review_ok:          # ← adversary runs only here
```

A rejection is already headed for the fix loop, so a second opinion adds
nothing there. The expensive error is a **false approve**. Running the
adversary only on the approving path halves its cost and points it exactly at
the failure mode that matters.

On split: the attempt fails, and `_fix_loop_issues(qa, qa_raw, review,
adversary)` returns the union of both reviewers' findings to seed the retry.

### 3.3 Bound

Runs on every approving attempt. `max_fix_attempts` is unchanged; exhaustion
lands in the existing accept / retry-with-guidance / quarantine gate, with
both reviewers' findings in the decision card so the human sees precisely what
they disagreed about. No new counter, no new escalation mechanism.

### 3.4 Fail-open, deliberately

A failed adversary call **counts as agreement**. The primary reviewer is the
sole designated blocking lens; a lens added for extra safety must not become a
new way for tasks to fail.

This is deliberately asymmetric to the E-38 scrub, which is fail-*closed*: a
leaked credential in a stored transcript is unrecoverable, a missed second
opinion is not. Both asymmetries are correct and the spec states both so
neither is later "fixed" into the other.

### 3.5 Configuration

`PipelineConfig.adversarial_review_enabled: bool = False`, mirroring
`deep_review_enabled`. Off by default: it changes hot-path outcomes and costs
money. Default-off is also what lets spec B sweep it as a benchmark **arm** —
on vs off, compared on held-out oracle pass-fraction against cost.

---

## 4. Part 3 — repairing and extending the instrument

### 4.1 The `judge` Literal

`QualityScore.judge` gains `"deep_review"`, `"adversary"`, `"handoff"`. This
is the fix for the §1 bug, and it is a prerequisite: without it both new
lenses die exactly as `deep_review` did — silently, inside a bare
`except Exception`.

**Companion hardening:** `_run_deep_review`'s blanket `except Exception:
return None` is what turned a contract violation into a silent no-op. The
handler stays (a lens must not fail delivery) but logs at warning with the
exception, so the next such bug is visible in one run rather than invisible
forever. The same handler shape is used for the handoff extractor and the
adversary.

### 4.2 New records

| Stage | Emitted when | `outcome` | `judge` | `score` | `fix_attempts` |
|---|---|---|---|---|---|
| `review` | every review call | `PASS`/`FAIL` on `approve` | `contract` | 1.0 approve / 0.0 reject | **0** |
| `adversary` | every approving attempt | `PASS` agree / `FAIL` split | `adversary` | 1.0 / 0.0 | **0** |
| `handoff` | once per task, success path | `PASS`, or `FAIL` on extractor failure | `contract` | fraction of claims surviving §2.3 | **0** |

The **missing `review` record is a prerequisite, not scope creep**:
disagreement is a *relation between two records*, so an adversary record
without the primary's is uninterpretable.

### 4.3 Why cause rows carry `fix_attempts=0`

`heatmap.py` accumulates two distinct things per `(case, stage)`:
`gate_rejects` (*why* rework happened) and `fix_attempts` (*how much*). Every
record contributes its `fix_attempts` to its own stage row
(`heatmap.py:75`).

If adversary records carried `fix_attempts` the way `code`/`qa` records do,
**one split would count three times**: `gate_rejects+1` on the adversary row,
plus `fix_attempts+1` on each of the `code` and `qa` rows for the following
attempt — inflating density by 3 for one disagreement and attributing it to
two stages that did not fail. That is the same double-count the `ORACLE_TASK`
exclusion at `heatmap.py:57-66` already guards against.

Emitting cause rows with `fix_attempts=0` keeps exactly one cause row per
event and leaves retry volume where it belongs, on `code`/`qa`. **No change to
`heatmap.py` is required** — this is discipline in what the workflow passes.

`CANONICAL_STAGES` (`heatmap.py:18`) gains `review`, `adversary` and
`handoff` so they render in DAG order rather than the trailing unknown bucket
where `deep_review` sits today.

### 4.4 `agreement_matrix.py`

Agreement is not rework density and does not belong in the heatmap. It gets
its own grid, modeled directly on `waste_matrix.py` — the E-36 precedent for
exactly this move (a task × arm matrix rather than a heatmap column):

- rows: `task_id`; columns: `harness#model` arm; per BENCHMARK.md matrix idiom
- cells: **split rate** (`adversary` records with `outcome=FAIL` ÷ all
  `adversary` records for that task+arm) and **cost per split** (summed
  `cost.usd` of all `adversary` records ÷ number of splits — what one
  disagreement costs to surface)
- a record with no adversary contributes nothing — it was not measured, and a
  zero cell would claim it was (`waste_matrix.py:7-10`'s rule)

**What this matrix deliberately cannot tell you** is whether the adversary was
*right*. Split rate is descriptive. "Was the extra call worth it" is a
counterfactual answerable only by running a case with
`adversarial_review_enabled` on and off and comparing held-out oracle
pass-fraction against cost — spec B's arm sweep. The matrix stays descriptive
by design; the verdict lives in the arm comparison.

---

## 5. Testing

**Unit (no Temporal, no model calls):**

- §2.3 path cross-check: claims naming files outside the diff are dropped; the
  surviving fraction is the score.
- `_fix_loop_issues` union: both reviewers' findings reach the retry prompt;
  `adversary=None` reproduces today's output byte-for-byte.
- three-way `check_adr6_families`: rejects adversary sharing a family with
  either `dev` or `reviewer`.
- `QualityScore(judge=...)` accepts every value the workflow emits — a
  regression test for the §1 bug, asserted over the literal set the workflow
  uses rather than a hand-copied list.
- `build_agreement_matrix`: records without adversary contribute no cell.

**Workflow (time-skipping):**

- adversary splits → task retries with merged findings.
- adversary splits on every attempt → escalation gate fires with both
  findings in the decision card.
- adversary call raises → treated as agreement, task passes (§3.4).
- `adversarial_review_enabled=False` → behavior identical to today.
- handoff extractor raises → mechanical handoff, task still passes.
- handoff content reaches the *next* task's prompt and reaches no validator.

**Fakes:** existing `fake_harness` plus injectable fake agents, as E-39 does.

---

## 6. Migration

`HandoffSummary`'s field types change from `list[str]` to
`list[HandoffClaim]`. Pydantic-converted Temporal history for **in-flight
runs** will fail to deserialize.

Resolution: **drain runs before deploy.** The alternative — additive fields
plus a deprecated one — carries the dead field indefinitely to protect runs
that are hours old. Draining is the honest cost and it is stated here so it is
not discovered at deploy time.

---

## 7. Open questions

- **OQ-A1** — Should `handoff` extraction also run on the *failure* path, so a
  quarantined task's open concerns reach its dependents? Currently success-only.
  Deferred: dependents of a quarantined task are blocked anyway (ARCHITECTURE
  §11), so the value is limited to the escalation decision card.
- **OQ-A2** — Cost ceiling for the adversary is `max_fix_attempts` calls per
  task in the worst case. If the observed split rate is high, §3.3's "every
  approving attempt" may want the reduced-budget variant (a separate, smaller
  counter). Deferred until spec B measures the rate — the data does not exist yet.
- **OQ-A3** — `deep_review` and `adversary` are both non-DAG lenses now living
  in `CANONICAL_STAGES`. If more accumulate, the heatmap's stage axis stops
  being the SDLC DAG. Revisit at the third such lens.
- **OQ-A4 (raised by this spec, deliberately out of its scope)** — `dev` and
  `reviewer` currently run **the same model**, `glm-5.2`, behind different
  provider prefixes (§3.1). ADR-6's anti-collusion invariant is therefore
  enforced structurally and satisfied vacuously in the shipped registry: the
  judge shares every weight, and every failure mode, with the author. Fixing it
  means moving `reviewer` off `glm-5.2` and strengthening `model_family` to
  compare model identity everywhere — which invalidates every existing
  benchmark baseline, since past numbers were produced under the vacuous
  pairing. That trade is a standalone decision and is **not** taken here.
  `deep_review` has the same defect for the same reason.
