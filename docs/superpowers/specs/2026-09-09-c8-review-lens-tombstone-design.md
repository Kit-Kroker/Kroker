# C8 — Lens-absence tombstones for the review lenses

**Date:** 2026-09-09
**Register row:** C8 (`docs/reports/external-ideas-2026-09.md:67`) — "A lens that
did not run is indistinguishable from a lens that approved"
**Filed by:** `docs/reports/2026-09-06-advisory-deterministic-pairing-audit.md`
(Row 2 and Row 3 of the pairing census)
**Branch:** `c8-review-lens-tombstone`
**Status:** **approved** at the user gate, 2026-09-10, with the five rulings
recorded in §8. Reviewed twice (`.workspace/tmp/reviewer-1.md` fixes-needed →
`.workspace/tmp/reviewer-2.md` approve); the second pass's advisory A1 is
folded into the OQ2 ruling. Implementation plan:
`docs/superpowers/plans/2026-09-10-c8-review-lens-tombstone.md`.

Sibling row C7 (nothing stands behind self-reported confidence) is context only
and is deliberately **not** absorbed here.

---

## 1. The defect

Three of the review stage's fail-open legs return `None`, and every consumer of
that `None` reads it as approval. There is no record anywhere that the lens did
not run, so "the reviewer approved" and "the reviewer was never wired up" are
bit-identical downstream.

This is C3's hole one layer up. C3 closed it at the merge gate — a required
check absent from the gate input is synthesized as a *failing* `MISCONFIGURED`
check (`src/sdlc/gate.py:122-139`). The C3 fix cannot reach these lenses,
because the review lenses never travel through `evaluate_quality_gate`.

### 1.1 Anchors, verified against the tree at `6a941fc`

Every line below was read, not inherited from the register.

| Site | Behaviour |
|---|---|
| `src/sdlc/stages/review/step.py:114-115` | primary reviewer returns `None` when `cfg.review_enabled` is false **or** `reviewer_agent is None` |
| `src/sdlc/stages/review/step.py:185-186` | adversary returns `None` when `adversarial_review_enabled` is false **or** `adversary_agent is None` |
| `src/sdlc/stages/review/step.py:234-240` | adversary returns `None` on **any** exception, logging a warning ("treating as agreement") |
| `src/sdlc/stages/code/step.py:335` | a **duplicate** copy of the adversary pre-check, in the code slice's wrapper |
| `src/sdlc/stages/code/step.py:798` | `review_ok = review is None or review.approve` — absence read as approval |
| `src/sdlc/stages/code/step.py:802` | `if review is not None:` — the adversary runs **only** when the primary produced a report |
| `src/sdlc/stages/code/step.py:813` | `if adversary is None or adversary.approve or ...` — absence read as agreement, guards the `done` return at `:827` |
| `src/sdlc/stages/merge/step.py:325` | `all(r.review is None or r.review.approve for r in results_list)` — the **same** `None`-as-approval read, one layer up, inside the `review_severity` ADVISORY check |

Two corrections to the brief this design started from:

- The C3 manifest lives in **`src/sdlc/gate.py:86`** (`MERGE_REQUIRED_CHECKS`),
  not in `merge/step.py`. `merge/step.py` only builds the input list. A
  merge-layer C8 change therefore touches `gate.py` plus one check builder, not
  the gate plumbing.
- The primary reviewer has **no** `try/except`, and neither does its call site
  (`code/step.py:736`); `_run_role` (`workflows/role_host.py:133-176`) does not
  swallow agent exceptions either. A primary that *raises* therefore fails the
  workflow loudly — it is not a fail-open leg. The primary's absence modes are
  exactly two: flag off, and no agent.

### 1.2 Two findings the register did not name

**The absence rule is quintuplicated.** The same "should this lens run?"
predicate is written out five times: `review/step.py:114`, `:185`, `:263-269`
(deep review), `code/step.py:335`, and `workflows/task_host.py:321`. Any
tombstone derived independently of the predicate that gated the run can drift
out of sync with it, which would reintroduce the defect in a subtler form.

**`TaskHost._run_adversary` and `_run_deep_review` are dead.** Defined at
`workflows/task_host.py:311` and `:335`, they have no call sites — `_dev_task`
(`:261`) delegates to `code.step`, which carries its own wrappers. They are two
of the five copies above, and they are vestigial. Deleting them was ruled in
scope at the user gate — see §3.6b and ruling OQ4.

**The compound failure.** Because `code/step.py:802` runs the adversary only
`if review is not None`, turning the primary off silently disarms the backstop
lens too. The configuration "no primary, adversary only" — the one arrangement
where the adversary is the *sole* remaining lens — runs no lens at all.

