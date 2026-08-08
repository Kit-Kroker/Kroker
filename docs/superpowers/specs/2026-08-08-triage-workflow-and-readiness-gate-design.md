# `TriageWorkflow`, the Readiness Verdict, and the FR-903 Gate — Design

| | |
|---|---|
| Date | 2026-08-08 |
| Work items | **E-42** (closes §10's Tier 0 assess half; E-44 is the fix half) |
| Requirements | FR-901, FR-903; ADR-18; FR-301/FR-302/FR-303 reused, not re-implemented |
| Scope input | `PRD.md` §FR-900; `ROADMAP.md` §10 (E-42), §15 item 2; `docs/superpowers/specs/2026-08-06-repository-triage-hygiene-signals-design.md` §11 |
| Status | Implemented |

E-41 built seven deterministic hygiene signals and the artifact they populate,
and then deliberately shipped no surface: *"nothing invokes them until E-42
wires the workflow."* This increment is that wiring — a durable workflow that
pins a commit, fans out the signals, computes the readiness verdict, and gates
on it through the existing human-in-the-loop machinery.

It contains no LLM call. Every decision in it is a function of bytes read from
a pinned commit or of a human's audited decision.

---

## 1. What exists today

**Built and load-bearing:**

- **`src/sdlc/triage/`** — `RepoTriage` / `Readiness` / `SignalResult` /
  `TriageFinding` / `Verdict`, seven signal activities, and the `SIGNALS`
  registry. All seven are registered in `worker.py:119`. Nothing calls them.
- **`compute_readiness()` (`triage/models.py:96`)** — the only producer of a
  `Verdict`, three-valued, with the invariant that any dimension which is not
  `MEASURED` forces `INDETERMINATE`. This design adds no second path to a
  verdict.
- **`FeatureWorkflow._gate()` (`feature.py:1258`)** — FR-301's policy
  resolution, FR-302's `(gate, round)` identity and first-decision-wins, and
  FR-303's reminder / escalation / expiry timers, in one ~60-line method.
- **`channels/transport.py`** — sends signals and runs queries **by name** and
  imports nothing from `FeatureWorkflow`, as its docstring states.

**The problem:** `_gate` is a method on `FeatureWorkflow`, reaching into
`self._pending`, `self._gate_decisions`, `self._status`, `self._emit`,
`self._retain`, `self._notify`, and `self._wait_for_decision`
(`feature.py:775`). None of it is reachable from a second workflow, and the
FR-903 readiness gate needs exactly it.

---

## 2. Decisions

### D1 — The gate lives in `TriageWorkflow`, and the artifact carries the override

FR-903 describes the readiness gate as "blocking Tier 2", but Tier 2
(`AssessmentWorkflow`, E-45) does not exist. A gate that blocks nothing could
be deferred to its consumer. It is not, for two reasons: the audit trail is
cheapest to install while the artifact is small, and E-44 needs a human
"proceed" point on a not-ready repository *today*.

So triage always terminates with a verdict, and a human decision to proceed
anyway is recorded **on the artifact** as a `ReadinessOverride`. E-45's
admission rule is then one line it can compute without re-asking:

> proceed to Tier 2 iff `verdict is READY or override is not None`.

`ReadinessOverride.approved_by` records the *class* of approver
(`human` / `policy` / `timeout`) verbatim, so E-45 may narrow that rule to
human approvals if it wants to (§7).

### D2 — Extract a shared `GateHost`; do not write the gate twice

A ~40-line local gate inside `TriageWorkflow` would leave `feature.py`
untouched and carry zero regression risk. It would also state FR-302's
"first decision for `(gate, round)` wins" a second time — the exact shape of
the defect `2026-07-16-registry-drives-every-role` was written about, where an
invariant held only while two hardcoded registries happened to agree. The gate
is the one part of E-42 that is not new code but *shared* code.

`GateHost` is a mixin, not a base workflow. Verified against the installed SDK
rather than assumed: `temporalio/workflow/_definition.py:288` collects signal
and query definitions via `inspect.getmembers(cls)`, which walks the MRO, and
only `@workflow.run` must be defined on the concrete class (`_definition.py:128`).
So `submit_gate_decision`, `status`, `pending_gate`, and `pending_decisions`
are inherited and register correctly on both workflows.

### D3 — `_gate` stops taking `PipelineConfig`; `GateSettings` carries the three fields it needs

`_gate` reads exactly three config values: `cfg.gates`, `cfg.default_gate_policy`,
`cfg.gate_timeout_hours` (`models.py:934,948,976`). Taking the whole
`PipelineConfig` would drag roles, memory, research, benchmark and deploy
configuration into triage's input contract, none of which triage has any use
for.

`GateSettings` lives in **`models.py`**, beside `GateConfig` — not in
`workflows/gates.py`. `PipelineConfig.gate_settings()` returns one, and if the
type lived in `workflows/` then `models.py` would import from `workflows/`,
which points the dependency arrow the wrong way.

### D4 — The `FeatureWorkflow` couplings become three no-op hooks

`_gate` emits `GATE_AWAITED` / `GATE_DECIDED` into the retro trace (E-32) and
retains a `GATE_FEEDBACK` memory (FR-401). Triage has neither a `RunSummary`
nor a memory bank. Both collapse into:

```python
async def _on_gate_decided(self, name: str, round: int,
                           policy: GatePolicy,
                           decision: GateDecision) -> None:
    """Hook: what this workflow does with a decided gate. No-op by default."""
```

`FeatureWorkflow` overrides it with today's emit-plus-retain body. Because the
override needs memory config and `feature.py` threads `cfg` as a parameter
rather than holding it, `FeatureWorkflow.__init__` gains `self._cfg:
PipelineConfig | None`, assigned at the top of `run()`.

The `GATE_AWAITED` emit happens before the wait, so it stays a second hook,
`_on_gate_awaited(name, round)` — same no-op discipline.

**A third coupling, found while mapping the code for the plan:** `_notify`
(`feature.py:750`) also calls `self._emit`, four times, to trace
`GATE_NOTIFIED` — whether each configured route delivered. §5 lists `_notify`
as moving to `GateHost`, so it needs the same treatment:
`_on_notified(gate, reason, notifier, delivered, error)`, no-op on the base,
overridden by `FeatureWorkflow` to emit. Without it, `gates.py` would have to
import `RunEventKind` and every triage gate would append events to a trace
nothing reads.

Three hooks then, all no-op by default, all overridden in exactly one place.
`NOTIFY_ACT` (`feature.py:127`) moves to `gates.py` with `_notify`; it has no
other caller.

**`confidence` is a hook parameter, never instance state.** *Corrected
2026-08-09, post-implementation review.* `_gate` folds `confidence` into the
`GATE_DECIDED` event, and the first implementation stashed it on the instance
(`self._last_gate_confidence`) to get it across the hook boundary. That
reintroduces as shared state what was previously a local parameter: gates
interleave — wave mode runs `_dev_task` concurrently under `asyncio.gather` —
so a gate opening while another awaits a human would overwrite the stash and
silently drop `RunSummary.gates[].confidence`, which SC-6's calibration
compare reads. `_on_gate_decided` takes `confidence` as its fifth parameter
instead. (Contrast `_escalation_round`, where a shared counter is *correct*
precisely because it must be monotonic across concurrent tasks.)

### D5 — Top-level workflow, `sdlc triage`, local path only

Triage's value is standalone: an operator runs it on a repository they may
never build a feature in. Making it stage 0 of `FeatureWorkflow` would weld
Tier 0 onto a pipeline whose brownfield mode (FR-102) does not exist yet.

Input is a **path on disk**, because every E-41 activity takes `repo_dir` +
`commit_sha`. Cloning from a URL is FR-1003/E-59's job; operator-run on an
already-authorised local clone is precisely the trust boundary NFR-9 and
E-41 spec D2 describe.

**Workflow id: `triage-<slug(basename)>-<UTC timestamp>`.** *Corrected
2026-08-09, post-implementation review.* This spec originally said
`-<short-sha>`, which cannot be built: the sha is resolved by
`triage_resolve_commit` **inside** the workflow (D7), and the id must exist
before the workflow starts. The first implementation dropped the suffix
entirely, which was worse than either — Temporal refuses to start a workflow
whose id is already `RUNNING`, so a bare `triage-<slug>` meant a triage parked
on the readiness gate (`HARD` by default, 48h) blocked the next triage of that
repository, and E-44's assess → fix → **re-triage** loop is the first thing
that would have hit it. The timestamp supplies the distinctness the sha was
there to provide; the artifact still carries `commit_sha` for provenance.

### D6 — The build probe is on by default, and skipping it is honest, not special-cased

`triage_build_probe` is the one signal that executes the triaged repository's
own code as the worker user with network access. `--no-build-probe` gives an
operator a read-only first look at an unknown repository.

Skipping it needs **no change to `compute_readiness`**: the workflow
synthesizes a `SignalResult` for the skipped signal whose `metrics` carry
`buildable` and `runnable` as `Measurement.not_collected("build probe not run
(--no-build-probe)")`, and the existing rule returns `INDETERMINATE`. The
artifact therefore distinguishes "we did not look" from "we looked and it
failed", *and says which*, which is FR-915's whole point. See D8a for where
the workflow learns which keys a skipped signal owed.

Off-by-default was rejected: the default run could then never reach `READY`,
so the gate would fire on every invocation and the verdict most operators see
would carry no information.

### D7 — The commit is pinned once, by an activity that also detects the toolchain

`triage_resolve_commit` takes a `TriagePinInput(repo_dir, commit)` — a
dedicated type, because feeding `"HEAD"` into `TriageSignalInput.commit_sha`
would put an unresolved ref in a field whose whole contract is that it is
resolved. It runs `git rev-parse <commit>`, then `git ls-tree` +
`detect_with_marker_from_paths`, returning `TriagePin(commit_sha, toolchain)`.
One activity rather than two because `RepoTriage.toolchain` needs an answer and
every signal detects the adapter independently anyway.

Pinning once is what makes the artifact coherent: all seven signals read the
same tree, and every evidence citation resolves at the same `path@sha`.

### D8 — A failed signal activity is `not_collected`, not a failed run

E-41 spec D3 promises that "a signal that crashes or times out yields
`not_collected` for ITSELF while every other signal still reports". E-41
delivered half of that: each activity catches its own exceptions. A
**timeout**, a lost worker, or an exhausted retry still surfaces in the
workflow as an activity failure, which would fail the whole triage.

So each `execute_activity` call is individually wrapped, and a failure becomes
`SignalResult(signal=<id>, version=<registry version>, collected=
Measurement.not_collected("<id> activity failed: …"))`. This is the
workflow-side half of D3's promise; without it the promise is only half true.

The one exception is `triage_resolve_commit`: if the commit does not resolve,
the run fails. There is no honest artifact describing a tree we cannot read.

### D8a — `SignalSpec` declares which readiness keys a signal owns

D6's skip path and D8's failure path both need to answer the same question:
*which readiness dimensions did this signal owe?* Today that knowledge is
implicit — it lives inside each signal's `evaluate()` and is only ever
observed after the fact, by `compute_readiness` raising when two signals report
the same key.

`SignalSpec` (`triage/registry.py`) gains `readiness_keys: tuple[str, ...] = ()`:
`build_probe` owns `buildable` + `runnable`, `baseline` owns `tests_present`,
`scaffold` owns `structure_discernible` (E-41b moved it there). The workflow
reads that declaration to populate precise `not_collected` metrics on a skipped
or failed signal, instead of leaving the dimension unreported and the operator
reading the generic "no signal reported buildable".

This makes FR-902's one-implementation rule **declarative** rather than only
detectable. `compute_readiness`'s duplicate detection stays exactly as it is —
it is now a backstop against the declaration drifting from the code, which is a
better job than being the only statement of the rule.

### D9 — `REVISE` re-runs the fan-out at a freshly resolved commit

`REVISE` on a readiness gate has an obvious operator meaning: *"I just deleted
the committed `.env` — look again."* It re-resolves the commit and re-runs the
whole fan-out at round+1, bounded by `TriageInput.max_gate_rounds` (defaulting
to `PipelineConfig`'s 2, `models.py:973`, but read from the triage input — a
triage run has no `PipelineConfig`), with exhaustion escalating to a final
`HARD` gate — the same shape as `_revisable_stage`.

Round 2 therefore describes a **different commit** than round 1. That is
correct, not a leak: `RepoTriage.commit_sha` names which one, and a triage
pinned to a commit the operator has since fixed is not the question they are
asking.

### D10 — `SOFT` degrades to `HARD` with no special case, and `_revisable_stage` stays in `feature.py`

Triage is deterministic and produces no confidence score, so a `SOFT` policy
on `readiness` has nothing to auto-approve *with*. `_gate`'s existing SOFT
branch auto-approves only when handed an `auto_decision`; triage passes none,
so it waits. No code required — but the spec says so out loud, because a
config that silently means something other than it says is a defect.

For the same reason `_revisable_stage` (`feature.py:1319`) does **not** move to
`GateHost`: it is welded to `_auto_decision_for`, `_spec_summary`, and
artifacts carrying `.confidence`. Triage gets its own ~8-line loop. The shared
thing is `_gate` — the FR-302 invariant — not the loop around it.

### D11 — Result plus query; no durable store

`TriageWorkflow` returns `RepoTriage` and exposes a `triage()` query. The run's
Temporal history is the record (ADR-1). No board table, no `.sdlc/` export.

E-44's before/after delta compares two triage **run ids**, which it will have
anyway since it starts the second triage itself. A durable store belongs to the
first consumer that needs a cross-run read it cannot get from a workflow handle
— that is E-45, and it can add one against a contract that by then has a real
producer.

Writing `.sdlc/triage.json` into the triaged repository was rejected outright:
we were authorised to *read* that repository, and an artifact describing sha X
landing in the working tree invites exactly the drift E-41 avoided by reading
through git.

---

## 3. Module layout

```
src/sdlc/
  models.py                 # + GateSettings, + PipelineConfig.gate_settings()
  workflows/
    gates.py                # NEW — GateHost mixin (FR-301/302/303 mechanics)
    feature.py              # FeatureWorkflow(GateHost); gate methods removed
    triage.py               # NEW — TriageWorkflow(GateHost)
  triage/
    models.py               # + ReadinessOverride, + RepoTriage.override
    registry.py             # + SignalSpec.readiness_keys (D8a)
    activities.py           # + triage_resolve_commit
  worker.py                 # + TriageWorkflow, + triage_resolve_commit
  cli.py                    # + `triage` verb
```

`workflows/gates.py` imports `gate.py`, `pending.py`, `notify/`, and
`models.py`. It never imports `feature.py` or `triage.py`.

---

## 4. Contracts

### `models.py`

```python
class GateSettings(BaseModel):
    """The three fields a durable HITL gate reads. Extracted so GateHost does
    not depend on the feature pipeline's PipelineConfig."""
    gates: dict[str, GateConfig] = Field(default_factory=dict)
    default_gate_policy: GatePolicy = GatePolicy.HARD
    gate_timeout_hours: int = 48


class PipelineConfig(BaseModel):
    ...
    def gate_settings(self) -> GateSettings: ...
```

### `triage/models.py`

```python
class ReadinessOverride(BaseModel):
    """FR-903: an audited decision to proceed despite a verdict that is not
    READY. Local and pure -- this module must not import models.py, so
    GateDecision cannot appear here; TriageWorkflow maps one to the other."""
    approved_by: Literal["human", "policy", "timeout"]   # decided_by
    reviewer: str | None = None    # GateDecision.reviewer -- see FR-1004
    reason: str                    # GateDecision.comments
    decided_at: datetime
    gate_round: int


class RepoTriage(BaseModel):
    repo_dir: str
    commit_sha: str
    toolchain: str | None = None
    readiness: Readiness
    signals: list[SignalResult] = Field(default_factory=list)
    override: ReadinessOverride | None = None      # NEW
```

### `workflows/triage.py`

```python
class TriageInput(BaseModel):
    repo_dir: str
    commit: str = "HEAD"                # resolved to a sha by D7's activity
    build_probe: bool = True            # D6
    advisory_source: str = "none"       # E-41a: off by default, declared egress
    gates: GateSettings = Field(default_factory=GateSettings)
    max_gate_rounds: int = 2            # D9's bound
```

### `triage/activities.py`

```python
@dataclass
class TriagePinInput:
    repo_dir: str
    commit: str = "HEAD"        # an unresolved ref -- see D7

@dataclass
class TriagePin:
    commit_sha: str
    toolchain: str | None

@activity.defn
async def triage_resolve_commit(inp: TriagePinInput) -> TriagePin: ...
```

### `triage/registry.py`

```python
class SignalSpec(BaseModel):
    id: str
    version: int
    activity: str
    readiness_keys: tuple[str, ...] = ()   # D8a: which dimensions this signal owes
```

`build_probe` → `("buildable", "runnable")`; `baseline` → `("tests_present",)`;
`scaffold` → `("structure_discernible",)`; the other four → `()`.

---

## 5. The `GateHost` extraction

**Moves to `workflows/gates.py`, behaviour unchanged:**

| Member | Today |
|---|---|
| `_pending`, `_gate_decisions`, `_status` | `feature.py:550,552,561` |
| `_gate()` | `feature.py:1258` |
| `_wait_for_decision()` | `feature.py:775` |
| `_notify()` | `feature.py:750` |
| `submit_gate_decision` signal | `feature.py:824` |
| `status`, `pending_gate`, `pending_decisions` queries | `feature.py:839,843,847` |

**Signature change:** `_gate(name, cfg: PipelineConfig, …)` becomes
`_gate(name, settings: GateSettings, …)`. `FeatureWorkflow`'s call sites pass
`cfg.gate_settings()`. Everything else — `auto_decision`, `round`, `context`,
`confidence`, `default_policy` — is untouched.

**Stays in `feature.py`:** `_revisable_stage` (D10), `_retain`, `_emit`,
`_track_usage`, `answer_question` (clarify is a feature-pipeline concept), and
every stage method.

**`GateHost.__init__`** initialises the three fields it owns. `FeatureWorkflow.__init__`
calls `super().__init__()` and keeps the rest.

**The payoff, and it is not incidental:** because `channels/transport.py`
resolves signals and queries by name and imports nothing workflow-specific,
`sdlc approve --id triage-… --gate readiness`, `sdlc reject`, `sdlc status`,
and E-8's cross-run inbox all work against `TriageWorkflow` with **zero**
changes to the channel layer.

---

## 6. `TriageWorkflow` — the run

1. **Pin** — `triage_resolve_commit` → `TriagePin`. Failure fails the run (D8).
2. **Fan out** — one `asyncio.gather` over the signal activities, all pinned to
   `commit_sha`; `triage_build_probe` omitted when `build_probe=False` (D6).
   Three input shapes, not one: `TriageSignalInput` for the five plain signals,
   `TriageDependencyInput` for `triage_dependencies` (it carries
   `advisory_source`), `TriageProbeInput` for the build probe (it carries three
   step timeouts). The fan-out builds each explicitly rather than pretending
   one type fits all.
   Parallel is safe: six signals only *read* `repo_dir` through git, and the
   build probe clones into its own temp dir (E-41 spec D8), so nothing writes
   to the operator's checkout. Wall clock is the build probe either way.
   Each call is individually wrapped per D8, and a skipped or failed signal's
   owed readiness keys come from D8a's declaration.
3. **Compute** — `compute_readiness(signals)`, untouched.
4. **Assemble** — `RepoTriage(repo_dir, commit_sha, toolchain, readiness, signals)`.
5. **Gate** — §7.
6. **Return** the artifact; `triage()` serves it as a query.

**Activity policies:**

| Activity | `start_to_close` | `maximum_attempts` | Why |
|---|---|---|---|
| `triage_resolve_commit` | 2 min | 3 | Read-only, idempotent. |
| six read-only signals | 10 min | 2 | Deterministic; the retry covers FS/git blips only. |
| `triage_dependencies` | 15 min | 3 when `advisory_source != "none"` | The only signal doing network I/O. |
| `triage_build_probe` | sum of its step timeouts + 5 min | **1** | Its docstring: a ten-minute timeout retried three times is a thirty-minute triage, and a deterministic build failure does not become a success on attempt two. |

---

## 7. The readiness gate (FR-903)

`verdict is READY` → no gate; final status `triaged:ready`.

Otherwise open `readiness` at round 1 through the inherited `_gate`, surfacing
a `StageGatePending` whose `spec_summary` names the verdict, the dimensions
that blocked it, and finding counts by severity. Reusing the existing variant
rather than adding a fifth to `pending.py` keeps `channels/contract.py`
untouched — a triage gate genuinely *is* a stage gate with a summary.

| Outcome | Effect | Final status |
|---|---|---|
| `APPROVE` | `ReadinessOverride` recorded on the artifact | `triaged:<verdict>+override` |
| `REJECT` | No override | `blocked:readiness` |
| `REVISE` | Re-resolve + re-run the fan-out at round+1 (D9) | — |
| timeout | The existing FR-303 `on_timeout` path produces an `APPROVE` or `REJECT` decision with `decided_by="timeout"` | whichever of the two rows above that outcome selects |

`TriageInput.gates` defaults to an empty `GateSettings`, so `readiness` is
unnamed and falls back to `default_gate_policy` — `HARD`.

**Who approved matters, and the artifact must not blur it.** `_gate` can
produce an approving decision three ways, and `GateDecision.decided_by`
(`models.py:697`) is already exactly a three-valued `Literal["human",
"policy", "timeout"]` naming which: a human signalled, the policy was `OFF`
and no human ever saw it, or the gate expired under `on_timeout=APPROVE`.

All three record a `ReadinessOverride` — one rule, no special cases — and
`approved_by` carries `decided_by` **verbatim**, so `"policy"` and
`"timeout"` are legible as non-human on the face of the artifact. E-45 is free
to narrow its admission rule to `approved_by == "human"`; what this design
refuses to do is discard the distinction, or let a config default silently
manufacture something that reads like a human decision.

**The operator's identity is a separate, weaker field.** `decided_by` is the
*class* of decider, not a principal; the identity lives in
`GateDecision.reviewer`, which is optional and self-asserted — the gap FR-1004
exists to close. `ReadinessOverride.reviewer` mirrors it and inherits that
weakness rather than hiding it. An assessment bundle that claimed a named
human approved a not-ready repository, on the strength of a field anyone can
set, would be worse than one that says `approved_by="human"` and leaves the
principal unproven.

---

## 8. CLI surface

```
sdlc triage --repo <path> [--commit HEAD] [--no-build-probe]
            [--advisory-source osv]
sdlc triage show --id <workflow-id>       # prints the triage() query result
```

`approve` / `reject` / `revise` / `status` / `inbox` need no changes (§5).
`_needs_temporal_client` gains nothing: `triage` needs the client.

---

## 9. Error handling & determinism

- `asyncio.gather` over activities is replay-safe: commands are ordered by
  creation and results are applied in that order. The `build_probe=False`
  branch changes the command set, but it is input-driven, not clock- or
  environment-driven.
- Three failure classes, three answers: a signal raising internally →
  `not_collected` (E-41); a signal timing out or losing its worker →
  `not_collected` synthesized by the workflow (D8); an unresolvable commit →
  the run fails (D8).
- No `Measurement.measured(0.0)` is ever synthesized on a failure path. The
  `SignalResult` validator already rejects `NOT_COLLECTED` carrying findings.

---

## 10. Testing

**Regression proof for the extraction** — these pass untouched:
`test_gate_decision`, `test_gate_notifications`, `test_gate_timeout_action`,
`test_gate_revision_loop`, `test_soft_gate_auto_approval`, `test_budget_gate`,
`test_tool_approval_gate`, `test_merge_gate_wiring`.

**One expected edit, not collateral damage:** `tests/test_pending_wiring.py:30`
asserts `"def pending_decisions("` and `"self._pending.pop("` appear in
`feature.py`'s *source text*. Both move to `gates.py`, so that test is
re-pointed. (`test_gate_accepts_context_param` survives — 
`inspect.signature(FeatureWorkflow._gate)` resolves through the MRO.
`test_soft_gate_auto_approval` survives — `_revisable_stage` does not move.)

**New tests**, following `test_deployment_workflow.py`'s split of pure helpers
tested directly and sequencing tested through the workflow:

- `READY` → no gate opened; `_pending` empty at completion.
- `NOT_READY` → one `StageGatePending` keyed `readiness#1`; `APPROVE` records
  the `ReadinessOverride` with `approved_by` / `reason` / `gate_round`;
  `REJECT` yields `blocked:readiness` and `override is None`.
- `build_probe=False` → `buildable` / `runnable` `not_collected` with the
  skip named in the detail string (D6/D8a), verdict `INDETERMINATE`, and a
  `SignalResult` for `build_probe` present in `signals` rather than absent.
- `approved_by` distinguishes the three approval sources: a human's identity,
  `"policy"` under `OFF`, `"timeout"` under `on_timeout=APPROVE` (§7).
- `SignalSpec.readiness_keys` agrees with what the signals actually report:
  for each spec, running its signal on a fixture yields metrics whose
  readiness keys are exactly the declared tuple. This is the test that keeps
  D8a's declaration from drifting from the code.
- A signal activity that times out → `not_collected` for that signal, the other
  six still reported (D3's promise, tested at the layer where it was previously
  only half-kept).
- `REVISE` → fan-out runs twice, second `RepoTriage` carries the re-resolved
  sha; `max_gate_rounds` exhaustion escalates to a final gate.
- `sdlc approve --id triage-… --gate readiness` resolves and signals through
  `channels/transport` unmodified — §5's claim tested, not asserted.
- `PipelineConfig.gate_settings()` round-trips the three fields; `GateSettings`
  defaults match `PipelineConfig`'s.

---

## 11. Out of scope

Memoization on `(tree hash, signal version)` — **E-46**; the `SIGNALS`
registry's `version` field already exists for it · mechanical fix runs and the
before/after delta — **E-44** · cloning from a URL — **FR-1003 / E-59** · any
Tier 2 consumer of the verdict or override — **E-45** · a durable triage store
— **D11** · any LLM call.

---

## 12. Roadmap consequences

On landing:

- **E-42** closes.
- **FR-901** closes — the triage stage and its readiness verdict exist, and
  complete on repositories that do not build.
- **FR-903** closes — the gate resolves through FR-301/302, overridable by an
  audited decision recorded on the artifact.
- **ADR-18** becomes enforceable rather than aspirational: E-45 has a computable
  admission rule (D1).
- **US-8** gains its verdict half; its "checkable hygiene list" half is E-44.
- **P5** moves to partial with only **E-44** outstanding.
- **NFR-9** unchanged in substance but now reachable by an operator command:
  `sdlc triage` executes a foreign repository's code by default. Operator-run
  only until E-57/E-21.
