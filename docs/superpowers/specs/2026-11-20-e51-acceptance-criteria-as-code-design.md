# E-51 — Acceptance criteria as code (FR-918) — design

| | |
|---|---|
| Requirements | FR-918 (with FR-915's three-state discipline throughout); FR-106's `CheckResult` |
| Item | `docs/roadmap/tier-2-edcr.md` E-51 → the `FINISH` stub (`PHASE_OWNER`, `workflows/assessment.py`) |
| Approach | **Report-only** (owner-approved 2026-11-20; the alternative is §7) |
| Does not cover | E-52 (reports, evidence bundle, `manifest.json`, handoff bundles — BrownKit `/finish` Parts C+D), E-53 (seeds), E-55 (budgets), E-56 (`/enrich`) |

## 1. Intent and why

BrownKit's `/finish` grades its own 14 acceptance criteria with the same model
that produced the artifacts being graded, and audits cross-references by asking
an LLM to check its own citations. Tier 2's whole reason to exist is that those
become `CheckResult`s computed by pure code from typed artifacts
(`docs/roadmap/tier-2-edcr.md` preamble). E-51 ports `/finish` **Part A (the 14
criteria)** and **Part B (the cross-reference audit)** — nothing else. The
`FINISH` phase body in `AssessmentWorkflow._finish` stops being `unbuilt()`.

An assessment that finishes now says, on the artifact itself, which criteria
passed, which failed and why, and which could not be evaluated because the
phase that owes them has not landed — the same honesty `PHASE_OWNER` already
gives the DAG.

## 2. Goals / non-goals / anti-goals

**Goals**

- The 14 terminal criteria, each a `gate.CheckResult` computed by a pure
  function over the assembled typed artifacts (`ScanResult`, `CapabilityMap`,
  `UnifiedRiskMap`, `RiskGateReport`) — never asserted by the agent that
  produced them (FR-918's SHALL).
- Per-phase exit criteria for the built phases (scan, discover, assess) as
  `CheckResult`s in the same report.
- Cross-reference integrity — every `bc_id`, threat, vulnerability, and
  testability identifier cited anywhere in the typed artifacts resolves to a
  record in the same run — as an **absolute** check (FR-918's own word).
- A `FinishReport` as its own typed field on `Assessment` (no generic payload
  bag — the FR-921 house rule every prior E-item restates).
- `PHASE_OWNER` loses its `FINISH` entry; finish measures; `terminal_status`
  needs no edit (D6).

**Non-goals**

- No new workflow gate, no new DAG stage, no new terminal status. E-50 owns
  gating; a failed absolute criterion reports on the artifact and is carried by
  E-52's eventual bundle/manifest. (§7 records the rejected alternative.)
- No LLM "needs-review" layer (§6, FD5). No proposer role is added.
- No repair of broken references (FD6): BrownKit edits its markdown in place;
  a typed artifact already emitted is history — a broken citation fails its
  check and names the producer, it is not rewritten.
- No handoff bundles, no `manifest.json` (Parts C+D → E-52/FR-704).

**Anti-goals**

- A criterion that reads as `passed` when its producer never ran. Producer
  absent ⇒ the criterion is **owed**, naming the E-item that owes it — never
  pass, never fail (FR-915).
- Grading anything by reading the artifact's prose back to itself.

## 3. Constraints

- **Purity.** The finish package (`src/sdlc/assessment/finish/`) imports
  Pydantic models, `measurement.py`, and `gate.py` only — never
  `assessment/models.py` (the aggregator), `activities.py`, or `temporalio`;
  exactly the rule written on `gates/models.py:3-7`. A dependency here would be
  a reviewable import.
- **Determinism (NFR-10).** Every sequence in `FinishReport` is sorted and
  deduped, enforced by model validators that raise rather than repair — the
  `RiskGateReport` precedent (`gates/models.py:43-67`).
- **Three states, not two.** `CheckResult.passed` is a bool; a criterion whose
  producer did not collect is therefore *not* a failing `CheckResult` — it is
  an owed row (§5, FD2).
- **Replay safety.** Finish computes **inline** (amended 2026-11-20, the E-50
  `evaluate()` precedent — owner-approved): a pure call inside `_finish` adds
  **zero workflow commands**, exactly as the pre-E-51 stub issued zero, so the
  replay corpus (including `assessment_discover_risk.json`) stays green with no
  patch marker and no new wire name. A pre-E-51 history replays finish
  computing the report on replay; commands match, and the payload field is
  defaulted for deserialization.

## 4. The 14 criteria, mapped

BrownKit's table (`commands/finish.md`) re-expressed over Kroker's typed
artifacts. Criterion ids are stable strings (`c01`…`c14`) so E-52's manifest
can join them; names never rename.

| # | BrownKit criterion | Kroker source (pure read of) | Owner when absent |
|---|---|---|---|
| c01 | Security context per capability | `Capability.security` / `.sensitivity` non-empty or honest (D6) | discover |
| c02 | QA context per capability, not-collected marked | `Capability.testability` / `.coverage` (D6a) | discover |
| c03 | STRIDE per capability | every `CapabilityRisk.threats` (validator already forces all six, in order) covering the locked L1 set | assess |
| c04 | Every vulnerability mapped to code and capability | every `Vulnerability` carries `path` + non-empty `evidence`, lives on a `CapabilityRisk` | assess |
| c05 | Security scoring complete | every `CapabilityRisk.security` composite MEASURED (or partial-with-reason) | assess |
| c06 | QA scoring complete **or explicitly unknown** | `CapabilityRisk.qa` — RD3 makes this partial on every run until E-56; an honest partial-with-reason **passes** c06 (FD8) | assess |
| c07 | Unified composite with 1–3 drivers | every `CapabilityRisk.unified` MEASURED with `drivers` (schema bounds 1–3). RD3: `unified` is not_collected on every run until E-56, so c07 **defers** — owed naming E-56 — exactly as E-50 deferred its composite-threshold clauses (FD12) | assess / **E-56** |
| c08 | Findings traceable with confidence | verification collected: `CapabilityMap.total_references > 0` and the citation guard did not trip (it already fails closed) | discover/assess |
| c09 | Cross-capability risks identified | `UnifiedRiskMap.system` collected (shared vulns, cascades, boundaries, escalation) | assess |
| c10 | File→capability coverage ≥ target | `AttributionReport.meets_floor` (already derived; `not_collected` never passes — its own validator). Under FD11: discover absent ⇒ owed; discover measured with a not_collected `AttributionReport` (e.g. unread blobs) ⇒ **evaluated fail** carrying the reason | discover |
| c11 | Blueprint comparison complete | `BlueprintComparison.collected` (MISSING gaps are context, not failure — E-48 D8) | discover |
| c12 | Domain model with code traceability | `DomainModel` collected; every `Capability.member_paths` non-empty | discover |
| c13 | All five reports | the REPORT phase body | **E-52 (owed)** |
| c14 | Evidence preserved, full cross-referencing | the Part B walk (§5): c14 is the derived AND over the evaluated xref domains — pass when every domain evaluated clean, fail naming the broken citations, owed while any xref domain's producer is absent | this item |

`c10` is ADVISORY (the floor is a configured target, and small repositories are
legitimately below it — scan D11's ruling); `c14` (and the walk beneath it) is
ABSOLUTE, per the PRD's own word. The remaining classifications are the
builder's table, defaulting to ABSOLUTE for structural presence (c01–c04,
c07–c09, c12) and ADVISORY where BrownKit accepts a documented shortfall
(c05/c06 honesty, c11).

## 5. Shape

```python
# src/sdlc/assessment/finish/models.py (pure; imports gate.py + measurement.py)
class FinishReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    criteria: tuple[CheckResult, ...] = ()   # the 14, evaluated ones only
    owed: tuple[str, ...] = ()               # "c13_five_reports: not collected (E-52)",
                                             # "c07_unified_drivers: deferred (E-56)",
                                             # "exit:report:…: not collected (E-52)"
    exits: tuple[CheckResult, ...] = ()      # "exit:scan:…", "exit:discover:…", …
                                             # and "xref:<domain>" — finish's own exits
    # sorted + deduped by validators that raise (NFR-10)

    @property
    def passed(self) -> bool:                # derived: every ABSOLUTE criterion passed
        ...
```

- **Carrier** (FD2): evaluated criteria are `CheckResult`s; a criterion whose
  producer did not collect is a row in `owed` — the `RiskGateReport.deferred`
  precedent, promoted to a first-class field because the 14 are a fixed
  manifest whose every member must stay addressable.
- **Three-state rule** (FD11, the load-bearing one): a criterion's state
  derives from its inputs, in this order —
  1. *producer phase absent* (unbuilt, or built-but-degraded: `no_discover`,
     `no_assess`, an unadmitted run) ⇒ **owed**, naming the owner — the E-item
     for an unbuilt phase, else the phase and its `not_collected` reason
     verbatim. Never pass, never fail.
  2. *producer phase measured but the specific sub-artifact is not_collected*
     (discover measured, `AttributionReport` not_collected because blobs were
     unreadable) ⇒ **evaluated fail** carrying that reason — a real finding,
     FR-915's "never pass" applied to a gap, not an absence.
  3. *inputs measured* ⇒ evaluated pass/fail by predicate.

  `FinishReport.passed` is therefore reachable only on runs whose absolute
  criteria were all evaluable; a degraded run reports owed rows, not red ones.
- **No synthesis** (FD3): unlike `MERGE_REQUIRED_CHECKS`, a missing producer is
  the *owed* state, not MISCONFIGURED. The manifest pin is computed over `c*`
  ids only: criteria named `c…` plus owed rows whose id starts `c` must total
  exactly 14, pinned by test. (`exit:*` and `xref:*` rows live outside the
  pin — FD14.)
- **Per-phase exits** (FD4): a small seed list the builder finalizes —
  scan: thirteen signal rows report, candidates non-empty (ADVISORY);
  discover: identity lock held, all files bucketed (orphan classification
  complete), ownership resolved-or-surfaced; assess: risk map covers the locked
  set, judgment measured-or-degraded-with-reason; report/generate: **owed rows
  naming E-52** (owed is not `CheckResult`-shaped, which is why they are rows
  in `owed`, not `exits`). `exit:finish:*` is the 14 plus the walk.
- **Cross-reference walk** (FD4, FD15): one ABSOLUTE `CheckResult` per citation
  domain — `xref:bc_ids`, `xref:vulnerability_keys`, `xref:capability_edges`
  (walked over the STORED projections — `SharedVulnerability.bc_ids`, `Cascade`
  paths, `TrustBoundary` source/target, `EscalationPath` paths — since
  `CapabilityEdge` itself is deliberately not stored), and
  `xref:threat_vulnerability_keys`. The census covers **structured, id-typed
  fields only**: `RiskGateReport` prose (`detail`/`deferred`/`reasons`) is out
  of scope by construction — walking it would mean parsing strings, which is
  the "reading prose back" anti-goal; `FindingDisposition` is not on the
  `Assessment` and is likewise out. A domain whose producer is absent is owed
  (FD11 rule 1); zero citation sites under a *measured* producer passes — the
  producer measured and cited nothing, which is true, not vacuous. Detail
  lists broken citations, sorted, bounded. `risk/apply.py:87` already enforces
  this where references are *created*; the walk is the belt-and-suspenders
  audit over the final artifact, which is what BrownKit Part B is.

**Workflow wiring** (the only workflow edit):

- `evaluate_finish` is a **pure inline call** inside `_finish` (the E-50
  `evaluate()` precedent — no activity, no worker registration, no patch
  marker), wrapped in try/except: a pure-code failure is a phase-level
  `not_collected` with the reason, never a half-graded report — mirroring
  `_discover`'s `build_map` guard.
- **Short-circuit** (FD13): finish evaluates only if at least one of scan,
  discover, risk measured; otherwise it reports phase-level not_collected
  naming the first absent phase's reason (scan → discover → risk,
  deterministically). Without this, a measuring finish over an all-degraded run
  would flip `terminal_status` from `admitted:no-phases-implemented` to
  `assessed:partial` with no edit to `terminal_status` — a run that assessed
  nothing must not read as one that assessed something. With it, `NO_PHASES`
  keeps its meaning and finish measures exactly when there is something to
  grade.
- `Assessment` gains `finish: FinishReport | None = None` (defaulted —
  pre-E-51 histories deserialize unchanged).
- `PHASE_OWNER` drops `FINISH`; the stub count goes 3 → 2 (report, generate —
  both E-52). `terminal_status` is otherwise untouched: finish measuring moves
  an admitted run toward `ASSESSED`, and stays `PARTIAL` while report/generate
  are owed — correct and honest.

## 6. Decisions

- **FD1 — report-only** (owner-approved): FR-918 says *evaluate*, not gate;
  E-50 owns gating; zero new gate surface.
- **FD2 — `criteria` + `owed` + `exits`** on one frozen report; no changes to
  `gate.CheckResult` (FR-106's shared model stays shared).
- **FD3 — owed ≠ fail ≠ pass**, and the manifest total is pinned by test.
- **FD4 — exits carry a `exit:<phase>:` name prefix; the xref walk is
  per-domain ABSOLUTE checks.**
- **FD5 — no needs-review LLM layer**: every BrownKit "needs-review" judgment
  determinizes (driver specificity is schema-enforced upstream; sub-floor
  coverage with documented orphans is ADVISORY-fail with the attribution
  summary in detail, not a judgment call).
- **FD6 — no repair**: broken citations fail and name the producer; typed
  artifacts are immutable history.
- **FD7 — placement**: `src/sdlc/assessment/finish/` (`models.py`, `checks.py`,
  `crossref.py`), mirroring `gates/`.
- **FD8 — c06 honest partial passes** (BrownKit: "explicitly `unknown` with a
  reason"), until E-56 gives the QA composite its source.
- **FD9 — c10 ADVISORY, xref ABSOLUTE** (PRD's word).
- **FD10 — criterion ids `c01`…`c14` are wire names**; never renamed, the
  `GUARD_PATCH_ID` rule.
- **FD11 — three-state rule** (builder-check Q2): producer phase absent ⇒ owed
  (E-item for unbuilt, phase+reason verbatim for built-but-degraded); producer
  measured but the criterion's specific sub-artifact not_collected ⇒ evaluated
  fail carrying the reason; inputs measured ⇒ pass/fail by predicate.
- **FD12 — c07 defers to E-56** (builder-check Q3), mirroring E-50's deferred
  composite-threshold clauses; c05 evaluates normally (its sources exist), c06
  passes on honest partial per FD8 — each criterion follows its BrownKit
  wording, which blesses honest-unknown for QA (c06) but requires drivers
  (c07).
- **FD13 — finish short-circuits** (builder-check Q4): evaluates only when at
  least one of scan/discover/risk measured; else phase-level not_collected
  naming the first absent phase. `NO_PHASES` must not flip to `PARTIAL`.
- **FD14 — schema homes** (builder-check Q5): `xref:*` rows live in `exits`
  (finish's own exit criteria); owed `exit:*` rows live in `owed`; the
  14-manifest pin counts `c*` ids only.
- **FD15 — the xref census is typed-ids only** (builder-check Q6): structured
  id-typed fields; gate-report prose and `FindingDisposition` are out of scope
  by construction; `CapabilityEdge` is walked via its stored projections.
- **FD16 — inline, no patch marker** (amended 2026-11-20 after approval,
  owner-approved): `evaluate_finish` runs inline like E-50's `evaluate()`,
  adding zero workflow commands, so no `finish-e51` wire name exists. Had the
  activity shape been kept, SG-2 would have required the marker.
- **FD17 — c08's predicate** must not fail a legitimate baseline-only run:
  "every proposer reference verified, guard not tripped" — zero references
  under a measured producer with the judgment layer off is recorded, not
  failed; the exact phrasing is builder's (§8), the trap is named here.

## 7. Approaches

1. **Report-only (chosen).** A `FinishReport` on the artifact; absolute
   failures fail their criterion visibly; nothing halts. Matches FR-918's
   wording, keeps one gate owner (E-50), zero workflow semantics beyond filling
   the stub. The failed absolute criterion still cannot hide: it is on the
   artifact, and E-52's manifest will carry it.
2. **Finish gates completion** (rejected). A broken xref degrades the terminal
   status (a new `assessed:degraded`) or opens a second human gate. Catches a
   broken bundle harder, but duplicates E-50's gate machinery and mints a new
   status string no owner decision has asked to spend. Revisit when E-52's
   bundle exists if a customer surface needs it.

## 8. What's left to the builder

- Final per-phase exit criterion list (seed in §5) and the classification table
  (defaults in §4).
- Exact citation-site census for the xref walk within FD15's scope (structured
  id-typed fields of the stored projections; sites enumerated and pinned by
  test).
- Test layout: `tests/test_assessment_finish_*.py` — fast tier for pure
  checks/xref/orchestration, temporal tier for the wired `_finish`
  (measured end-to-end, inline-failure degrade, short-circuit), and the
  default-tier replay corpus staying green with zero new commands.
- The plan (writing-plans skill) splits this the way E-46/E-48/E-49 split —
  likely contracts+criteria, then xref walk+exits, then wiring.

## 9. Verification sketch

Fast tier: pure criteria over synthetic artifacts (one fixture per criterion
state: pass / fail / owed), sortedness validators, manifest-total pin over
`c*` ids, the default-tier replay corpus green (zero new commands). Temporal
tier: `_finish` measured end-to-end on an admitted run; an inline failure
degrades to phase-level not-collected; the all-degraded short-circuit keeps
`NO_PHASES`; `PHASE_OWNER` structural test drops its FINISH row; a recorded
pre-E-51 history deserializes with `finish=None` (or computes on replay —
commands are unchanged either way). `check_file_size.py` clean.
Close-out per house rules: FR-918 row, tier-2 E-51 entry, log prepend.
