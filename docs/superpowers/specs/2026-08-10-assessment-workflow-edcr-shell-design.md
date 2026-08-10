# `AssessmentWorkflow` — the EDCR DAG Shell and the Tier 2 Admission Rule — Design

| | |
|---|---|
| Date | 2026-08-10 |
| Work items | **E-45** (opens §11's Tier 2; every phase body is a later item) |
| Requirements | FR-911; ADR-18; FR-903 narrowed; FR-915 applied to phases |
| Scope input | `PRD.md` §FR-910; `ROADMAP.md` §11 (E-45), §15; `docs/superpowers/specs/2026-08-08-triage-workflow-and-readiness-gate-design.md` D1; `docs/superpowers/specs/2026-07-25-brownfield-assessment-and-outcome-measurement-design.md` §§3–5 |
| Status | Design approved 2026-08-10 |

E-42 shipped a readiness gate whose own spec (D1) admits it "blocks nothing":
Tier 2 did not exist, so the verdict and its override were recorded against a
consumer that had not been written. This increment writes that consumer.

What it deliberately does **not** do is build any of the EDCR phases. Scan is
E-46, discover E-48, assess E-49, report and generate E-52, finish E-51. This is
the shell those land in — and, more importantly, it is the place where three
invariants get installed while the artifact is still small enough that
installing them is cheap.

It contains no LLM call.

---

## 1. What exists today

**Built and load-bearing:**

- **`TriageWorkflow` (`workflows/triage.py`)** — pins a commit, fans out seven
  hygiene signals, computes a three-valued `Verdict`, and opens the FR-903
  readiness gate. Records a human's proceed-anyway decision on the artifact as
  `RepoTriage.override`.
- **`ReadinessOverride` (`triage/models.py:101`)** — `approved_by` carries
  `GateDecision.decided_by` **verbatim**, so `"policy"` (gate OFF) and
  `"timeout"` (`on_timeout=APPROVE`) stay legible as non-human on the face of
  the artifact. That field exists precisely so a consumer can refuse them.
- **`GateHost` (`workflows/gates.py`)** — FR-301 policy resolution, FR-302
  `(gate, round)` identity and first-decision-wins, FR-303 notification and
  expiry timers, as a mixin a second workflow inherits rather than restates.
- **`TidyUpWorkflow` (`workflows/tidyup.py`)** — the reference shape for a
  workflow that runs `TriageWorkflow` as a child and assembles a report
  envelope from it.
- **`Measurement` (`measurement.py`)** — FR-915's `not_collected` vs measured
  discipline, already retrofitted onto `CoverageReport`, `SecurityReport` and
  `SignalResult`.

**The problem, stated as three defects rather than one absence:**

1. **A live admission hole.** `tidyup.py:87-97` carries an explicit
   `FUTURE-CONSUMER TRAP` comment. `TidyUpWorkflow`'s after-triage measures and
   does not gate, so `triage_gates(..., gating=False)` auto-approves its own
   readiness gate; when the verification tree is not READY, `TidyUpReport.after`
   therefore carries an override with `approved_by == "policy"` — a machine
   placeholder. E-42's admission rule (`verdict is READY or override is not
   None`) applied to that field admits a tree nobody approved. The comment names
   E-45 as the fix. This is that fix.
2. **One rule, about to become two copies.** `tidyup/backlog.py:18` reads
   *"E-42's admission rule verbatim — the same line E-45 will use."* The moment
   Tier 2 tightens, that sentence is false and the codebase holds two admission
   rules that agree only by coincidence — the failure shape
   `2026-07-16-registry-drives-every-role` was written about, where an
   invariant held only while two hardcoded lists happened to match.
3. **No phase has a place to be honestly absent.** With no `Assessment`
   artifact, there is no contract in which "discover did not run" is
   distinguishable from "discover found nothing" — the same conflation
   `report_from_sarif` had on the absolute security floor before E-40.

---

## 2. Decisions

### D1 — The shell ships now, with the invariants, not after a phase exists

The alternative was to defer the workflow until E-46 gives it content. Rejected:
FR-911 is specifically *"a durable `AssessmentWorkflow` SHALL execute the EDCR
DAG"*, and the three defects in §1 are all live **today** — defect 1 is a trap a
future consumer walks into, and the cheapest moment to install a fail-closed
admission rule is before any phase is producing findings that would make
overriding it tempting.

The shell is falsifiable on its own: an admitted repository runs to `finish` and
produces an artifact that says, in typed fields, that nothing was assessed; a
policy-approved tree is refused.

### D2 — Admission is one function with a strictness parameter

The two tiers genuinely differ, and the difference is defensible:

- **Tier 0 (tidy-up)** adopts admission for a *build-economics* reason, stated
  in `backlog.py`'s docstring: on a repository that does not build,
  `build_integration_green` is an absolute merge-gate check, so every fix run
  would produce a correct patch and then be blocked. That argument does not
  care who approved.
- **Tier 2 (assessment)** is expensive per-capability reasoning over a structure
  the readiness verdict says may not exist, and it terminates in an evidence
  bundle handed to a customer (FR-921). "A human looked at this and said
  proceed" is load-bearing there in a way it is not for a mechanical PR.

Encoding that as two functions in two modules is defect 2. Encoding it as one
function with a parameter makes the difference **reviewable in one place**:

```python
# src/sdlc/triage/admission.py
def admits(triage: RepoTriage, *, require_human: bool) -> tuple[bool, str]:
    """FR-903. The strictness difference between tiers is a PARAMETER, so two
    tiers cannot drift into meaning different things by accident."""
```

It returns `(bool, reason)` rather than a bare bool: the reason is recorded on
the `Assessment`, so a refusal is legible without a Temporal replay.

`tidyup/backlog.admitted` becomes a delegation at `require_human=False`, and its
docstring's "verbatim — the same line E-45 will use" claim is corrected in
place. Touching shipped E-44 code is deliberate and is the wider half of this
diff; the narrower alternative (a second Tier 2 rule beside E-44's) is exactly
defect 2 and was rejected.

The rule, which is also the test table:

| verdict | override | Tier 0 (`require_human=False`) | Tier 2 (`require_human=True`) |
|---|---|---|---|
| `READY` | — | admit | admit |
| not `READY` | none | refuse | refuse |
| not `READY` | `approved_by="policy"` | admit | **refuse** |
| not `READY` | `approved_by="timeout"` | admit | **refuse** |
| not `READY` | `approved_by="human"` | admit | admit |

`reviewer` is **not** consulted. It is self-asserted (the gap FR-1004 closes),
and `ReadinessOverride`'s own docstring records why the class of decider, not
the claimed identity, is the trustworthy field.

### D3 — `init` runs a `TriageWorkflow` child; a `RepoTriage` is never accepted as input

Accepting a caller-supplied `RepoTriage` would be cheaper — no re-triage, no
second build-probe execution. It is rejected because the admission rule's whole
subject is `override.approved_by == "human"`, and a caller-supplied artifact is
a caller-supplied value for exactly that field. A fail-closed rule reading an
attacker- or accident-controlled input is not fail-closed.

Running the child means the verdict, the readiness gate, and the human decision
all appear in **this assessment's own history**, so the claim "a human admitted
this tree" is replayable evidence. It also directly mirrors
`TidyUpWorkflow._triage`, so there is one pattern for "a workflow that needs a
triage", not two.

Accepted cost: an assessment run immediately after a tidy-up re-triages the same
tree, including a second build-probe execution of the repository's own code
(NFR-9, unchanged — operator-run only until E-57/E-21). FR-912's
`(tree hash, signal version)` memoization is E-46's job and will absorb most of
it.

### D4 — Explicit phase methods; order is the run body

The DAG is seven `async def _phase(...)` methods called in sequence, matching
`FeatureWorkflow._pipeline`. Rejected alternatives: a `PhaseSpec` registry
mirroring `triage/registry.py` (the seven phases are far more heterogeneous than
seven signals — some deterministic activities, some proposer calls, some pure
checks — so a common spec would be a poor abstraction bought early), and a
pluggable phase registry (that is the graph interpreter §14's **E-72** owns, and
§15 item 7 deliberately leaves it unsequenced).

The two FR-911 deviations from the source methodology are therefore facts about
the run body:

- **`report` runs after `assess`.** The methodology numbers report 4th and
  assess 5th; reports render risk scores only `assess` produces, and `/finish`
  requires all five reports complete.
- **No `workflow.json`.** BrownKit's `phases[].status/started_at/completed_at`
  is a hand-rolled durable state machine, which is what Temporal history already
  is. FR-911: *"phase state SHALL live in workflow history."*

### D5 — Unbuilt phases report `not_collected`, and there is no untyped payload

Every stub returns `Measurement.not_collected("scan not implemented (E-46)")`.
The artifact therefore never renders as a clean assessment of a repository
nothing looked at — FR-915 applied to phases, the same shape as the
malformed-SARIF hole E-40 closed on the absolute floor.

`PhaseResult` carries **no** `payload: dict`. Each later item adds its own typed
field to `Assessment` (`capabilities: CapabilityMap | None` from E-47,
`risk: UnifiedRiskMap | None` from E-49). A generic bag would be a schema-less
hole in the one artifact that gets handed to a customer under FR-921, and it
would let a phase ship content no contract describes.

### D6 — `terminal_status` is derived, never assigned

A pure function over the phase results, so E-46 landing changes the status with
no workflow edit and no second place to update:

| condition | status |
|---|---|
| not admitted | `blocked:admission` |
| admitted, every post-`init` phase `not_collected` | `admitted:no-phases-implemented` |
| admitted, some phases collected | `assessed:partial` |
| every phase collected | `assessed` |

`assessed:partial` is the seam FR-922's budget exhaustion (E-55) reuses;
this increment computes it but no phase can currently produce it.

---

## 3. Module layout

```
src/sdlc/assessment/
  __init__.py
  models.py          # PhaseId, PhaseResult, Assessment, terminal_status()
src/sdlc/triage/
  admission.py       # admits() -- the one rule (D2)
src/sdlc/workflows/
  assessment.py      # AssessmentWorkflow(GateHost), AssessmentInput
```

`assessment/models.py` is **pure** — Pydantic, `measurement.py`, and
`triage/models.py` only. It must not import `models.py`, `activities.py`, or
`temporalio`, exactly as `triage/models.py` and `capability/models.py` must not:
a dependency there would appear as a reviewable import.

`admits()` lives under `triage/` rather than `assessment/` because its subject
is a `RepoTriage` and both tiers call it; putting it in `assessment/` would make
Tier 0 import Tier 2 to decide a Tier 0 question.

---

## 4. Contracts

```python
class PhaseId(str, Enum):
    INIT = "init"
    SCAN = "scan"
    DISCOVER = "discover"
    ASSESS = "assess"
    REPORT = "report"          # after ASSESS -- FR-911 deviation (a)
    GENERATE = "generate"
    FINISH = "finish"


class PhaseResult(BaseModel):
    phase: PhaseId
    collected: Measurement     # not_collected names the owing E-item


class Assessment(BaseModel):
    repo_dir: str
    commit_sha: str = ""       # "" only when init failed to pin one
    toolchain: str | None = None
    # init's artifact -- in-history evidence (D3). None ONLY when the child
    # workflow itself failed (§6), which is also the only case where
    # admitted is False without admits() having been consulted. A validator
    # enforces `triage is None implies admitted is False`, so no code path
    # can admit a repository whose triage never materialized.
    triage: RepoTriage | None = None
    admitted: bool
    admission_reason: str      # admits()' reason, verbatim
    phases: list[PhaseResult]
    terminal_status: str
```

`_init` returns both halves explicitly rather than a bare `PhaseResult`, since
the caller needs the artifact and the phase row is what lands in `phases`:

```python
class InitOutcome(BaseModel):
    result: PhaseResult            # measured, or not_collected on child failure
    triage: RepoTriage | None
```

`AssessmentInput` mirrors `TriageInput`'s knobs, which are the ones the child
needs:

```python
class AssessmentInput(BaseModel):
    repo_dir: str
    commit: str = "HEAD"
    build_probe: bool = True
    advisory_source: str = "none"
    gates: GateSettings = Field(default_factory=GateSettings)
```

`max_gate_rounds` is **not** surfaced: the readiness gate's REVISE loop belongs
to the child, which owns its own bound.

---

## 5. The run

```python
@workflow.defn
class AssessmentWorkflow(GateHost):

    @workflow.query
    def assessment(self) -> Assessment | None: ...

    @workflow.run
    async def run(self, inp: AssessmentInput) -> Assessment:
        init = await self._init(inp)                  # TriageWorkflow child
        if init.triage is None:                       # §6 -- child failed
            return self._assembled(init, False, init.result.collected.reason)
        ok, why = admits(init.triage, require_human=True)
        if not ok:
            return self._assembled(init, False, why)
        rest = [
            await self._scan(inp),                    # E-46
            await self._discover(inp),                # E-48
            await self._assess(inp),                  # E-49
            await self._report(inp),                  # E-52, AFTER assess
            await self._generate(inp),                # E-52
            await self._finish(inp),                  # E-51
        ]
        return self._assembled(init, True, why, rest)
```

`_assembled` is the **only** constructor of an `Assessment`, and the only caller
of `terminal_status()` — one place where the artifact is built means the derived
status cannot disagree with the phase list it was derived from. On a refusal it
fills the six unrun phases with `not_collected("not run: repository not
admitted")`, so `phases` is always the full seven and anything rendering the DAG
can rely on that.

`AssessmentWorkflow` inherits `GateHost` even though it opens no gate of its
own: it gets `status`, `pending_decisions`, and `submit_gate_decision` for free,
and E-50's assessment gate checks will open gates here. The `_status` sequence
is `starting → triaging → running → <terminal_status>`.

The child runs at `{workflow_id}-triage` on `workflow.info().task_queue`, with
`inp.gates` passed through unchanged — the operator's readiness-gate policy is
the admission decision, and this workflow does not second-guess it.

**Non-admission is not empty-handed.** The returned `Assessment` still carries
the full `RepoTriage`, so the caller gets the readiness verdict and every
hygiene finding — the shape E-44 D7 established, where a repository that is not
admitted still yields US-8's checkable list.

---

## 6. Error handling & determinism

- **A child that raises degrades to a refusal, not a crash.** `_init` catches,
  the way `TriageWorkflow._one` does, and produces a refusal whose
  `admission_reason` names the failure. An assessment that could not establish
  admission must never proceed to assess, and the `triage is None implies not
  admitted` validator (§4) makes that unrepresentable rather than merely
  unwritten.
- **No `datetime.now()`, no `uuid4()`, no filesystem access in the workflow.**
  Every timestamp is `workflow.now()`; the child id is derived from
  `workflow.info().workflow_id`, never generated.
- **The stubs are pure returns.** No activity is scheduled for an unbuilt phase,
  so the shell adds no task-queue load and no retry surface.
- **`Measurement.not_collected` is never `measured(0.0)`.** A phase that did not
  run has no value, which is the whole of FR-915.

---

## 7. CLI surface

Parity with `sdlc triage` / `sdlc tidyup`:

```
python -m sdlc.cli assess --repo /path/to/repo [--commit HEAD]
python -m sdlc.cli assess --repo /path/to/repo --no-build-probe
python -m sdlc.cli assess show --id assess-myrepo-20260810T101500Z
```

`assess_workflow_id(repo, now)` produces `assess-<slug>-<stamp>`, run-scoped for
the reason `triage_workflow_id` documents: a bare `assess-<slug>` would let one
assessment parked on the readiness gate (HARD by default, 48h) block the next
assessment of that repository.

`AssessmentWorkflow` is registered in `worker.py`'s `workflows=[...]`. No new
activity is registered — this increment adds none.

## 8. Persistence

Temporal history only, which is FR-911's own requirement. Board publication
(E-78's `publish_artifact_version`) is the natural home once a phase produces
content worth versioning across runs — E-52's bundle and E-54's re-assessment
delta — and is explicitly deferred rather than forgotten. Versioning an empty
artifact today would also inherit §16's known `run_id` dedupe gap for no gain.

---

## 9. Testing

| File | Covers |
|---|---|
| `tests/test_assessment_admission.py` | §D2's five-row table at both strictness settings. The `policy` row cites `tidyup.py`'s `FUTURE-CONSUMER TRAP` by name, and asserts a `TidyUpReport.after`-shaped artifact is refused at Tier 2 and admitted at Tier 0. |
| `tests/test_assessment_models.py` | The four `terminal_status` rules; `phases` is exactly the seven `PhaseId`s in order; `report` precedes `generate` and follows `assess`; a stub's `not_collected` reason names an E-item. |
| `tests/test_assessment_workflow.py` | Sequencing, admission short-circuit (no phase runs when refused), child-failure degradation, and that the refused artifact still carries the full `RepoTriage`. |
| `tests/test_assessment_cli_wiring.py` | `assess` / `assess show` resolve through the same parser `main()` uses, mirroring `test_tidyup_cli_wiring.py`. |
| `tests/test_assessment_workflow_e2e.py` (`-m temporal`) | Two scenarios against a fixture repo with `--no-build-probe`, which forces `INDETERMINATE` by construction so admission is genuinely exercised: **(a)** gate `OFF` → `approved_by="policy"` → **refused**, `blocked:admission`; **(b)** a human `submit_gate_decision` on the child → **admitted**, seven phases, `admitted:no-phases-implemented`. |

Scenario (a) is the load-bearing test of this increment: it is the trap
`tidyup.py` documented, executed end to end.

The e2e is two workflows with no fan-out — materially lighter than the
`TidyUpWorkflow` e2e P5 deferred for host contention, so it is expected to run
here rather than being deferred.

---

## 10. Out of scope

- Every phase body: **E-46** scan, **E-48** discover, **E-49** assess,
  **E-51** finish criteria, **E-52** report/generate/bundle.
- **E-50**'s assessment gate checks. `/gate` is not a phase (FR-911); it is
  deterministic gate checks, and `GateHost` is already inherited for them.
- **E-56**'s `/enrich` as a declared stage input, and **E-55**'s per-phase
  budgets. `assessed:partial` (D6) is the seam E-55 fills.
- **FR-1004.** `reviewer` stays self-asserted; D2 consults the class of decider
  precisely because of that.
- Board publication (§8) and any `.sdlc/` export.

---

## 11. Roadmap consequences

| Item | Change |
|---|---|
| **E-45** | `[x]` — shell, admission rule, contracts, CLI. Phase bodies remain their own items. |
| **FR-911** | `[ ]` → `[ ]` ⚠️ — the DAG and its two deviations exist; six of seven phases are stubs. |
| **FR-903** | Note the Tier 2 narrowing to `approved_by == "human"` and the single `admits()` rule. |
| **P6** | Opened. Exit criterion (one repository audited end to end, SC-7 held, bundle handed over) untouched. |
| **§11 E-45 entry** | Replace "may narrow its admission rule" with the landed rule. |
| `workflows/tidyup.py:87-97` | `FUTURE-CONSUMER TRAP` comment updated: E-45 closed it. |
| `tidyup/backlog.py:18` | Docstring corrected — no longer "the same line E-45 will use". |
| `workflows/triage.py:104-109` | `override_from`'s "E-45 may narrow its admission rule" note becomes a statement of fact. |