### 1.3 The constraint the register did not account for

The register's candidate shape is "an explicit absence tombstone that the
task's success condition must see". That phrasing implies the tombstone
*blocks*. The repo has a written, binding contract pointing the other way:

- `src/sdlc/stages/review/review.md` **REVIEW-1.3**: the adversary lens
  "operat[es] fail-open to ensure safety checks never fail task delivery".
- `src/sdlc/stages/review/AGENTS.md` invariant: "Lenses are fail-open: safety
  lenses must never fail task delivery."
- `run_adversary`'s docstring (`review/step.py:179-183`): "a lens added for
  safety must not become a new way to fail", stated as a deliberate asymmetry
  against the fail-closed E-38 scrub.

C8's title is about **indistinguishability**, not about blocking. This design
separates the two and closes the first without silently overturning the second.

---

## 2. Approaches considered

**A — Sentinel report.** Return a synthesized non-approving `ReviewReport`
carrying a marker instead of `None`. Smallest diff. **Rejected:** it conflates
"did not run" with "rejected", pushing infrastructure failures into the fix
loop, where an implementer agent is asked to repair a crashed lens it cannot
see.

**B — Merge-layer only.** Leave the task loop untouched; add a lens-presence
check to `MERGE_REQUIRED_CHECKS` and let C3's machinery do the rest.
**Rejected as insufficient alone:** the register is explicit that the task's
success condition must see the absence, and the merge check can only grade
evidence the task layer actually produced.

**C — Typed lens outcome, produced once, graded twice (recommended).** Each
lens yields a typed `LensOutcome` with a presence enum, produced by a single
pure classifier. The outcome travels in `TaskResult` and is read explicitly by
the task success condition (restoring distinguishability) and graded as a
required ADVISORY check at the merge gate (restoring enforcement, via C3's
audited-override route).

The advisor seat recommended C's bite-points independently; see §7.

---

## 3. Design

### 3.1 The tombstone type

New module `src/sdlc/stages/review/lenses.py` — pure, no `ctx`, no I/O,
table-testable. This mirrors the shipped precedent of `code/freeze.py`, which
holds C2's decision rules as pure functions re-exported by `step.py`.

The shape mirrors `Measurement` / `CollectionState` (`src/sdlc/measurement.py:23-45`),
the repo's existing idiom for "a value we may not have, with the reason we do
not have it", already consumed by coverage and security at the merge gate.

```python
GATING_LENSES: Final[frozenset[str]] = frozenset({"reviewer", "adversary"})

class LensPresence(StrEnum):
    PRESENT = "present"                       # ran, produced a report
    DECLARED_ABSENT = "declared_absent"       # operator turned the flag off
    NOT_REACHED = "not_reached"               # enabled, but its run site was never reached
    UNDECLARED_ABSENT = "undeclared_absent"   # enabled and reached, but the wiring broke

class LensOutcome(BaseModel):
    lens: str                            # a name in GATING_LENSES
    presence: LensPresence
    approved: bool | None = None         # meaningful only when PRESENT
    has_blocking_findings: bool = False  # meaningful only when PRESENT
    reason: str = ""                     # human-facing detail
```

A `model_validator(mode="after")`, mirroring `Measurement._value_matches_state`,
enforces the invariant that is the whole point of the row:

- `PRESENT` requires `approved is not None`.
- **All three** absent states — `DECLARED_ABSENT`, `NOT_REACHED`,
  `UNDECLARED_ABSENT` — require `approved is None` **and** a non-empty
  `reason`.

An absent outcome that claims approval is therefore not merely discouraged —
it is unconstructible.

**`NOT_REACHED` — the fourth value (user-gate ruling OQ2, from reviewer A1).**
The primary runs on every attempt (`code/step.py:736`, before `task_passed` is
computed at `:750`), but the adversary's run site sits inside the approving
block (`:801`). On the post-gate return (`:899` — every quarantined task, and
every operator-approved budget-exhausted one) an adversary-enabled task never
reaches its run site at all. Without a fourth value that geometry classifies as
`UNDECLARED_ABSENT`, and routine pipeline shape becomes indistinguishable from
broken wiring — the very conflation this row exists to end, reintroduced inside
the fix. `NOT_REACHED` keeps `UNDECLARED_ABSENT` meaning *exactly* "enabled,
reached, and the wiring broke". It is tombstoned and visible, and it does not
fail the merge check (§3.5).

**The lens manifest.** `GATING_LENSES` is the authoritative list of lenses
whose presence is graded — the same role `MERGE_REQUIRED_CHECKS` plays for
checks, one layer down. It holds exactly the two lenses that participate in the
task success condition; `deep_review` is deliberately excluded (§3.6). The merge
check of §3.5 iterates this set, so a lens that stops emitting an outcome fails
rather than disappears. OQ2 is a question about how this set is graded, not
about its membership.

