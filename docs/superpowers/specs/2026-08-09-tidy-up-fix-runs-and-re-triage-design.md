# Tidy-Up Fix Runs and the Before/After Re-Triage Delta — Design

| | |
|---|---|
| Date | 2026-08-09 |
| Work items | **E-44** (closes §10's Tier 0 fix half; E-42 shipped the assess half) |
| Requirements | FR-904, FR-915; NG5; US-8 (second half), US-9; FR-104/FR-106/FR-803 reused, not re-implemented |
| Scope input | `PRD.md` §FR-900, §NG5; `ROADMAP.md` §10 (E-44), §15 item 2; `docs/superpowers/specs/2026-08-08-triage-workflow-and-readiness-gate-design.md` §11 |
| Status | Implemented |

E-42 shipped triage's assess half: a durable workflow that pins a commit, fans
out seven deterministic signals, computes a readiness verdict, and gates on it.
It deliberately shipped no fix path — `FixClass.MECHANICAL` has existed on
`TriageFinding` since E-41 with no consumer.

This increment is that consumer, and it is the first end-to-end proof of the
assess → fix → **prove** claim: accepted mechanical findings become governed
brownfield runs that open one PR each, and triage then re-runs so the delta
between before and after is recorded evidence rather than a claim.

---

## 1. What exists today

**Built and load-bearing:**

- **`src/sdlc/triage/`** — `RepoTriage` / `Readiness` / `SignalResult` /
  `TriageFinding` / `FixClass` / `Verdict`, seven signal activities, and the
  `SIGNALS` registry. Twelve rules across four signals already classify
  `MECHANICAL`: `gitignore_missing`, `gitignore_missing_env`, `no_env_example`
  (baseline), `env_file_tracked` (secrets), `permissive_cors`,
  `debug_enabled`, `allowed_hosts_wildcard`, `world_readable_storage`
  (misconfig), `unpinned_dependency`, `duplicate_dependency`,
  `unused_dependency` (dependencies).
- **`TriageWorkflow` (`workflows/triage.py`)** — returns `RepoTriage`, hosts
  the FR-903 readiness gate, records a `ReadinessOverride` on the artifact.
  Its ids are already per-*run*, written that way (E-42 D5) precisely because
  E-44's assess → fix → re-triage loop would be the first thing to collide on
  a per-repository id.
- **`GateHost` (`workflows/gates.py`)** — FR-301 policy resolution, FR-302
  `(gate, round)` identity and first-decision-wins, FR-303 timers. Extracted at
  E-42 D2 so a second workflow can host a gate without restating the rule.
- **`FeatureWorkflow` (`workflows/feature.py`, 2451 lines)** — the governed
  path from a task to a PR: ADR-14 integration branch, per-task worktree,
  clean-context reviewer, bounded fix loop, `DeterministicQualityGate`,
  `open_pull_request`.
- **`compute_readiness()` (`triage/models.py:120`)** — the only producer of a
  `Verdict` (E-41 D4). This design adds no second path to one, and takes its
  discipline as the template for `compute_delta`.

**The gaps:**

1. **`TriageFinding` has no identity.** `(signal, rule, path, line)` is the only
   natural key, and `line` shifts the moment a fix lands above it — so any
   before/after diff keyed on it manufactures phantom `resolved` + `new` pairs.
2. **`FeatureWorkflow` has one entry point**, at stage 0. Reaching the code
   stage costs research → clarify → architecture → planning, six-plus model
   calls, and clarify can *block on an open question* — for "add `.env` to
   `.gitignore`".
3. **`open_pull_request` opens; it does not merge.** Re-triaging the base
   branch after the fix runs would measure a tree containing none of the fixes.

---

## 2. Decisions

### D1 — Fix runs enter `FeatureWorkflow` with a deterministically-authored plan

NG5 is the constraint that matters: *"Assessment never patches a repository
directly. Every fix is a governed factory run."* It says nothing about which
stages must run. The stages that make a run *governed* are stage 8 onward —
clean-context review (ADR-6/FR-204), the bounded fix loop (FR-105), the
deterministic quality gate (FR-106), the merge gate. Clarify, architecture and
planning exist to decide *what* to build, and for a mechanical finding that
question is already answered by the finding itself.

So `TidyUpWorkflow` authors the `ImplementationPlan` from the finding, and
`FeatureWorkflow` gains one optional input:

```python
class SeededWork(BaseModel):
    """E-44: an ImplementationPlan authored deterministically, not by the
    planner. Stages 0-3 are skipped; everything from _dev_task down is
    unchanged and still binding."""

    arch: ArchitectureSpec
    plan: ImplementationPlan
```

`_pipeline` gains one branch: when `seeded` is present, `arch, plan =
seeded.arch, seeded.plan` and control enters stage 4 (`feature.py:2069`).

`arch` is seeded rather than made optional because after planning it is read at
exactly one place — `feature.py:2381`, the PR body — and seeding it keeps
stages 4 onward free of `| None` handling.

**Rejected: a dedicated `FixRunWorkflow`** that reuses the activities without
touching `feature.py`. It would be a second registry of "how a governed change
reaches a PR", which is the exact failure shape this codebase has already paid
for twice: ADR-6's boot check validated an `agents.yaml` `developer` role while
`cfg.roles["dev"]` did the coding, and every stage passed one hardcoded `MODEL`
constant to `content_key` while per-role models were configured elsewhere. Both
invariants held only while two copies happened to agree.

**Rejected: full `FeatureWorkflow` runs per finding.** Faithful to the
roadmap's one-line description and to NG5, but it pays six model calls for a
one-line fix, and clarify's open-question wait can park a tidy-up run
indefinitely on a question the finding already answers.

### D2 — One PR per accepted finding

ADR-14 already gives per-task worktrees, per-task review, and per-task
quarantine *inside* one run; batching findings as N `DevTask`s in a single run
would keep all of that and cost one QA pass instead of N. It is rejected anyway,
because the shared artifact is the one the client acts on: with one PR the
client accepts or declines the whole tidy-up, and one item failing the shared
absolute merge gate takes the good items with it.

US-9 says *"PR per item"*, and the reason it says so is that a client merging
the CORS fix while declining an `unused_dependency` removal is the normal case,
not the exception — E-41a's own finding text says "distribution names and
import names diverge, so confirm before removing."

One accepted finding is therefore one child `FeatureWorkflow` run, one
integration branch, one PR.

### D3 — Identity is signal-supplied and composed in one place

`TriageFinding` gains `key: str = ""` — the rule-scoped discriminator each rule
already holds: the dependency name for `unpinned_dependency`, the tracked path
for `env_file_tracked`, the matched literal for `permissive_cors`. Composition
lives in one pure function, in **`triage/models.py` beside `compute_readiness`**
rather than in `delta.py`: the `SignalResult` validator below needs it, and
`delta.py` imports `models.py`, so siting it in `delta.py` would close an import
cycle.

```python
def finding_identity(f: TriageFinding) -> str:
    return f"{f.signal}:{f.rule}:{f.path}:{f.key}"  # never `line`
```

The default `""` keeps all seven signals valid without edits, which creates a
silent-collapse hazard: an author who forgets `key` turns three unpinned
dependencies in one manifest into one identity, and fixing one would read as
resolving all three. The guard is a `SignalResult` validator rejecting
**duplicate identities within a single result** — the failure is caught in the
signal that caused it, not in the delta that inherits it. Signals that populate
`key` bump `VERSION`, per the `SIGNALS` registry contract E-46 will read.

**Rejected: deriving the key from existing fields.** `(signal, rule, path)`
collapses same-rule findings unconditionally. `(signal, rule, path, evidence)`
looks better but `evidence` is `""` for `duplicate_dependency`,
`gitignore_missing`, and others — so it collapses for *some* rules, silently,
which is worse than collapsing for all of them.

### D4 — `compute_delta` is the only producer of a `FindingState`

Mirroring E-41 D4: no caller sets a state, so a `TidyUpReport` cannot disagree
with its own inputs, and E-52's bundle reads one derivation rather than
re-deriving policy.

```python
class FindingState(str, Enum):
    RESOLVED = "resolved"  # before yes, after no
    PERSISTED = "persisted"  # both
    NEW = "new"  # after only
    UNVERIFIABLE = "unverifiable"  # not measurable on one side
```

`NEW` is first-class: a fix that broke something is an outcome, not noise.

### D5 — `UNVERIFIABLE` is the FR-915 guard, and it is why this is not a set difference

A naive before-minus-after diff reads *absence* as *resolution*. That is exactly
the conflation `Measurement` was built to remove — `report_from_sarif` returning
`critical=0` for a malformed document, byte-identical to a clean scan. Five
conditions produce `UNVERIFIABLE` instead:

| Condition | Effect |
|---|---|
| Owning signal `not_collected` on either side | its findings → `UNVERIFIABLE`, carrying the signal's own reason |
| `SignalResult.version` differs before vs after | that signal's findings → `UNVERIFIABLE` ("signal changed mid-run") |
| Fix branch conflicted, absent from the verification tree | that identity → `UNVERIFIABLE`, **not** `PERSISTED` |
| No fix branch produced at all (`after is None`) | *all* backlog identities → `UNVERIFIABLE`, never an empty delta reading as "nothing resolved" |
| Finding present only after | `NEW` |

`reason` is required whenever the state is `UNVERIFIABLE`, enforced by a
model validator.

The version check costs nothing and is not theoretical: both triages normally
run against the same worker, but a deploy between them would otherwise let a
rule change silently register as a fix.

### D6 — The after-triage measures a composite verification branch

The fixes live on unmerged branches, so the tree to re-triage has to be
constructed. One new activity, beside the existing `merge_into_integration` in
`src/sdlc/activities.py`:

```python
def build_verification_branch(inp) -> VerifyResult:
    # worktree at before.commit_sha, branch sdlc/tidyup-verify/<tidyup_id>
    # git merge --no-ff each successful fix branch, in accepted order
    # conflict -> git merge --abort, record in `conflicted`, continue
```

→ `VerifyResult(ref, head_sha, merged: list[str], conflicted: list[str])`

Local ref, never pushed — E-44 is operator-run and delivery is PR-only
(FR-1003/E-59 is where refs reach a remote). The after-triage runs against the
same `repo_dir` with `commit=head_sha`, so `triage_resolve_commit` and the build
probe's throwaway clone both work unchanged.

`TidyUpReport.verify_ref` records what the after-triage actually measured. The
report never presents that number as the state of `main`, because it is not.

**Rejected: per-item re-triage** (N extra triages, each with a 40-minute build
probe) — more informative, and the cost is superlinear in exactly the case Tier
0 targets. **Rejected: waiting for a human to merge the PRs** — truest to what
the client ships, but it parks the workflow on an action outside the factory and
E-44 stops being demonstrable in a single run. **Rejected: re-triaging the base
branch and marking the delta pending** — it measures nothing, which is the
conflation D5 exists to prevent.

### D7 — Admission reuses E-42's rule verbatim

FR-903's gate blocks *Tier 2*, not tidy-up, so an admission rule is not
automatic. It is adopted anyway for a mechanical reason: on a repository that
does not build, `build_integration_green` is an **absolute** merge-gate check,
so every fix run would produce a correct patch and then be blocked — N runs of
model spend to learn what the build probe already reported.

The rule is E-42 D1's, unchanged and unduplicated:

```python
admitted = before.readiness.verdict is Verdict.READY or before.override is not None
```

The same line E-45 will use. On a not-ready repository the operator meets the
readiness gate inside the child `TriageWorkflow`, decides once, and the decision
is recorded as a `ReadinessOverride` on the artifact.

**Not admitted is not empty-handed.** The report still carries the full
`backlog` with zero `accepted` — that backlog *is* US-8's checkable hygiene
list, and it is the deliverable even when nothing is fixed.

### D8 — Selection arrives on a signal; the gate stays a gate

`GateDecision` is approve / revise / reject plus comments. It carries no item
selection, and widening it would push a tidy-up concern into FR-302's contract.

The precedent already exists in `FeatureWorkflow`: clarify's open questions
arrive on an `answer_question` signal while the decision arrives on a gate. So:
a `select_items(identities: list[str])` signal narrows the backlog, and one
`tidy_up` gate decides. Unsent means all.

The selection is read **once, at decision time**, and copied into
`TidyUpReport.accepted`. A signal arriving after the gate resolves cannot
retroactively change what ran — the same first-decision-wins spirit FR-302
applies to the decision itself.

### D9 — `fix_cfg` defaults the deploy gate to `OFF`

`feature.py:2387` opens the `deploy` gate *before* checking
`cfg.deploy.enabled`, and `PipelineConfig.default_gate_policy` is `HARD`. Left
alone, every tidy-up PR would park for 48 hours on a gate for a deploy that was
never going to run.

`TidyUpInput.fix_cfg` therefore ships `"deploy": GateConfig(policy=OFF)` in its
default factory. This is a defaulting decision in E-44, **not** a change to
`feature.py` — the ordering there is deliberate for feature runs, where the gate
records an operator's intent independently of whether deploy is configured.

### D10 — Serial fix runs, capped

Children run serially. Per-task worktrees make tasks concurrent *within* a run;
nothing makes two runs' git operations on one `repo_dir` safe. `max_fix_runs`
(default 10) caps spend; excess backlog items are recorded as deferred with a
reason rather than silently dropped.

Child ids are derived, never generated: `f"{wf_id}-fix-{n:02d}"` over the
backlog sorted by `finding_identity`. Sorting is load-bearing — replay must
produce the same ids.

---

## 3. Contracts

### Changed

```python
# src/sdlc/triage/models.py
class TriageFinding(BaseModel):
    ...
    key: str = ""  # D3: rule-scoped discriminator; never `line`


class SignalResult(BaseModel):
    ...

    @model_validator(mode="after")
    def _identities_unique(self) -> "SignalResult": ...  # D3


def finding_identity(f: TriageFinding) -> str: ...  # D3
```

### New — `src/sdlc/triage/delta.py` (pure: Pydantic + `.models` only)

```python
class FindingState(str, Enum): ...


class FindingDelta(BaseModel):
    identity: str
    signal: str
    rule: str
    severity: Literal["critical", "high", "medium", "low"]
    state: FindingState
    reason: str = ""  # required when UNVERIFIABLE


def compute_delta(
    before: RepoTriage, after: RepoTriage | None, conflicted: list[str] = ()
) -> list[FindingDelta]: ...
```

### New — `src/sdlc/workflows/tidyup.py`

```python
class TidyUpInput(BaseModel):
    repo_dir: str
    commit: str = "HEAD"
    build_probe: bool = True
    advisory_source: str = "none"
    gates: GateSettings = ...  # the tidy_up gate
    fix_cfg: PipelineConfig = ...  # D9: deploy gate OFF
    max_fix_runs: int = 10


class FixRunResult(BaseModel):
    identity: str
    workflow_id: str
    outcome: str  # FeatureWorkflow's return string, verbatim
    pr_url: str | None = None
    branch: str | None = None
    merged_into_verify: bool = False


class TidyUpReport(BaseModel):
    before: RepoTriage
    after: RepoTriage | None
    verify_ref: str | None
    backlog: list[str]  # every mechanical identity
    accepted: list[str]  # the subset approved
    deferred: list[str]  # accepted but beyond max_fix_runs
    runs: list[FixRunResult]
    deltas: list[FindingDelta]
    readiness_before: Verdict
    readiness_after: Verdict | None
```

### New — `src/sdlc/models.py`

```python
class SeededWork(BaseModel):  # D1
    arch: ArchitectureSpec
    plan: ImplementationPlan
```

---

## 4. Control flow

`TidyUpWorkflow(GateHost)`:

1. **Baseline** — child `TriageWorkflow`, id `f"{wf_id}-triage-before"`. The
   child owns the readiness gate; the operator decides there, once.
2. **Backlog** — mechanical findings from `before`, sorted by identity.
   Materialized before admission is checked, so the not-admitted path still
   returns it.
3. **Admission** (D7) — not admitted → return a report with the full `backlog`,
   empty `accepted` and `runs`, and every identity `UNVERIFIABLE` per D5 rule 4.
4. **Gate** — `tidy_up`, with the `select_items` signal (D8).
5. **Fix runs** (D10) — serial child `FeatureWorkflow(seeded=SeededWork(...))`,
   one per accepted identity.
6. **Verify** (D6) — `build_verification_branch` over the branches of runs that
   reached a PR. "Reached a PR" is read off `FeatureWorkflow`'s return string,
   which is `deployed:…` or `merged-not-deployed:…` on exactly those paths; a
   `rejected:…` or `failed:…` run contributes no branch.
7. **After** — child `TriageWorkflow` at the verification head,
   id `f"{wf_id}-triage-after"`. Skipped when step 6 merged nothing, leaving
   `after=None` and D5 rule 4 in force.
8. **Delta** — `compute_delta(before, after, conflicted)`.

Per accepted finding, the authored task:

```python
DevTask(id="T01", role="dev",
        title=f"{f.rule} in {f.path or 'repository'}",
        description=f.detail + evidence quote + "Change nothing else.",
        acceptance_criteria=[f"triage signal `{signal}` v{version} no longer "
                             f"reports `{f.rule}` for `{f.path}`"],
        files_hint=[f.path] if f.path else [],
        contract=ValidationContract(task_id="T01", assertions=[...],
                                    frozen=True))
```

FR-803 freezes the contract *at planning, before code*. Here the analogous
moment is backlog acceptance — still before any code, with a deterministic
producer instead of the planner.

---

## 5. Error handling

Every failure degrades one item, never the run — the shape `TriageWorkflow._one`
already established:

- child `FeatureWorkflow` raises → `FixRunResult(outcome="failed:<type>")`,
  loop continues to the next accepted item
- merge conflict → recorded in `VerifyResult.conflicted`, run continues, and
  D5 rule 3 marks that identity `UNVERIFIABLE`
- after-triage fails → `after=None`, D5 rule 4 applies
- `tidy_up` gate rejected → report with full `backlog`, empty `accepted`

---

## 6. Testing

**Pure (no Temporal):**

- `compute_delta` — one test per D5 row, plus `RESOLVED` / `PERSISTED` / `NEW`
- `finding_identity` — stability under line drift; distinctness for two
  same-rule findings in one file
- the duplicate-identity `SignalResult` validator
- backlog materialization — `MECHANICAL` only, sorted, capped, excess recorded
  as `deferred`
- the `reason`-required-when-`UNVERIFIABLE` validator

**Temporal (`pytest -m temporal`, existing `tests/fakes/` stubs):**

- not-admitted → backlog present, `runs` empty, no child `FeatureWorkflow`
  started
- admitted → child ids deterministic across replay
- `select_items` narrows; a signal arriving after the gate resolves does not
- a `SeededWork` run never invokes `t_clarifier` / `t_architect` / `t_planner`
  (`TestModel` stubs record calls)
- one conflicted branch → that identity `UNVERIFIABLE`, the others still
  computed

---

## 7. Out of scope

Memoizing the second triage on `(tree hash, signal version)` — **E-46** ·
pushing the verification ref or auto-merging PRs — **FR-1003 / E-59** ·
`JUDGEMENT` and `STRUCTURAL` findings, which by construction are not
mechanically fixable · cloning from a URL — **FR-1003 / E-59** · per-rule
deterministic fixers (they would violate NG5) · any Tier 2 consumer of the
report — **E-45 / E-52** · containment for the fix runs, which execute a foreign
repository's toolchain as the worker user — **NFR-9, removed by E-57 / E-21**.

---

## 8. What this closes

- **FR-904** closes — mechanical findings execute as brownfield factory runs and
  the before/after delta is recorded evidence rather than a claim.
- **US-8** closes — its verdict half landed with E-42; the backlog is the
  checkable hygiene list, and it lands even on a repository that is not
  admitted.
- **US-9** closes — the operator approves a backlog, gets a PR per item and a
  recorded delta.
- **P5** reaches its exit criterion: one unfamiliar repository triaged, a
  mechanical backlog fixed through governed runs, before/after delta recorded.
- **NG5** holds — no path in this design patches a repository outside a
  `FeatureWorkflow` run.
- **NFR-9** unchanged in substance and larger in exposure: the fix runs execute
  the triaged repository's build and test commands, not just the build probe.
  Operator-run only until E-57 / E-21.
