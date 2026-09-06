# C3 — fail closed on a missing gate; C4 — the advisory/deterministic pairing audit

**Date:** 2026-09-06
**Status:** approved design, ready for planning
**Scope:** two rows from the external-ideas register (`docs/reports/external-ideas-2026-09.md`). **C3** is a bounded code change to the deterministic quality gate. **C4** is an audit deliverable — research and writing, no gate code.
**Satisfies:** no FR moves. C3 generalizes an existing FR-915 ruling; C4 produces a report against the current tree.
**Baseline:** `main` at `03e0663`.
**Does not cover:** vacuous-present checks, duplicate check names, any new `CheckClass` member, any `PipelineConfig` surface (all §2.6), and — for C4 — every remedy the audit names, which lands as register rows and not as code (§3.7).

The two items ship as **two commits**: C3's code diff, then C4's docs diff. They share a spec because C4's most interesting finding is that C3's hole recurs one layer up (the adversary lens's fail-open leg, §3.4 row 3), and neither reads correctly without the other.

---

## 1. Problem

### 1.1 C3 — the gate judges only what it is handed

`src/sdlc/gate.py:77` `evaluate_quality_gate(checks, overrides)` loops the list it receives. A failing ABSOLUTE check blocks and its override is ignored; a failing ADVISORY check blocks unless an audited `GateOverride` names it. A required check that is **absent** from the list is invisible: nothing iterates a manifest, so nothing notices. The run goes quietly green.

The merge stage is the only consumer. `src/sdlc/stages/merge/step.py:262-314` builds the checks inline as a single unconditional list literal of seven `build_check(...)` calls, and `src/sdlc/stages/merge/activities.py:255` hands it to the `evaluate_gate` activity. Today no code path omits a check — the literal has no conditionals — so this is a latent hole, not an active bug. It is worth closing anyway, because the cost of closing it is one constant and one pre-loop pass, and the cost of discovering it later is a merge that passed for a reason nobody recorded.

**Caller census** (verified 2026-09-06, independently reproduced by both review panes). `evaluate_quality_gate` has exactly one caller in `src/`: the merge `evaluate_gate` activity. The other `build_check` users — `src/sdlc/context/delta.py:48,56,79,80` (`DELTA_CHECK`, `brownfield_delta_grounded`) and `src/sdlc/stages/context/activities.py:96,103` — produce a *single* `CheckResult` consumed directly via `.passed` at `src/sdlc/stages/architecture/step.py:171`. They never travel through the evaluator. That census is what makes the small mechanism in §2 safe, and §2.7 names the exit path if it ever stops holding.

### 1.2 C4 — a principle with no completion criterion

The C4 register row states a rule — every LLM check ships with a deterministic enforcement path behind it — and then observes that the rule has no way to be finished or checked. The row's own instruction is to make it an audit or drop it. The owner decision is **audit**.

An audit that merely lists rows inherits the same defect, so §3.6 gives this document a completion criterion of its own.

---

## 2. C3 — decision

### 2.1 The manifest

A module-level constant in `gate.py`, beside `ABSOLUTE_FLOOR`:

```python
MERGE_REQUIRED_CHECKS: Final[Mapping[str, CheckClass]] = MappingProxyType({
    "build_integration_green": CheckClass.ABSOLUTE,
    "lint_clean":              CheckClass.ABSOLUTE,
    "security_scan_collected": CheckClass.ABSOLUTE,
    "security_no_critical":    CheckClass.ABSOLUTE,
    "review_severity":         CheckClass.ADVISORY,
    "traceability":            CheckClass.ADVISORY,
    "coverage":                CheckClass.ADVISORY,
})
```

A **mapping**, not a frozenset, because synthesizing a missing check requires a classification. **One** mapping, not `REQUIRED_ABSOLUTE` + `REQUIRED_ADVISORY`, because two sets can drift — a name in neither, or in both — and the synthesis site would then have to arbitrate a conflict that need not exist. The name carries `MERGE_` so the ownership is self-describing: this is the merge gate's production contract living in the shared module its enforcement lives in.

### 2.2 Which names are required, and how severe absence is

All seven, each synthesized at **the classification it carries when present**. Four absolute, three advisory.

The governing principle: *absence must be at least as severe as failure, and nothing in the gap demands more than that.* Classification encodes who may wave a check through, and that does not change when the check stops being produced.

- `review_severity`, `traceability`, `coverage` are **required-advisory**: absence blocks, and a human may waive it through the existing audited `GateOverride` path at the merge gate.
- Making them optional would reopen the hole for three of seven names. An advisory check that vanishes is exactly as invisible as an absolute one that vanishes.
- Making them absolute would invent a terminal failure for checks the repo deliberately made waivable, and would remove the human escape hatch at precisely the moment the pipeline is known to be misconfigured — when human judgment is most useful.

The repo has already made this ruling once, for one check. `gate.py:62-67` puts `security_scan_collected` in the floor because, per FR-915, "the scan could not run" is as absolute as "the scan found a critical". C3 generalizes that ruling from one check to the required set: **not-produced ≡ produced-and-failed.**

### 2.3 Enforcement site: inside the pure function, unconditionally

Synthesis happens inside `evaluate_quality_gate`. The signature does not change: no manifest parameter, no default.

1. **The merge step evaluates twice.** `merge/step.py:316-318` evaluates clean; `:378-380` re-evaluates with overrides, and the second call passes the **original** `checks` variable (`:379`), not `gate_report.checks`. In-function enforcement covers both calls and introduces no new invariant. Step-side enforcement would require mutating `checks` before the first call and would add the invariant "the list handed to the evaluator must be the augmented one" — an invariant whose violation is silent.
2. **A parameter with a default is itself a fail-open mechanism** — the exact bug class C3 exists to kill. Every future caller who forgets it gets the default silently. A *required* parameter with one caller is a constant with extra ceremony.
3. **The "trap" for a hypothetical future caller is the feature**, and it fires closed and loud: a red gate naming the missing checks, which is strictly better than today's quiet green. The repo already has the escape hatch for a differently-shaped consumer — the delta check reads `.passed` directly and never calls the evaluator.

### 2.4 Synthesis mechanics

Before the loop, for every manifest name absent from `{c.name for c in checks}`:

```python
build_check(
    name,
    False,
    MERGE_REQUIRED_CHECKS[name],
    detail=f"MISCONFIGURED: required check {name!r} absent from gate input",
)
```

The detail string is specified verbatim here so it is not bikeshedded in review. Four requirements, each load-bearing:

- **(a) Synthesize through `build_check`, never by constructing `CheckResult` directly.** A manifest typo mapping a floor name to ADVISORY is then corrected by the same floor-forcing (`gate.py:73`) every other caller gets.
- **(b) Synthesized checks MUST appear in `GateReport.checks`.** This is a hard requirement, not an implementation detail. `merge/step.py:321-325` and `:353-357` derive the absolute/advisory blocking split by iterating `gate_report.checks`, and `:359` hands `GateContext(checks=gate_report.checks)` to the human. If a synthesized name landed in `blocking` but not in `checks`, `absolute_blocking` would be empty, the advisory split would be empty, the human gate would see a clean list and approve, zero overrides would be produced, the re-evaluation at `:378` would reproduce a failing report — and the stage would continue past it and open the PR, because there is no `passed` re-check after `:380`.
- **(c) Copy, then append. The caller's list is never mutated.** `gate.py:93` currently echoes the caller's list object by reference. In-place mutation would happen to be idempotent across merge's double call, but it is a hidden side effect on an input; pin the non-mutating behaviour explicitly.
- **(d) No new enum member.** `MISCONFIGURED` is detail text. `CheckClass` stays two-valued.

### 2.5 The demotion bypass — in scope

`evaluate_quality_gate` trusts `c.classification` as handed. The floor is enforced only at construction time inside `build_check`, and `CheckResult` is a plain Pydantic model — so a caller that constructs one directly can hand in `security_no_critical` classified ADVISORY and waive it with a single override.

This is in scope. "Absent" and "demoted" are two spellings of one hole, and the design already accepts the demotion thesis for the checks it *creates* (§2.4a); declining it for the checks it is *handed* would be incoherent. FR-915's own rationale (`gate.py:63-65`) already argues that a call site must not be able to reopen a bypass by relabeling.

**It must be implemented as a pre-loop normalization of the input list, not as a branch inside the loop.** A loop-only re-assertion would block correctly but leave `GateReport.checks` echoing the *demoted* object — and `merge/step.py:321-325`/`:353-357` split on `c.classification` read from that echoed list, so a demoted floor check would land in the **advisory** split and become human-waivable. That is the misrouting §2.4(b) exists to prevent, reintroduced one clause later. Normalize by rebuilding any `ABSOLUTE_FLOOR`-named check through `build_check` (or `model_copy`) so the loop, the report, and the step-side split all agree.

### 2.6 Non-goals

Stated explicitly so C3 is not later cited as covering them.

- **Vacuous-present checks.** `merge/step.py:303-313` emits `coverage` unconditionally and **passes** it when coverage is unmeasured (`diff_coverage is None → True`, detail "coverage unmeasured"). C3 polices presence, not validity. The asymmetry with security (FR-915: unmeasured → failing ABSOLUTE) is pre-existing policy and stays. Hardening it is its own register row. What C3 does improve: after it, *omitting* a check is no longer cheaper than emitting an honest vacuous one — absence blocks, so the soft skip must at least leave an audit trail.
- **Duplicate names.** Under the current loop a failing duplicate blocks like a single failing check and a passing duplicate is inert; duplicates cannot manufacture a false green, only absence can. Revisit only if evaluation is ever refactored into a name-keyed reduction (`{c.name: c for c in checks}` silently keeps the last).
- **No new verdict enum member; no `PipelineConfig` surface.** A per-project manifest would be an opt-out surface by nature: a misconfigured project would silently reopen the exact hole C3 closes. `ABSOLUTE_FLOOR` already staked this position (`gate.py:59`, "whatever a project configures"). Fail-closed contracts live in code, next to their enforcement.

### 2.7 The exit path, named

The manifest is *merge's* manifest living in shared `gate.py`. That is acceptable only as long as the caller census in §1.1 holds. If a second gate caller ever appears, the manifest promotes to a **required** field on `QualityGateInput` — never to a defaulted parameter, per §2.3(2).

### 2.8 The human-gate surface

Post-C3, `GateContext(checks=...)` (`merge/step.py:359`) can carry `MISCONFIGURED` rows to the human standing at the merge gate. This is desired: the human sees the missing check by name with its MISCONFIGURED detail, and waiving an advisory one is the designed escape hatch. Nobody should later "fix" the alarming detail text out of the UI.

### 2.9 TDD

Mandatory. Tests first, fast unit tier (`pytest`, no marker).

**New cases:**

1. Missing absolute → in `blocking`, and an override naming it is ignored.
2. Missing advisory → in `blocking`, and waived by an override naming it.
3. Typo'd required name (`security_no_crtical` handed instead of `security_no_critical`) → synthesis fires for the real name and the merge is blocked, instead of quietly green. This is the sharpest demonstration of what C3 buys.
4. Empty checks list → all seven synthesized and blocking.
5. Every `ABSOLUTE_FLOOR` name appears in `MERGE_REQUIRED_CHECKS` mapped to ABSOLUTE.
6. Synthesized checks are present in `GateReport.checks` — guards §2.4(b).
7. Non-mutation and idempotence: evaluate twice as merge does (clean, then with overrides); the caller's list is unchanged, and the second report's `checks` contains each synthesized name exactly once — guards §2.4(c).
8. Demotion normalization: a directly-constructed `security_no_critical` classified ADVISORY both blocks despite an override **and** is echoed in `GateReport.checks` as ABSOLUTE — guards §2.5.
9. **The pin.** `MERGE_REQUIRED_CHECKS` keys equal the names `merge/step.py` actually builds. Source-needle style, precedent at `tests/merge/test_merge_gate_wiring.py:40-47`. This test alone owns the census and must **not** use the shared fixture, or the census would be checking itself.

**Shared helper.** A `required_checks` fixture in `tests/conftest.py` returning a *builder* callable: a fresh list per call, driven by `MERGE_REQUIRED_CHECKS` rather than a hardcoded seven, with per-name pass/fail overrides. A fixture rather than a helper module because the four migrating tests span `tests/` and `tests/merge/`, the tree has no `__init__.py` packaging, and a top-level `tests/gate_manifest.py` import from `tests/merge/` would depend on collection order. `tests/conftest.py` already mixes helpers and fixtures (`run_git:82`, `write_registry_dir:156`). Caveat: a fixture cannot be used inside `@pytest.mark.parametrize`; none of the migrations needs it, and the builder promotes to a module if one ever does.

### 2.10 Migration of existing tests

In-function synthesis retroactively changes the contract of every existing test that hands the evaluator a partial list. This is budgeted work in the same red→green pass, not a surprise to be discovered mid-implementation.

**The rule:** synthesis only ever *adds failing names*. A test asserting a **clean or exact** outcome from a partial list (`passed is True`, `blocking == []`, exact-equality on `overridden`) breaks; a test asserting a **dirty** outcome (`passed is False`, membership, absence of a specific name, or `overridden == []` where no override can match a synthesized name) survives. Assertion shape decides, not which names are handed.

Full census of the eleven evaluator-calling tests.

**Break (4)** — rewrite onto the `required_checks` builder:

| Test | Why |
|---|---|
| `tests/test_quality_gate.py::test_advisory_failure_passes_with_override` (:25-32) | `passed is True`, `blocking == []` |
| `tests/test_quality_gate.py::test_all_pass_is_clean` (:45-52) | `passed is True`, `blocking == []` |
| `tests/test_security_collection_gate.py::test_measured_clean_scan_passes_both` (:52-54) | `blocking == []` |
| `tests/merge/test_merge_gate_wiring.py::test_advisory_failure_passes_with_audited_override` (:79-86) | `assert report.passed`; its list holds only `coverage_gate`, so **all seven** manifest names are absent |

**Survive (7):** `test_quality_gate.py::test_absolute_failure_blocks_unconditionally` (:9-16), `::test_advisory_failure_blocks_without_override` (:19-22), `::test_security_floor_cannot_be_demoted` (:35-42); `test_security_collection_gate.py::test_not_collected_scan_blocks_on_its_own_check` (:43-49); `test_security_floor.py::test_security_check_blocks_when_critical_present` (:116-125), `::test_security_check_absolute_even_if_requested_advisory` (:128-138); `test_merge_gate_wiring.py::test_absolute_failure_blocks_despite_override` (:63-76).

Unaffected because they never call the evaluator: `test_security_collection_gate.py::test_collection_check_is_in_the_absolute_floor`, `::test_a_caller_cannot_downgrade_the_collection_check`, and the source-needle wiring tests.

One incidental finding worth keeping: `coverage_gate` in `test_merge_gate_wiring.py:80` is a name no production code builds — a made-up check name already living in the suite, and a live specimen of exactly the typo hazard case 3 tests for.

### 2.11 Same-diff contract obligations

The repo rule is binding: whoever changes a stage's behaviour updates its clauses in the same diff. C3's code lives in `gate.py`, but the behaviour is the merge stage's.

- **`src/sdlc/stages/merge/merge.md` — new clause `MERGE-1.6`, "Required-check manifest."** A new id rather than in-place amendment of MERGE-1.2/1.3, for three reasons: the register row, this spec, and the `foundation.md` update all want one citable handle; the behaviour spans both 1.2 (absolute) and 1.3 (advisory), so amending both in place would state the synthesis mechanism twice and the two statements would drift — the same failure §2.1 rejects two frozensets for; and once synthesis exists, 1.2 and 1.3 remain *literally true*, because an absent check becomes a failing check of the right class and flows through the existing clauses. MERGE-1.6 names the manifest as the single authoritative list, states that absence yields a synthesized failing `MISCONFIGURED` check at the manifest classification, and routes absolute absence to MERGE-1.2 and advisory absence (including the override path) to MERGE-1.3.
- **One-line cross-reference in each of MERGE-1.2 and MERGE-1.3** pointing at MERGE-1.6. No duplication of the name list.
- **One line in `merge.md`'s "Failure modes" list** (`merge.md:24-28`). A failure-modes list that omits the new failure mode is how the next audit finds its next C3.
- **`src/sdlc/stages/merge/AGENTS.md`** — the "Absolute checks are non-overridable" invariant is reinforced by §2.5 and must be updated to say so. Mandatory, now that §2.5 is in scope.
- **`src/sdlc/gate.py` module docstring**, which already carries the floor's rationale, gains the required-manifest paragraph.
- **`docs/reference/foundation.md:73-86`**, which documents `build_check`, `ABSOLUTE_FLOOR` and `evaluate_quality_gate` semantics for this module. It is **already stale**: `:81` lists the floor as `security_no_critical` only, missing FR-915's `security_scan_collected`. Fix that sentence while in the section, and say in the commit message that the fix is deliberate rather than drive-by.
- **The C3 row in `docs/reports/external-ideas-2026-09.md:51`** flips to Fixed. Its own cites are stale — it says `ABSOLUTE_FLOOR (:57)` and `build_check (:66)`; the actual lines are `:60` and `:71`. Correct them on the flip.

Treat `MERGE_REQUIRED_CHECKS` edits with floor-grade scrutiny thereafter. After C3, deleting a manifest entry becomes the only way to make a dropped check quiet again: the pressure point moves from the producer to the constant. Tests pin today's set (§2.9 case 9); the rest is review culture, on the FR-915 model of saying why in the diff.

---

## 3. C4 — decision

### 3.1 Deliverable

A new report at `docs/reports/2026-09-06-advisory-deterministic-pairing-audit.md`, plus an update to the C4 row in `docs/reports/external-ideas-2026-09.md:52` pointing at it. Header carries the date and the commit hash: this is a point-in-time snapshot under the docs-describe-main convention, not a living queue.

### 3.2 Scope criterion

Scope is drawn by criterion, not by stage list. A pass is in scope iff either prong holds:

- **Prong A — judgment.** Its output is, or contains, a verdict about work it did not itself produce: approve, findings, severity, or a self-reported confidence that an admission decision consumes.
- **Prong B — evidence.** Its output is retained or derived evidence about work that a gate, a fix loop, or a later admission decision reads.

Generators — architect, planner, clarify, research, the code task prompt — are **out**. Their artifact *is* the work; their defects are the jurisdiction of the judgment passes that consume them, and those passes are already rows. Asking "what deterministic check stands behind the Architect" is answered by pointing at the rows.

The non-obvious precision: **a generator's self-reported confidence is in scope under Prong A even though the generator is not**, because it short-circuits a human gate. The unit of the audit is the judgment, not the stage.

The verification surface, enumerated: task admission in the code stage (`code/step.py:797-836`, plus the budget-exhausted human task gate at `:858-906`), the merge gate, the evidence extractors feeding both, and the confidence short-circuits on gates. Scoping to merge alone would miss where most of the binding actually happens, one stage earlier.

### 3.3 Verdict set

"What deterministic mechanism stands behind it" conflates two directions, and the rows exhibit both. Ask each row two questions — *if it blocks, what makes the block stick?* and *if it wrongly passes, what catches it?* — and the verdicts are four:

| Verdict | Meaning |
|---|---|
| **PAIRED** | A deterministic twin covers the pass's jurisdiction and can block without the LLM. |
| **ENFORCED** | The LLM's block is reified into deterministic machinery, but a wrong-yes has no deterministic backstop inside the pass's own jurisdiction. |
| **FILTERED** | A deterministic mechanism sanitizes what the pass sees or what it can credibly claim, and nothing it says blocks. |
| **UNPAIRED** | The output influences admission with nothing deterministic behind it. |

Columns: *pass + file:line* | *failure mode if wrong* | *enforcement* | *backstop* | *verdict*. `file:line` for **both** the pass and the mechanism, so the audit's claims are checkable the way register rows are. The two-direction test is stated **in the document itself**, so the next auditor re-runs it rather than trusting the table.

### 3.4 The eight in-scope rows

All verified against `main @ 03e0663`. Cites name the **invocation** site, not the definition.

1. **MergeVerdict** — `merge/models.py:21`, consulted `merge/step.py:399`. Only under `GatePolicy.SOFT`, and only in the `else` branch reached after the deterministic gate passed clean. Behind it: `evaluate_quality_gate` itself. It can approve an already-clean build; it can never bypass the gate. **PAIRED** — with a one-line cross-reference to row 8, because while it cannot bypass the *gate*, its `confidence` feeds `_auto_decision_for` at `:399` and can skip the *human*. Without that cross-ref the row reads cleaner than reality.
2. **Primary reviewer** — binds twice: task admission (`code/step.py:797`, where `review_ok` gates the done path) and merge (the `review_severity` ADVISORY check at `merge/step.py:287-292`, waivable via audited `GateOverride`). Wrong-yes backstop: the absolute merge checks cover code-level dimensions only; design-quality jurisdiction has the human alone. **Its own fail-open leg must be annotated**: `review/step.py:114-115` returns `None` when `review_enabled` is false or no agent is configured, and `code/step.py:797` reads `review is None` as approval. The failure is *compound* — `code/step.py:801` runs the adversary only `if review is not None`, so the primary's fail-open silently disarms the backstop lens too. **ENFORCED**, with a fail-open leg.
3. **Adversary lens** — defined `review/step.py:159`, invoked `code/step.py:802`, consulted `code/step.py:812`. **This corrects the brief this work started from, which called the adversary "signal only". It is not.** Line 812 reads `if adversary is None or adversary.approve or not adversary.blocking_findings:` and guards the done-return at `:826`; a blocking rejection skips the done path, feeds the fix loop (`:838`), and on budget exhaustion reaches the human task gate (`:867`). It runs only after `task_passed and review_ok` (`:800`), so it can only tighten. The honest gap is the **fail-open leg**: an exception, `adversarial_review_enabled` false, or no agent yields `None`, which is read as agreement, with no tombstone (`review/step.py:179-183`, `:234-240`, `code/step.py:335`). **That is C3's hole one layer up — a missing check read as a passing one — and the audit must name the analogy explicitly.** **ENFORCED**, with an UNPAIRED fail-open leg.
4. **deep_review** — `review/step.py:243`, invoked `code/step.py:813` and `:894`, both post-decision; never in the success condition. Behind it, output-side: `handoff.py:99-124` `verified_integrity_flags` and `:127-149` `verified_plan_deviations` (E-43/E-83) drop any flag or deviation whose evidence quote is not verbatim in the transcript. Input-side: the E-38 scrub. A deterministic filter that never gates. **FILTERED**.
5. **Handoff extractor** — `code/step.py:417`. Output deterministically cross-checked by `handoff.py:60-84` `cross_check_claims`: claims naming files outside the diff are dropped, quotes absent from the transcript are dropped. Never gates. Fail-open degrades to a *mechanical* `HandoffSummary` (files only, `code/step.py:459-465`) — the only pass whose failure lands on a deterministic artifact. **A second site must be cited or ruled out with evidence**: `workflows/feature.py:340` is a `_run_role("handoff", ...)` twin with the same prompt shape at `:345-349`; if it is dead, it belongs in the out-of-scope table with the evidence that says so. **FILTERED**.
6. **Analyst** — `analyze/step.py:121`. Behind it: the deterministic `untraced_criteria` reduction (`:136`) feeding the merge `traceability` ADVISORY check (`merge/step.py:293-302`, waivable). A wrong-yes ("everything traces") has no backstop in its jurisdiction; name that honestly. **ENFORCED**.
7. **QA LLM pass** — `qa/step.py:175`; its own docstring disclaims gating (`qa/step.py:129-131`, "Never calls a gate"). **The disclaimer is not the whole truth, and the row must say so.** `code/step.py:750` is `task_passed = bool(qa_raw.tests_passed and not qa.issues and not drift.found)` — `qa.issues` is the QA LLM's output, and an empty issue list is a *conjunct of the pass verdict*. The LLM blocks. The verdict still stands, on corrected grounds: the deterministic twin `run_test_suite` (`qa/step.py:137-141`) holds the wrong-yes direction for test-detectable issues, and the LLM's conjunct is tighten-only — it can fail a passing build, never pass a failing one. Residual to name: a wrong-yes on a *non-test-detectable* issue has no deterministic backstop in QA's own jurisdiction and is caught only by the reviewer, adversary, and human rows. **PAIRED**.
8. **Confidence auto-approves** — `workflows/role_host.py:55-75` `_auto_decision_for` (FR-301), consumed at `:224` inside `_revisable_stage` (`:212-239`) for the architecture (`architecture/step.py:188`) and plan (`plan/step.py:109`) gates, plus MergeVerdict's copy at `merge/step.py:84-100`, consulted `:399`. SOFT policy plus a self-reported confidence at or above threshold skips the human gate. Real guards exist: a `None` confidence never auto-approves (`role_host.py:64-65`), and exhausted rounds force a final gate where even SOFT waits (`:236-239`). Nothing deterministic stands behind self-confidence. **UNPAIRED — and the audit's headline row**, because it runs in the direction the register's phrasing does not anticipate: the LLM output does not *add* a check, it *removes* a human one.

### 3.5 The memory channel — a section, not a row

Retained LLM text — GOTCHA (`review/step.py:227`, `:345`; `code/step.py:910`; `analyze/step.py:166`), STAGE_SUMMARY (`analyze/step.py:155-162`), GATE_FEEDBACK (`merge/step.py:329`, `:424`; `workflows/feature.py:256`) — is recalled into later runs as a declared, hashed, watermark-frozen stage input (`memory/activities.py:52-60`, FR-402; the memoization key at `role_host.py:122`). Past LLM judgments shape future *proposers*, which are then gated by the gates already audited.

The deterministic guard on this channel is **replayability, not judgment**. It earns a section rather than a row because it is the mechanism by which an UNPAIRED pass's wrongness compounds across runs — which is exactly the blast-radius question §3.6(4) demands.

Also recorded here: **retro has no LLM pass of its own.** `retro/step.py:34-108` is deterministic orchestration, fully trapped so the run outcome is never modified. It *triggers* the `reflect` activity (`memory/activities.py:107`), which is memory-domain consolidation and sits outside the admission surface.

### 3.6 Completion criterion

The register's charge against C4 is that the principle has no completion criterion. This document has one. Done means all five:

1. Every in-scope row carries a verdict, with `file:line` for **both** the pass and the mechanism.
2. The census greps are printed **verbatim** in the document, so a reader can re-run them and diff the table.
3. An **out-of-scope table** is present — one line per excluded pass with its reason — so "missed" and "excluded" are distinguishable. A census that lists only its hits cannot be audited for misses.
4. Every UNPAIRED row carries either a named follow-up register row, or an argued "signal only, and that is correct" justification that states **blast radius**: what bad work is admitted if this pass is sycophantic, and what still catches it.
5. The C4 register row points at the document and names the real row count — eight, not the three the row currently names.

**The out-of-scope table must be provably exhaustive at the near-misses.** Reproduce `grep "run_role(" src/sdlc` and account for every line: review ×3 (`review/step.py:127,195,289`), analyze (`:121`), clarify ×4 (`clarify/step.py:78,84,146,161`), architecture (`:138`), code handoff (`:417`), plan (`plan/step.py:88`), merge verdict (`merge/step.py:391`), qa (`:175`), plus the workflow-side twins `feature.py:340` and `role_host.py:133` / `core/context.py:33` (the capability itself). Rule explicitly on two awkward candidates rather than leaving the reader to wonder whether the census missed or dodged them: `ctx.judge` (benchmark quality scoring — an LLM verdict retained as evidence, which Prong B arguably reaches via C5's calibration loop) and the crew workflow's roles (E-88). Record that **intake and deploy have no `run_role` sites at all**, so the census dates itself.

Two cite corrections carried in from review, to be made in the audit rather than repeated: the watermark-freeze mechanism lives at `role_host.py:122` and MemoryHost, not `core/context.py:55` (which is the `recall` protocol stub); and the None-confidence guard is `role_host.py:64-65` (`:60-62` is the docstring).

Worth noting in the out-of-scope lines: the architect is the best-backed generator — `check_brownfield_delta` (`context/delta.py` `DELTA_CHECK`, consumed `architecture/step.py:162-184`) stands behind it deterministically. The plan stage has nothing analogous; E4's plan-drift signal is computed and read by nothing, and is already its own register row.

### 3.7 Boundary — a diff tripwire

C4 is writing. Its diff touches **exactly two files**: the new `docs/reports/2026-09-06-advisory-deterministic-pairing-audit.md` and `docs/reports/external-ideas-2026-09.md`. **Any change under `src/`, `tests/`, `agents/`, prompts, or config in C4's diff is a defect.**

The slide temptations, in order of likelihood: hardening the adversary's fail-open (the census's juiciest gap, found while writing prose next to a code editor); wiring `deep_review` or the handoff extractor into a success condition "since we're documenting them anyway"; contamination from C3, whose legitimate `gate.py` edits leave gate context hot — hence the separate commits; census automation, a script asserting every `run_role` site appears in the table, which is itself a register row ("census drift backstop") and not audit content; and scope slide into generators, against which §3.2's criterion is the fence and the out-of-scope table its visible form.

**Recommendations live only as register rows** in `external-ideas-2026-09.md`. The audit may sketch a one-line candidate remedy inside a gap row, because triage context is useful there — but priority, sizing, and where-it-lands belong to the queue. Two actionable copies disagree within a month: one queue, one map.

---

## 4. Sequencing

1. **C3, commit 1.** Tests first (§2.9), including the four migrations (§2.10), red → green. Then `gate.py`, then the contract and doc obligations of §2.11 in the same diff.
2. **C4, commit 2.** The audit document and the register row, and nothing else (§3.7).

Verification for C3 is `pytest` (fast tier — no marker needed), plus `ruff check .`, `ruff format .`, and `mypy`. No file approaches the 1000-line ceiling: `gate.py` is 93 lines, `merge/step.py` 444, `merge.md` 28.

## 5. Open questions for the human orchestrator

1. **The brief's adversary characterization was wrong** (§3.4 row 3). Both review panes independently verified `code/step.py:812`. The audit is written on the corrected reading; confirm that is the intent rather than a scope change.
2. **`workflows/feature.py:340`** (§3.4 row 5) is a second handoff extractor site. Whether it is live or vestigial is a question about `FeatureWorkflow`'s in-flight surgery that the audit should record rather than resolve — confirm the exec agent should cite it as found, not chase it.
3. **`docs/reference/foundation.md:81` is stale independently of C3** (§2.11). Fixing it inside C3's diff keeps the doc honest but widens the diff by one sentence; say if you would rather it be its own commit.