**Facts, not verdicts.** The outcome carries what the lens observed; it does
**not** carry a single pre-computed "blocking" boolean. The two lenses apply
genuinely different admission rules today (§3.4), and folding them into one
field is exactly how F2's silent semantic change entered the first draft.

**Three states, not two.** The declared/undeclared split is structural rather
than a substring of `reason`, because the two cases justify different things:
fail-open is a defence only for the undeclared case (a transient failure should
not fail delivery), while the declared case is an operator decision that must
still not be silent. Downstream consumers branch on the enum; `reason` stays
human-facing. `enabled-but-agent-missing` classifies as **undeclared** — the
operator asked for the lens and the wiring did not deliver it.

### 3.2 One producer

```python
def classify_lens(
    lens: str,
    *,
    enabled: bool,
    agent_present: bool,
    reached: bool,
    report: ReviewReport | None,
) -> LensOutcome
```

Pure, derived from exactly the facts the existing pre-checks consult plus one
the call site already knows — whether control reached the lens's run site — so
the tombstone cannot disagree with the predicate that gated the run. `reached`
is a plain caller-supplied boolean, not an inspection of control flow: the
primary's call site passes `True` unconditionally (it always runs), and the
adversary's passes whether the approving block was entered. The classifier
stays pure.

**Classification order, and why.**

| `enabled` | `agent_present` | `reached` | `report` | → |
|---|---|---|---|---|
| `False` | — | — | — | `DECLARED_ABSENT` |
| `True` | `False` | — | — | `UNDECLARED_ABSENT` |
| `True` | `True` | `False` | `None` | `NOT_REACHED` |
| `True` | `True` | `True` | `None` | `UNDECLARED_ABSENT` |
| `True` | `True` | `True` | report | `PRESENT` |

Two ordering decisions carry reasoning rather than convention:

- **`enabled` is checked first.** When the operator has turned the lens off,
  that declaration is the truthful cause; path geometry and wiring are moot.
- **`agent_present` is checked before `reached`.** A missing agent on an
  enabled lens is a real misconfiguration, and it is observable whether or not
  the run site was reached (the agent is a parameter of `code.step`).
  Suppressing it behind `NOT_REACHED` would hide a genuine wiring defect on
  exactly the runs — quarantined ones — where knowing the lens coverage matters
  most.

`reached=False` with a non-`None` report is incoherent and is rejected by the
classifier rather than silently normalized.

To keep that guarantee real, the duplicated pre-checks are **collapsed**:
`code/step.py:335`'s copy is deleted (the runner at `review/step.py:185`
already holds it), leaving one gate on running and one classifier on the
outcome. This dedup is not hygiene here; it is the mechanism. (The advisor
rated the dedup hygiene-only; §7 records that divergence.)

**Residual: the guarantee holds at construction, not forever.** "The tombstone
cannot disagree with the predicate that gated the run" is true only while the
classifier is invoked with the runner's own predicate facts. If someone later
widens the runner's predicate without widening the call site, the two can drift
— the §1.2 failure, one layer down. Test 11 (§4) pins the invocation.

Accepted trade: `classify_lens` cannot distinguish "the adversary raised" from
"the adversary returned no report" — both are `enabled and agent_present and
report is None`, both `UNDECLARED_ABSENT`. The traceback survives in the
existing warning log (`review/step.py:234-240`). Deriving presence from
observable facts rather than from a flag the runner sets is what makes the
tombstone unforgeable; the lost granularity is the price and it is small.

### 3.3 Where it travels

`TaskResult` (`src/sdlc/workflows/models.py:52`) gains:

```python
lens_outcomes: list[LensOutcome] = Field(default_factory=list)
```

