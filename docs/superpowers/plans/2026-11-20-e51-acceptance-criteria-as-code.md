# E-51 — Acceptance Criteria as Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FINISH phase — the 14 EDCR acceptance criteria, per-phase exit criteria, and the cross-reference walk, as pure `CheckResult`s in a `FinishReport` on the `Assessment` artifact (FR-918).

**Architecture:** A new pure package `src/sdlc/assessment/finish/` (`models.py` contracts, `crossref.py` xref walk, `checks.py` the 14, `exits.py` phase exits, `__init__.py` orchestration) composed by one inline pure call inside `AssessmentWorkflow._finish` — the E-50 `evaluate()` precedent: no activity, no worker registration, no patch marker, zero new workflow commands.

**Tech Stack:** Python 3.13, Pydantic v2 (frozen models, raising validators), pytest (fast + temporal tiers), Temporal workflow replay.

**Spec:** `docs/superpowers/specs/2026-11-20-e51-acceptance-criteria-as-code-design.md` — the plan argues from it; executors read both. FD-numbers below refer to its §6.

## Global Constraints

- Purity: nothing in `src/sdlc/assessment/finish/` imports `assessment/models.py`, `activities.py`, `temporalio`, or any workflow module — Pydantic, `..measurement`, `...gate` only (spec §3).
- NFR-10: every sequence on `FinishReport` is sorted and deduped, enforced by validators that **raise**, never repair (`gates/models.py` precedent).
- FR-915 three-state (FD11): producer phase absent ⇒ owed; producer measured but the criterion's sub-artifact not_collected ⇒ evaluated fail; inputs measured ⇒ pass/fail. Owed never passes and never fails.
- Wire names — `c01…c14` criterion ids, `xref:*` domains, `exit:*` names (below) — are never renamed once landed.
- Owed row format: `f"{id}: not collected ({owner})"` (or `: deferred (E-56)` for c07), owner = an E-item id or `f"{phase}: {reason}"` with the phase's not_collected reason verbatim.
- 1000-line file ceiling (`uv run python scripts/check_file_size.py` must stay exit 0).
- Tests run via `uv run pytest`; the default tier is the fast tier; temporal tests via `-m temporal`.
- No new dependencies; no edits to `gate.py` (`CheckResult` stays FR-106's shared model).

## Review Focus

The five input classes the spec implies that no ordinary task exercises; each is pinned by the named test in its owning task.

1. A cited id that does not resolve (discover/risk measured, a citation dangles) → ABSOLUTE fail naming the citation — `test_broken_bc_citation_fails_absolute` (Task 2).
2. All-degraded run (no phase measured) → finish not_collected and `terminal_status` stays `admitted:no-phases-implemented` — `test_all_degraded_run_keeps_no_phases` (Task 6).
3. Baseline-only run (`propose_discover=False`, zero references) → c08 records the mode, does not fail — `test_c08_baseline_run_records_not_fails` (Task 3).
4. A directly-constructed `FinishReport` with unsorted or duplicate rows → validators raise — `test_unsorted_rows_raise` / `test_duplicate_names_raise` (Task 1).
5. Measured producer, not_collected sub-report (discover measured, `AttributionReport` not_collected) → c10 evaluated fail carrying the reason, not owed — `test_c10_subreport_not_collected_fails_not_owed` (Task 3).

---

### Task 1: `FinishReport` contracts and the manifest

**Files:**
- Create: `src/sdlc/assessment/finish/__init__.py` (empty re-export shell for now)
- Create: `src/sdlc/assessment/finish/models.py`
- Test: `tests/test_assessment_finish_models.py`

**Interfaces:**
- Consumes: `gate.CheckResult`, `measurement.Measurement`.
- Produces (later tasks rely on these exactly):
  - `CRITERIA_MANIFEST: tuple[str, ...]` — the 14 wire names, in id order:
    `c01_security_context, c02_qa_context, c03_stride_per_capability, c04_vulnerabilities_mapped, c05_security_scoring, c06_qa_scoring, c07_unified_drivers, c08_findings_traceable, c09_cross_capability_risks, c10_coverage_floor, c11_blueprint_comparison, c12_domain_model_traceability, c13_five_reports, c14_cross_reference_integrity`
  - `class FinishReport(BaseModel)` — `model_config = ConfigDict(frozen=True, extra="forbid")`; fields `collected: Measurement`, `criteria: tuple[CheckResult, ...] = ()`, `owed: tuple[str, ...] = ()`, `exits: tuple[CheckResult, ...] = ()`; property `passed: bool` = every row in `criteria + exits` with `classification is CheckClass.ABSOLUTE` has `passed=True` (owed rows are not rows; they never fail it).

- [ ] **Step 1: Write the failing tests** — `tests/test_assessment_finish_models.py`:
  - `test_manifest_has_the_fourteen` — `len(CRITERIA_MANIFEST) == 14`, ids unique, each starts `c` + two digits, `c01`…`c14` prefix order matches.
  - `test_unsorted_rows_raise` / `test_duplicate_names_raise` — constructing `FinishReport` with `criteria` out of name order (or a duplicate name; same for `exits`, and for `owed` unsorted/duplicated) raises `ValidationError`.
  - `test_passed_reads_only_absolute_rows` — one passing ABSOLUTE + one failing ADVISORY → `passed is True`; one failing ABSOLUTE → `False`; empty report (no rows) → `True` (nothing evaluated, nothing failed — orchestration guarantees rows exist before `passed` is meaningful).
  - `test_manifest_is_frozen_tuple` — `CRITERIA_MANIFEST` is a `tuple` (not list).

- [ ] **Step 2: Run** `uv run pytest tests/test_assessment_finish_models.py -q` — expect FAIL (module missing).

- [ ] **Step 3: Implement** `models.py` — docstring states the purity rule and FD2/FD3/FD11 in three lines; `CRITERIA_MANIFEST`; `FinishReport` with two `model_validator(mode="after")`s (one for `criteria`/`exits` sorted-by-name + unique, one for `owed` sorted + deduped), each raising with the NFR-10 rationale sentence used by `RiskGateReport`'s twins; `passed` property as specified above.

- [ ] **Step 4: Run** the test file — PASS. Also `uv run pytest tests/test_assessment_models.py -q` (aggregator untouched yet, must stay green).

- [ ] **Step 5: Commit** — `feat(assessment): E-51 finish contracts — FinishReport, the 14-criterion manifest, NFR-10 validators`

### Task 2: the cross-reference walk

**Files:**
- Create: `src/sdlc/assessment/finish/crossref.py`
- Test: `tests/test_assessment_finish_crossref.py`

**Interfaces:**
- Consumes: `Task 1` (none of it, actually — only `gate` + the discover/risk models), `discover.map.CapabilityMap`, `risk.models.UnifiedRiskMap`, `measurement.{CollectionState, Measurement}`.
- Produces:
  - `def xref_domains(*, discover: CapabilityMap | None, discover_state: Measurement, risk: UnifiedRiskMap | None, risk_state: Measurement) -> tuple[tuple[CheckResult, ...], tuple[str, ...]]`
  - Domain names (wire): `xref:bc_ids`, `xref:vulnerability_keys`, `xref:capability_edges`, `xref:threat_vulnerability_keys` — all `CheckClass.ABSOLUTE` (FD9).
  - Citation census (FD15 — structured id-typed fields only): records for `bc_ids` = the map's locked `Capability.bc_id` set; citing sites = every `CapabilityRisk.bc_id`, `SharedVulnerability.bc_ids`, `Cascade.path` entries, `TrustBoundary.source_bc_id`/`target_bc_id`, `EscalationPath.path` entries. Records for `vulnerability_keys` = union of `CapabilityRisk.vulnerabilities[].key`; citing sites = `ThreatAssessment.vulnerability_keys` and `SharedVulnerability.vulnerability_keys`. `xref:capability_edges` = every bc_id in the stored projections resolves to a locked capability (both endpoints). `xref:threat_vulnerability_keys` = every `ThreatAssessment.vulnerability_keys` member resolves to a vulnerability key of the SAME `CapabilityRisk` row.

- [ ] **Step 1: Write the failing tests** — `tests/test_assessment_finish_crossref.py`, fixtures built with the models' minimal constructors (reuse existing fixture helpers from `tests/test_risk_apply.py`/`tests/test_assessment_models.py` where importable):
  - `test_clean_map_passes_all_domains` — 2 capabilities, one shared vuln, one cascade path, one threat citing an existing key → four rows, all `passed`, all ABSOLUTE.
  - `test_broken_bc_citation_fails_absolute` — a `SharedVulnerability.bc_ids` containing `BC-099` (no such capability) → that domain's row `passed is False`, `detail` contains `BC-099`, classification ABSOLUTE.
  - `test_zero_citation_sites_under_measured_producer_passes` — risk measured, no citations at all → all domains pass (true, not vacuous — FD15).
  - `test_producer_absent_is_owed` — `discover_state=Measurement.not_collected("...")`, `discover=None`, risk present → domains whose records are gone return owed rows `"xref:bc_ids: not collected (discover: …)"` citing the reason verbatim; citing-side-only absence (risk absent, discover present) → owed naming `risk`.
  - `test_gate_prose_is_not_walked` — a synthetic check string in no field (assert the module reads only the census fields; simplest form: a `CapabilityMap` whose `advisories` prose mentions `BC-099` does NOT fail any domain).

- [ ] **Step 2: Run** — FAIL (module missing).

- [ ] **Step 3: Implement** `crossref.py` — a `_records`/`_cites` helper pair per domain, one `build_check` per domain (detail joins broken citations `sorted`, truncated at ~300 chars), owed formatting per the Global Constraints. Docstring cites FD4/FD15 and `risk/apply.py:87` as the construction-site guard this walk audits.

- [ ] **Step 4: Run** — PASS; `uv run pytest tests/test_risk_apply.py -q` stays green.

- [ ] **Step 5: Commit** — `feat(assessment): E-51 cross-reference walk — four ABSOLUTE domains over typed ids, owed on producer absence`

### Task 3: the 14 criteria

**Files:**
- Create: `src/sdlc/assessment/finish/checks.py`
- Test: `tests/test_assessment_finish_criteria.py`

**Interfaces:**
- Consumes: Task 2's `xref_domains` (passed in, not called — orchestration calls it once), `scan.models.ScanResult`, the discover/risk models, `Measurement`/`CollectionState`.
- Produces:
  - `def evaluate_criteria(*, scan: ScanResult | None, scan_state: Measurement, discover: CapabilityMap | None, discover_state: Measurement, risk: UnifiedRiskMap | None, risk_state: Measurement, xref_checks: tuple[CheckResult, ...], xref_owed: tuple[str, ...]) -> tuple[tuple[CheckResult, ...], tuple[str, ...]]`
  - Classifications: ABSOLUTE = c01–c04, c07, c08–c09, c12, c14; ADVISORY = c05, c06, c10, c11, c13 (c13 is always owed today; classification still declared for E-52).
  - State mapping (spec §4 table is authoritative; predicates at a glance):
    - c01/c02 — every `Capability.security`/`.sensitivity` (c01), `.testability`/`.coverage` (c02) non-empty-or-honest: pass when every capability carries at least one observation or a collected `not_collected` marker; fail naming bare capabilities.
    - c03 — risk measured AND its `capabilities` bc_id set == the map's locked set (validator already forces six STRIDE rows each).
    - c04 — every `Vulnerability` has non-empty `evidence` and non-empty `path` (field is required; check evidence).
    - c05 — every `CapabilityRisk.security` composite MEASURED (ADVISORY: partial-with-reason passes, FD8-adjacent).
    - c06 — every `.qa` composite MEASURED or PARTIAL/not_collected **with a reason** (honest partial passes — FD8).
    - c07 — owed `c07_unified_drivers: deferred (E-56)` while ANY `.unified` is not MEASURED for the RD3 reason; otherwise pass when every `.unified` MEASURED with ≥1 driver (schema bounds 1–3) — FD12.
    - c08 — every proposer reference verified: `total_references > 0` implies citation guard not tripped; `total_references == 0` passes with detail recording the mode (baseline-only or degraded judgment) — FD17.
    - c09 — `UnifiedRiskMap.system` collected.
    - c10 — `AttributionReport.meets_floor` (ADVISORY); discover measured + `attribution` not_collected ⇒ **evaluated fail** carrying its reason (FD11 rule 2).
    - c11 — `BlueprintComparison.collected` MEASURED (MISSING gaps pass — E-48 D8).
    - c12 — `DomainModel.collected` MEASURED and every `Capability.member_paths` non-empty.
    - c13 — always owed today: `c13_five_reports: not collected (E-52)`.
    - c14 — derived: all four xref domains evaluated and passed ⇒ pass; any failed ⇒ fail; any xref owed ⇒ owed `c14_cross_reference_integrity: not collected (<same owner>)`.
  - Owed producer mapping (FD11 rule 1): a criterion whose producer phase is absent (state not MEASURED) is owed with owner `f"{phase}: {reason}"`; c07/c13 owners are static (`E-56`/`E-52`).

- [ ] **Step 1: Write the failing tests** — `tests/test_assessment_finish_criteria.py`, one parametrized fixture family over (clean, degraded, absent) × (discover, risk):
  - `test_clean_run_evaluates_thirteen_criteria` — clean artifacts → 13 evaluated rows (c01–c12, c14; c13 owed) + exactly 1 owed row; `test_manifest_pin`: `{r.name for r in checks} | {o.split(":")[0] for o in owed} == set(CRITERIA_MANIFEST)`.
  - `test_c07_deferred_to_e56`, `test_c13_owed_to_e52` — owed strings verbatim.
  - `test_c08_baseline_run_records_not_fails` — `propose_discover` off shape: `total_references == 0` → c08 passes with mode in detail.
  - `test_c10_subreport_not_collected_fails_not_owed` — discover MEASURED, `attribution.coverage` not_collected → c10 fail, detail carries the reason.
  - `test_producer_absent_makes_family_owed` — `discover=None`, `discover_state=not_collected("lock failed")` → every discover-family criterion owed naming `discover: lock failed` verbatim.
  - `test_c14_follows_xref` — xref_checks with one failure → c14 fails; xref_owed non-empty → c14 owed.

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement** `checks.py` — one pure predicate function per criterion (`_c01(…)` … `_c14(…)`) with a `_FAMILY` producer map driving the three-state wrapper; nothing else. Keep predicates tiny; shared helpers (`_locked_bcids(map)`, `_reason_of(state)`) at module top.

- [ ] **Step 4: Run** — PASS.

- [ ] **Step 5: Commit** — `feat(assessment): E-51 the 14 criteria — three-state predicates over typed artifacts, c07 deferred to E-56`

### Task 4: exits and orchestration

**Files:**
- Create: `src/sdlc/assessment/finish/exits.py`
- Modify: `src/sdlc/assessment/finish/__init__.py`
- Test: `tests/test_assessment_finish.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `def evaluate_exits(*, scan, scan_state, discover, discover_state, risk, risk_state) -> tuple[tuple[CheckResult, ...], tuple[str, ...]]` with wire names: `exit:scan:signals_measured` (ABSOLUTE — thirteen signal rows report), `exit:scan:candidates_present` (ADVISORY), `exit:discover:identity_lock_held` (ABSOLUTE), `exit:discover:orphans_classified` (ABSOLUTE — every bucket counted), `exit:discover:ownership_resolved` (ADVISORY — resolved-or-surfaced), `exit:assess:covers_locked_set` (ABSOLUTE), `exit:assess:judgment_honest` (ADVISORY — judgment MEASURED or degraded-with-reason); owed rows `exit:report:reports_emitted: not collected (E-52)`, `exit:generate:seeds_emitted: not collected (E-52)`. Finish's own exits ARE the 14 + the walk — no separate rows (design §5).
  - `def evaluate_finish(*, scan, scan_state, discover, discover_state, risk, risk_state) -> FinishReport` in `finish/__init__.py` — calls `xref_domains` once, feeds both, builds `FinishReport`; `collected = Measurement.measured(p)` where `p` = passed ABSOLUTE rows ÷ total ABSOLUTE rows across `criteria + exits` (the count is never 0 when any producer measured because `exit:scan:signals_measured` evaluates whenever scan measured; guard the division anyway).

- [ ] **Step 1: Write the failing tests** — `tests/test_assessment_finish.py`:
  - `test_orchestration_composes_all_three` — clean fixtures → all of `criteria`, `exits` populated, `owed` contains exactly the c07/c13/report/generate rows; `collected.state is MEASURED`; value equals the computed ratio.
  - `test_ratio_when_scan_only` — only scan measured → discover/risk families owed, ratio < 1, `collected` MEASURED.
  - `test_exits_owed_for_unbuilt_phases` — the two E-52 owed strings verbatim.
  - `test_sorted_everything` — orchestrator output constructs `FinishReport` without raising.

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** `exits.py` + the `__init__.py` composer (imports only from the package's own modules). **Step 4: Run** — PASS; full `uv run pytest tests/test_assessment_finish_models.py tests/test_assessment_finish_crossref.py tests/test_assessment_finish_criteria.py tests/test_assessment_finish.py -q` green.

- [ ] **Step 5: Commit** — `feat(assessment): E-51 exits + evaluate_finish orchestration`

### Task 5: artifact field and workflow wiring

> **Errata (final fix wave):** Task 5's text omitted the phase-agreement validator for the new `finish` field — the `_scan_agrees_with_its_phase` pattern every prior typed field carries — so `_finish_agrees_with_its_phase` and its two mismatch-shape tests were added in the final review wave.

**Files:**
- Modify: `src/sdlc/assessment/models.py` (the `Assessment` model — add field + import)
- Modify: `src/sdlc/workflows/assessment.py` (`PHASE_OWNER`, `FinishOutcome`, `_finish`, `run`, `assemble` call)
- Test: `tests/test_assessment_workflow.py` (extend; also update any existing PHASE_OWNER / stub-count pins — grep `PHASE_OWNER` and `report, generate, finish` in `tests/` first)

**Interfaces:**
- Consumes: Task 4's `evaluate_finish`.
- Produces:
  - `Assessment.finish: FinishReport | None = None` (defaulted — pre-E-51 payloads deserialize unchanged).
  - `class FinishOutcome(BaseModel)` in `workflows/assessment.py`: `result: PhaseResult`, `report: FinishReport | None = None`.
  - `_finish(self, inp, scan_out: ScanOutcome, discover_out: DiscoverOutcome, assess_out: AssessOutcome) -> FinishOutcome` — FD13 short-circuit first (none of the three `result.collected` MEASURED → `PhaseResult(FINISH, not_collected(f"not run: nothing to grade — {first} did not collect ({reason})"))` with first = scan → discover → risk); then `try: report = evaluate_finish(...) except Exception as e:` → not_collected `f"evaluate_finish failed: {type(e).__name__}: {e}"[:300]` (the `no_discover` shape); else measured with `report.collected`.
  - `PHASE_OWNER` loses its `FINISH` entry (REPORT/GENERATE stay, E-52); its comment gains one line: finish's body landed (E-51).
  - `run()` passes the outcomes to `_finish` and `assemble(...)` gains `finish=finish_out.report`.

- [ ] **Step 1: Write the failing tests** — extend `tests/test_assessment_workflow.py`:
  - `test_finish_measures_on_admitted_run` — the existing fake-activity admitted run (reuse its fixtures): finish row MEASURED, `report.criteria` non-empty, `Assessment.finish` set, `terminal_status` still `assessed:partial` (report/generate owed).
  - `test_phase_owner_loses_finish` — `PHASE_OWNER == {REPORT: "E-52", GENERATE: "E-52"}`.
  - `test_inline_failure_degrades_to_not_collected` — monkeypatch `evaluate_finish` to raise → finish row not_collected with the exception's type name in the reason, `Assessment.finish is None`.
  - Update pre-existing PHASE_OWNER/stub-count expectations found by the grep.

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** the three modifications exactly as above. **Step 4: Run** `uv run pytest tests/test_assessment_workflow.py tests/test_assessment_models.py -q` — PASS.

- [ ] **Step 5: Commit** — `feat(assessment): E-51 wires FINISH — inline evaluate, short-circuit, PHASE_OWNER drops FINISH`

### Task 6: end-to-end, short-circuit, replay

**Files:**
- Test: `tests/test_assessment_workflow_e2e.py` (extend; `pytestmark` already temporal)

**Interfaces:**
- Consumes: Task 5's wiring; the e2e harness's fake activities.

- [ ] **Step 1: Write the failing tests** (temporal tier):
  - `test_finish_measured_e2e` — the existing admitted-run e2e path: final `Assessment.finish.collected.state is MEASURED`, owed contains the four known rows (c07, c13, two exits).
  - `test_all_degraded_run_keeps_no_phases` — activities degraded so scan/discover/risk all not_collected on an admitted run → finish row not_collected, `terminal_status == "admitted:no-phases-implemented"` (FD13 pinned end-to-end).

- [ ] **Step 2: Run** `uv run pytest -m temporal tests/test_assessment_workflow_e2e.py -q` — FAIL. **Step 3: no implementation expected** (Task 5's code satisfies them; failures here are wiring bugs — fix in place, that IS this task's deliverable). **Step 4: Run** — PASS (14 existing + 2 new).

- [ ] **Step 5: Run the replay corpus** — `uv run pytest tests/replay/ -q` — PASS, zero new commands (FD16). If red, the inline call leaked a command — fix before committing.

- [ ] **Step 6: Commit** — `test(assessment): E-51 e2e — finish measured, all-degraded keeps NO_PHASES, replay corpus green`

### Task 7: sweep, lint, close-out docs

**Files:**
- Modify: `ROADMAP.md` (§2 FR-918 row; FR-911 row's stub-count sentence is closed-history — do NOT touch), `docs/roadmap/tier-2-edcr.md` (E-51 → `[x]` with landing note), `docs/roadmap/last-verified-log.md` (prepend), `ROADMAP.md` header cell (refresh, one sentence)

**Interfaces:** none (documentation per house close-out rules).

- [ ] **Step 1: Full battery** — `uv run pytest -q` (fast tier; the 2 known worktree-path fixture failures in `tests/test_read_fixtures_fresh.py` are pre-existing and environment-rooted — note, don't fix); `uv run pytest -m temporal tests/test_assessment_workflow_e2e.py tests/test_assessment_workflow_risk_gate_e2e.py tests/test_assessment_workflow_e2e_proposer_hang_chaos.py -q`; `uv run ruff check src/sdlc/assessment/finish tests/test_assessment_finish*.py`; `uv run ruff format --check` on the same; `uv run mypy`; `uv run python scripts/check_file_size.py`. All green (except the 2 noted).
- [ ] **Step 2: Docs** — FR-918 row: `[ ]` → `[ ]` ⚠️ with the landing note (partial until E-52's c13 evaluates — the honest-partial shape; full `[x]` is the owner's close-out ruling); tier-2 E-51 → `[x]` with the standard landing note (what landed, FD1/FD11/FD12/FD13/FD16 one line each); log prepend with the battery as observed; cell refresh one sentence.
- [ ] **Step 3: Commit** — `docs: E-51 landed — FR-918 partial (criteria+xref+exits live; c13 waits on E-52), tier-2 entry, log prepend`