Populated on **every** return path out of `code.step`. There are exactly **two
`TaskResult` return sites carrying three statuses**: `:827` (the `done` return)
and `:899` (the post-gate return, which yields `done` or `quarantined`
depending on the operator's decision). Both must be populated.

An empty list must never read as "all lenses fine"; §3.5 makes an empty list
fail the merge check, which also covers `TaskResult`s built by producers that
predate the field — including in-flight workflows crossing a deploy, which land
on the failing side, the correct side to fail on.

### 3.4 Where it bites — the task success condition

`code/step.py:798` and `:813` stop reading `None` and start reading the
outcome. The two admission rules become two pure predicates in `lenses.py`:

```python
def primary_admits(o: LensOutcome) -> bool:
    return o.presence is not LensPresence.PRESENT or bool(o.approved)

def backstop_admits(o: LensOutcome) -> bool:
    return (
        o.presence is not LensPresence.PRESENT
        or bool(o.approved)
        or not o.has_blocking_findings
    )
```

**Behaviour is preserved exactly.** `primary_admits` is a transcription of
today's `review is None or review.approve` (`:798`); `backstop_admits` is a
transcription of today's `adversary is None or adversary.approve or not
adversary.blocking_findings` (`:813`). The asymmetry between them — any primary
rejection fails the done path, but only a *blocking* adversary rejection does —
is today's shipped behaviour, and this design keeps it deliberately rather than
inheriting it by accident.

#### The `review_ok` truth table (pinned)

| Primary outcome | `primary_admits` | Today's `:798` | Same? |
|---|---|---|---|
| `PRESENT`, `approved=True` | admits | admits | ✓ |
| `PRESENT`, `approved=False`, blocking findings | **fails** | fails | ✓ |
| `PRESENT`, `approved=False`, **no** blocking findings | **fails** | fails | ✓ |
| `DECLARED_ABSENT` | admits | admits (`None`) | ✓ |
| `NOT_REACHED` | admits | admits (`None`) | ✓ |
| `UNDECLARED_ABSENT` | admits | admits (`None`) | ✓ |

Both predicates test `presence is not PRESENT`, so all three absent states
admit identically — the fourth value changes what the tombstone *says*, never
what the task layer *does*. Per the OQ1 ruling the task layer stays
non-blocking in every presence state.

Row 3 is the cell F2 caught: the first draft expressed both guards over a
single `blocking` field, which would have flipped a PRESENT primary rejecting
with an empty `blocking_findings` list from fix-loop to `done`, surfacing only
as a waivable merge advisory. That contradicts the pin at
`tests/review/test_review_wiring.py:49-53` ("the task success path must require
reviewer approval when review ran"). **This design adopts the faithful reading:
C8's charter is absence, and the change is absence-only.**

*Considered and rejected — harmonization.* Making the primary blocking-only
too, so both lenses share one rule, is tidier and would let `LensOutcome` carry
a single `blocking` field. Rejected: it is a substantive loosening of the
primary's admission bar smuggled in under a row about tombstones, it needs its
own evidence about whether non-blocking rejections should ship, and it would
require amending a pin that states the opposite. If it is wanted, it is its own
register row.

What *does* change is that absence is no longer *spelled the same as* approval.
The success condition consumes a typed presence value; there is no expression
in it that maps `None` to "approved". That is the distinguishability C8 asks
for, delivered without overturning REVIEW-1.3. Whether the tombstone should
also *block* at this layer was the question this design routed to the user;
ruling OQ1 (§8) settled it as **merge gate only**, so the task layer stays
non-blocking as written here.

#### The `:802` compound guard is deleted — and this overrides a pinned decision

The adversary runs on `task_passed and review_ok` alone.

This is not dead-code removal. `tests/review/test_adversary_workflow.py:185-198`
(`test_adversary_never_runs_without_a_primary_reviewer`) asserts the guard's
source text is present and records the rationale in its docstring: *"The
adversary is a SECOND opinion; it presupposes a first. When review is disabled
(review is None) it must not run — the primary reviewer is the sole designated
blocking lens, which is the justification for this lens being fail-open."* That
is a deliberate design position from the 2026-08-05 verified-handoff work, and
this design overrides it. Calling the guard "redundant", as the first draft
did, was wrong: the guard is doing exactly the suppressing work that the
audit's Row 2 names, and under C8's reading that work **is** the bug.

The rebuttal, taking the pinned rationale on its own terms:

1. **Decorrelation does not require a first opinion to exist.** The adversary's
   value comes from an independent read of the same three inputs — contract
   assertions, diff, deterministic test output — which is why `run_adversary`
   is given inputs identical to the primary's (`review/step.py:187-194`). With
   no primary, that read is not less valid; it is merely unpaired. "Second
   opinion" describes its *role in the pipeline order*, not a precondition for
   its output being meaningful.
2. **The fail-open justification survives untouched.** The docstring's argument
   is about what happens when the adversary *fails*: it must not become a new
   way to fail delivery. That argument does not depend on the primary having
   *run*; it depends on the adversary not being the designated blocking lens,
   which remains true. Under this design the adversary stays fail-open in every
   presence state.
3. **"No primary, adversary only" must run some lens.** Today that
   configuration runs *none* — the operator has explicitly enabled a lens that
   silently does not execute. That is C8's own defect, reproduced in a guard
   rather than in a `None`-read, and leaving it in place while fixing the
   `None`-reads would ship an incoherent row.
4. **No operator gets a surprise adversary.** `adversarial_review_enabled`
   defaults to `False` (`core/models.py:386`), so "primary off, adversary on"
   remains an explicit two-flag opt-in. The cost objection behind the original
   position — an operator who disabled review to save money
   (`core/models.py:381-383`) — is answered by the adversary's own flag, which
   that operator has not set.

**In scope:** amending `test_adversary_never_runs_without_a_primary_reviewer`
— replacing the source assertion and rewriting its docstring to record the
reversal and this rationale, so the next reader finds the argument rather than
an orphaned deletion.

### 3.5 Where it bites — the merge gate

Two checks, deliberately kept apart:

- **`review_lenses_present`** (new, ADVISORY, added to `MERGE_REQUIRED_CHECKS`
  in `gate.py:86`). **One uniform check covering both lenses** (ruling OQ3);
  the detail names the lens and its presence state. Its grading rule, per
  ruling OQ2, is:

  > For every task result and every name in `GATING_LENSES`: **fail** if that
  > lens has **no outcome recorded at all**, or an outcome whose presence is
  > `UNDECLARED_ABSENT`. `PRESENT`, `DECLARED_ABSENT`, and `NOT_REACHED` all
  > pass — and all three are named in the detail regardless.

  The **no-outcome-recorded** clause is what preserves the empty-list defense
  under a fail-only-on-`UNDECLARED_ABSENT` rule: a `TaskResult` with
  `lens_outcomes=[]` — a producer that predates the field, an in-flight
  workflow crossing a deploy — has no `UNDECLARED_ABSENT` entry to trip on, so
  without this clause it would sail through. A missing tombstone is graded as
  severely as a broken one. Test 7 (§4) pins it.

  Passing on `DECLARED_ABSENT` and `NOT_REACHED` while still printing them is
  the point of the ruling: the operator's declaration and the pipeline's shape
  are honoured, absence is still never silent, and a failing check now means
  one specific thing — a lens that was asked for, was reached, and did not
  deliver.
- **`review_severity`** (`merge/step.py:325`, existing). Its `r.review is None
  or r.review.approve` read is replaced by one that grades **only `PRESENT`
  lenses**, applying `primary_admits` (§3.4) so the merge check and the task
  success condition cannot diverge on what "approved" means. Absence is no
  longer approval here; it is simply not this check's question.

They stay separate because they answer different questions — "did the lens
run?" versus "did it approve?" — and because a single audited `GateOverride`
should not waive both at once.

**ADVISORY, not ABSOLUTE.** An ABSOLUTE lens-presence check would make a
config-off lens terminally block the merge with no override available, which
deletes the configuration flag by force. ADVISORY preserves operator intent
(the human who turned the lens off can waive the check) while making the waiver
audited rather than silent. Adding the name to `MERGE_REQUIRED_CHECKS` means
C3's `_synthesized` also covers the case where the producer stops emitting the
check at all.

### 3.6 Scope: `deep_review` is excluded

The audit classified `deep_review` as FILTERED — post-decision at both call
sites (`code/step.py:814`, `:896`), never in the success condition, as its own
docstring requires. It gates nothing, so its absence cannot be read as
approval. Giving it a tombstone would be scope creep, and it is excluded from
`GATING_LENSES`. Its pre-check (the predicate at `review/step.py:263-269`) is
left alone.

### 3.6b The dead `TaskHost` twins are deleted (ruling OQ4)

`TaskHost._run_adversary` (`workflows/task_host.py:311`) and
`_run_deep_review` (`:335`) have no call sites — `_dev_task` (`:261`) delegates
to `code.step`, which carries its own wrappers. They are two of the five copies
of the absence predicate (§1.2). With the dedup elevated to the mechanism
(§3.2), leaving two unreachable copies of the rule the design is trying to
make single-sourced would undercut it, so the user gate ruled them in scope.

Consequence the plan must carry: `tests/review/`'s source-concatenation
assertions read `task_host.py` *before* `code/step.py`, so deleting the twins
changes which text their `find()` calls land on. §4.1 names the specific tests.

### 3.7 Contract deltas

Clause numbers verified free at `6a941fc`: `review.md` tops out at REVIEW-1.5,
`code.md` at CODE-1.5. `merge.md` runs to **MERGE-1.7, which is taken** by
`plan_drift` (E4, `merge.md:29-30`) — hence MERGE-1.8 below.

- `src/sdlc/stages/review/review.md` — new **REVIEW-1.6**: every lens in
  `GATING_LENSES` yields a `LensOutcome`; absence is typed and carries a
  reason; fail-open at the task layer is preserved and now explicit. Amend the
  "Failure modes" entries for primary and adversary to name the tombstone. The
  primary's entry (`review.md:36`) additionally needs a **correctness** fix:
  "If review fails or is disabled … returns `None`" overstates the fail-open —
  §1.1 establishes that a raising primary propagates. The amendment corrects
  the wording to the two real absence modes.
- `src/sdlc/stages/merge/merge.md` — new **MERGE-1.8**, mirroring MERGE-1.6:
  lens presence is a required ADVISORY check over `GATING_LENSES`, graded by
  the §3.5 rule — a missing or `UNDECLARED_ABSENT` outcome is an advisory
  failure reaching the human gate with its reason, waivable by audited
  override, while `DECLARED_ABSENT` and `NOT_REACHED` pass and are still
  reported in the detail. The clause must state the grading rule explicitly,
  since "required check" here means *the check must be produced*, not *every
  lens must have run*. Also
  add `review_lenses_present` to MERGE-1.3's advisory-check enumeration
  (`merge.md:17`), alongside `review_severity`, `traceability`, `coverage`,
  and `plan_drift`.
- `src/sdlc/stages/code/code.md` — new **CODE-1.6**: `TaskResult` carries lens
  outcomes on every return path.
- `src/sdlc/stages/review/AGENTS.md` — extend the fail-open invariant line:
  fail-open at the task layer, never silent, always tombstoned.
- `src/sdlc/gate.py:80-85` — extend the `MERGE_REQUIRED_CHECKS` comment to
  cover the new entry.

No amendment weakens the fail-open invariant; REVIEW-1.3 stands as written.

---

## 4. Testing strategy

TDD per repo convention; each bullet is a failing test first.

**Pure, table-driven (`tests/review/`):**
1. `classify_lens` truth table over `enabled × agent_present × reached ×
   report` → the expected `LensPresence` for every cell of §3.2's table,
   including both ordering decisions (flag-off-and-unreached →
   `DECLARED_ABSENT`; enabled-agent-missing-and-unreached →
   `UNDECLARED_ABSENT`) and the rejection of `reached=False` with a report.
2. `LensOutcome` validator rejects absent-and-approved and absent-without-reason
   for **all three** absent states, and present-without-`approved`.

2b. `primary_admits` / `backstop_admits` over the §3.4 truth table, including
   the **`PRESENT`, `approved=False`, no blocking findings** cell for the
   primary — the one place F2's semantic change could reappear silently.

**Task layer (`tests/code/`):**
3. Adversary raises → `UNDECLARED_ABSENT` recorded, task still returns `done`
   (the fail-open invariant, now under test rather than merely documented).
4. `adversarial_review_enabled=False` → `DECLARED_ABSENT`, task returns `done`.
5. `review_enabled=False` **and** adversary enabled → the adversary **runs**
   (regression test for the `:802` compound bug).
5b. Primary `DECLARED_ABSENT` **and** adversary `PRESENT` rejecting with
   blocking findings → **not** `done`; routes to the fix loop. Test 5 pins that
   the adversary runs on the new path; this pins that its rejection still
   bites there.
5c. A task returning through the post-gate site (`:899` — quarantined, or
   budget-exhausted) with the adversary **enabled** yields `NOT_REACHED`, not
   `UNDECLARED_ABSENT`. This is the A1 case; it is the cell that keeps
   `UNDECLARED_ABSENT` meaningful.
6. Both `TaskResult` return sites (`:827`, `:899`) — across all three statuses
   — carry a non-empty `lens_outcomes`.

**Merge layer (`tests/merge/`):**
7. A `TaskResult` with `lens_outcomes=[]` fails `review_lenses_present` (the
   no-outcome-recorded clause of §3.5 — the empty-list defense under a
   fail-only-on-`UNDECLARED_ABSENT` rule).
8. `UNDECLARED_ABSENT` fails `review_lenses_present`, and an audited
   `GateOverride` waives it.
8b. `DECLARED_ABSENT` **passes** the check and still appears in its detail.
8c. `NOT_REACHED` **passes** the check and still appears in its detail.
9. An absent lens no longer passes `review_severity` by absence, and a
   `PRESENT`-and-rejecting lens still fails it.
10. Dropping `review_lenses_present` from the gate input synthesizes the C3
    `MISCONFIGURED` failure (manifest wiring is live).

**Mechanism (`tests/review/`):**
11. `classify_lens` is invoked with the runner's own predicate facts — a
    source-assertion pin in the repo's established style (§3.2's residual).

### 4.1 Existing pins this change breaks — amendments in scope

Named here so the implementation plan budgets for them, and so the empty-list
defense cannot be quietly weakened under pressure to go green. Each is an
amendment with a stated reason, never a deletion.

| Pin | What it asserts | Amendment |
|---|---|---|
| `tests/review/test_review_wiring.py:51` | `"review is None or review.approve" in src` | update to the `primary_admits` form; semantics preserved per §3.4, so only the source text changes |
| `tests/review/test_review_wiring.py:75` | `"r.review is None or r.review.approve" in block` | update to the `PRESENT`-only merge form (§3.5) |
| `tests/review/test_adversary_workflow.py:196` | `"review is not None" in src[pred:call]` | **reversed** per §3.4; assertion replaced and docstring rewritten to record the reversal and its rationale |
| `tests/review/test_adversary_workflow.py:106-112` (`test_adversary_is_fail_open`) | `"return None" in` the body after the **first** `async def _run_adversary` in the concatenation | breaks by side effect, not by intent — see below |

These are **source-concatenation assertions**: `test_review_wiring.py`'s `SRC`
and `test_adversary_workflow.py`'s `_src()` read `feature.py` + `task_host.py`
+ `review/step.py` (+ `merge/step.py`, in `test_review_wiring.py` only) +
`code/step.py` as one string. Two consequences the plan must carry: the
amendments are textual, not behavioural; and because §3.6b deletes the
`task_host.py` twins, the concatenation shrinks — every `find()`-based offset
must be re-checked against the new string.

**The specific case that re-check must catch (reviewer note P1).**
`test_adversary_is_fail_open` locates the first `async def _run_adversary` in
the concatenation and asserts `return None` appears in the following 2600
characters. Today that first match is the dead `task_host.py:311` twin, whose
pre-check contains `return None`. After §3.6b deletes the twins **and** §3.2
collapses `code/step.py:335`'s duplicate pre-check, the first match becomes the
live `code/step.py` wrapper, which may no longer contain `return None` at all —
so this test fails for a reason unrelated to fail-open behaviour, which
genuinely still holds (it lives in `run_adversary` at `review/step.py:186`,
`:240`). The amendment retargets the assertion at the runner that actually
implements fail-open; it must not be "fixed" by reinstating a pre-check the
design deliberately removed.

**Merge fixture blast radius.** These construct `TaskResult` without
`lens_outcomes` and will fail `review_lenses_present` on landing (test 7 is
exactly why). Each needs outcomes added, not the check relaxed:
`tests/merge/test_merge_slice_contract.py:112, :171, :247, :291`;
`tests/merge/test_merge_gate_wiring.py:97-117`;
`tests/merge/test_plan_drift_gate.py:24, :119`.

---

## 5. Out of scope

- C7 (confidence calibration) — the sibling row, untouched.
- `deep_review` tombstones (§3.6).
- The wrong-yes direction of any lens: nothing here makes a *bad* approval
  more detectable. C8 is about absence only.
- **Harmonizing the two admission rules** so the primary, like the adversary,
  fails only on blocking findings — considered and rejected in §3.4 as a
  substantive loosening that belongs to its own row.
- **Lens-outcome records in the benchmark corpus** — ruled a separate row at
  the user gate (OQ5). The same defect lives there: both lenses emit a stage
  record only when they run (`review/step.py:204-222` adversary,
  `:136-154` reviewer — reviewer note P2 widened this from the adversary alone).
  The proposal is filed at
  `.workspace/tasks/2026-09-10-benchmark-lens-outcome-records.md`; per protocol
  the register row itself is added by the user. **This work does not touch
  `benchmarks/`.**
- `workflows/feature.py:340`'s handoff twin, recorded by the audit as found but
  unresolved — a different row.

---

## 6. Risks

- **Blast radius on `TaskResult`.** A new field on a Temporal-visible model
  touches the passthrough set named in `code/AGENTS.md` (`workflows/models.py`).
  Mitigated by a defaulted field, but the implementation plan must confirm no
  running-workflow deserialization path breaks.
- **Deleting the dead twins shifts source-assertion offsets.** §3.6b's deletion
  is behaviourally inert but textually disruptive to `tests/review/`'s
  concatenation-based pins. §4.1 names the specific failure this must not be
  papered over (P1).
- **A recorded design position is overridden.** The `:802` deletion reverses
  `test_adversary_never_runs_without_a_primary_reviewer` and the argument in
  its docstring (§3.4). The rebuttal is stated in full and the test is amended
  rather than deleted, but a reviewer who finds the original argument more
  persuasive should say so at the user gate, not after landing.
- **Waiver fatigue — priced out by the OQ2 ruling, not merely accepted.** The
  first draft's grading rule would have met a failing advisory check on every
  merge for the default configuration (`adversarial_review_enabled=False`), and
  reviewer A1 showed the same for any run containing a quarantined task. Under
  the ruling both pass while staying tombstoned, so a failing
  `review_lenses_present` now names one specific condition — a lens asked for,
  reached, and undelivered. The residual risk moves in the opposite direction:
  the check is *quiet* in the two common absence cases, so the tombstone's
  detail text is the only thing carrying them to a human. It must actually be
  rendered — §3.5 requires all presence states in the detail, and tests 8b/8c
  pin it.

---

## 7. Advisor consultation

One round, answered in full: `.workspace/tmp/advisor-13.md` (2026-09-09).
The advisor independently verified the anchors, corrected the brief's placement
of the C3 manifest (`gate.py`, not `merge/step.py`), and recommended:

1. Tombstone bites at the merge gate, not the task done-path — preserving
   REVIEW-1.3 rather than amending it by stealth. **Adopted** (§3.4, §3.5), and
   escalated to the user as OQ1 because it is the one place this design departs
   from the register's literal wording. **Upheld at the gate** (ruling OQ1).
2. Three-state structural enum rather than a reason string. **Adopted** (§3.1).
3. The merge `review_severity` `None`-read belongs in C8, not a follow-up row —
   shipping task-layer-only would leave a known bypass. **Adopted** (§3.5).
4. The `:802` compound guard is in scope as a correctness fix. **Adopted**
   (§3.4).

The advisor would refuse: blocking `done` without an explicit contract
amendment; ABSOLUTE classification for lens absence; a reason-string-only
tombstone; splitting the merge fix into a follow-up.

**Divergence from recorded counsel.** On the pre-check dedup, `advisor-13.md`
§4 rated it "hygiene, not gating — do it in the same diff only if it stays
small". §3.2 elevates it to the mechanism and makes it non-optional, on the
grounds that the dedup *is* the drift protection for the quintuplicated
predicate (§1.2) and that a tombstone derived independently of the predicate
that gated the run reintroduces C8 in a subtler form. Recorded here as a
planner departure from the advisor's rating rather than as agreement.

No degradation to record — the advisor seat was available and answered.

---

## 8. Rulings — user gate, 2026-09-10

All five open questions were decided at the gate, taking the second reviewer
pass (`.workspace/tmp/reviewer-2.md`, verdict **approve**) and its advisory A1
into account. Each ruling below is already folded into the design above; the
question it settles is restated so the reasoning survives the decision.

**OQ1 — where the tombstone bites: MERGE GATE ONLY, as designed.**
The task layer reads a typed presence value, so absence is no longer spelled as
approval, but it does not block the done path in any presence state. REVIEW-1.3
and the `review/AGENTS.md` fail-open invariant are untouched — no contract
amendment. Enforcement lands one layer later, at the merge gate, through C3's
audited-override route. *Folded into §3.4, §3.5.*

**OQ2 + A1 — grading rule: FAIL ONLY ON `UNDECLARED_ABSENT`, plus a fourth
presence value `NOT_REACHED`.** The gate took option (c) and extended it with
reviewer A1's remedy (i). The adversary's run site (`code/step.py:801`) is
never reached on the post-gate return, so quarantined and budget-exhausted
tasks would otherwise have been classified `UNDECLARED_ABSENT` — routine
pipeline geometry reported as broken wiring, which is C8's own defect
reintroduced inside the fix. `NOT_REACHED` types that geometry: visible in
`TaskResult` and in the check detail, non-failing. `DECLARED_ABSENT` likewise
passes the check but stays tombstoned. `UNDECLARED_ABSENT` therefore keeps
meaning exactly "enabled, reached, and the wiring broke". *Folded into §3.1,
§3.2, §3.4, §3.5, §3.7, tests 1, 2, 5c, 7, 8, 8b, 8c.*

**OQ3 — check granularity: ONE uniform `review_lenses_present`, as designed**
(orchestrator ruling). Both lenses are graded by a single check whose detail
names the lens and its presence state, rather than a per-lens pair with the
primary at a higher bar. *Folded into §3.5.*

**OQ4 — the dead `TaskHost` twins: DELETE, in C8 scope.**
`TaskHost._run_adversary` (`workflows/task_host.py:311`) and `_run_deep_review`
(`:335`) are removed as part of this work rather than deferred, because leaving
two unreachable copies of the absence predicate would undercut the dedup that
§3.2 elevates to the mechanism. Reviewer note P1 applies: the deletion shifts
the source-concatenation offsets that `test_adversary_is_fail_open` depends on.
*Folded into §3.6b, §4.1, §6.*

**OQ5 — benchmark lens-outcome records: SEPARATE ROW, out of C8 scope.**
The proposal is filed at
`.workspace/tasks/2026-09-10-benchmark-lens-outcome-records.md`, widened per
reviewer note P2 to cover both lenses rather than the adversary alone. Per
protocol the register row itself is added by the user. This work does not touch
`benchmarks/`. *Folded into §5.*
