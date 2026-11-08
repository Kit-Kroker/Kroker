# Decision: Arm re-selection round

- **Slug**: arm-reselection-round
- **Decided**: 2026-11-08
- **Verdict**: kill-as-park — round closed, documented HOLD on Option D (final, 2026-11-08, after owner answers; earlier decisions kept below as history)
- **Artifacts reviewed**: intake.md, research.md, problem.md, concept.md, diagnosis.md

## Final decision (2026-11-08, after owner answers): kill-as-park

**Verdict: kill-as-park.** The round is closed with no build, no proving run and no spend. The corpus stays at 0 of 8 under a documented HOLD on Option D (wait for a new z.ai model). The user approved the orchestrator's recommendation to park.

### Owner answers (received via orchestrator, user, 2026-11-08)

- Corpus purpose: **capability discrimination.**
- Deadline / consumer: **no deadline; no near-term consumer.**
- Anthropic subscription arm use: **NO.**
- Spend ceiling: **none given.**

(Recorded as relayed by the orchestrator; not a verbatim transcript of the user's own words.)

### Trigger and option status

| Item | Status |
|---|---|
| K1 (no near-term consumer) | **Treated as met.** No consumer or date named. |
| K2 (cost exceeds stated budget) | **Untested.** No spend ceiling was given. |
| K3 (provider dead end) | **Half met.** Anthropic subscription use is a NO; the z.ai catalog check was deliberately **not run** and no provider call was made. It stays a check to do at reopen time. |
| K4 (regression-detection purpose) | **Not fired.** The stated purpose is capability discrimination. |
| Option B (flash-strong, absolute bar) | **Dead on the data.** Its premise is contradicted (flash mean 0.704 vs glm-5.3 0.829, absent on readtime) and no bar exists that is not post-hoc (`diagnosis.md`). |
| Option C (cross-provider pair) | **Blocked by policy.** The owner disallows Anthropic subscription arms. |
| Option D (wait for catalog) | **Held.** Chosen by default; the other options are closed. |

### Reopen triggers

1. A new non-deprecated z.ai model appears in the `zai-coding-plan` catalog. At that point run the read-only catalog check that was skipped now.
2. The owner names a roadmap item or date that needs an accepted corpus case.
3. The owner opens a rule change for the n=3 acceptance rule.

### Standing note for the owner (not acted on)

At the observed cat-cafe spread (pooled SD 0.259) the acceptance rule cannot resolve a 0.15 margin at its n=3-per-arm minimum: about **47 runs per arm** are needed, or about **6-7 if failures are scored separately** (`diagnosis.md` (b)). So any `accepted` or `rejected` verdict at n=3 is largely noise in both directions. Changing the rule, including the margin or the run minimum, is **out of scope** of this round and is left to the owner (reopen trigger 3). `SEPARATION_MARGIN` was not touched.

### What was left undone on purpose

No repo edits, no code changes, no catalog or provider call, no paid run. The unresolved data items (host run records, private theatre record and its verdict's code version) remain unfetched; they matter only if the round reopens.

---

## Re-decision (2026-11-08, after the cleared offline diagnosis): history

**Verdict: still needs-clarification, now narrower.** Not `go`: no option has an honest basis. Not yet `kill`: the two facts that decide it are owner answers that were not given and I did not assume. What the diagnosis (`diagnosis.md`) changed:

- **The "does not separate" finding is weaker than the card says.** At the observed cat-cafe spread (pooled SD 0.259) a 0.15 margin needs about 47 runs per arm; the rule accepts at 3. Dropping one 0.0 flash run flips cat-cafe (flash 0.844 vs glm-5.3 0.829). So the rule at n=3 is mostly noise in both directions; this is a finding about the rule's resolving power, not a reason to lower the margin.
- **Option B (flash-strong absolute bar) has lost its premise.** Flash's mean is below glm-5.3 on cat-cafe, it is absent on readtime, and no pre-registered bar exists that is cleared on more than one case.
- **"Weak-arm fragility is flash-specific" is not established.** Visible gaps: 4 weak benches (cat-cafe 1, readtime 3) and 2 strong benches (geotext) are absent from graded evidence; absence is not proof of loss (`not_comparable` is also present). The ADR-6 collision predates every bench id in the files except the carried 2026-10-16 run, so it does not explain these gaps. Logs are not on this machine.
- **Theatre's `rejected no_separation` may be a mislabel** of a stall, or written by older code; unverifiable without the private record.
- **The catalog question is unanswerable from the repo** (no listing, no `glm-5.4+` reference).

### Blocking items (narrowed)

1. **Owner:** what is the corpus for (regression detection vs capability discrimination), and is there a near-term consumer and date? Not answered; not assumed.
2. **Owner:** may an Anthropic-family arm run on subscription via `claude -p` unattended, and what spend ceiling applies to proving runs? Not answered; not assumed.
3. **Data, zero spend but off this machine:** run records from the host volume (classify the lost runs by arm, stage, cause) and the private `theatre-box-office` record, including which code version wrote its verdict. Advisor's note: time-box these; if they cannot be produced by a date the owner names, proceed without them.
4. **Read-only provider/CLI model listing** for the z.ai coding-plan catalog (one call; not covered by the current clearance). Same time-box.

### Kill triggers (record these; either closes the round as `kill`)

- **K1 — no near-term consumer.** The owner names no roadmap item or date that needs an accepted corpus case. Then the cost of waiting is nil and the round is closed; the hold on Option D is recorded with a re-open trigger (a new non-deprecated z.ai model appears).
- **K2 — cost exceeds budget.** Replaces the skeptic's original "cases cannot separate any arm", which cannot be tested at zero spend (it would need runs of another arm). Computed form: runs per arm needed to resolve the gap at the measured spread, times cost per run, exceeds the budget the owner states. The arithmetic is in `diagnosis.md` (b); only the owner's budget is missing. If failures are scored separately and the SD falls to about 0.09, the requirement drops to about 6-7 runs per arm and K2 may not trigger.
- **K3 — provider dead end (skeptic).** The owner disallows unattended Anthropic subscription runs and the catalog check shows no new usable z.ai model. Then B is broken by data and C is blocked by policy, so close the round.
- **K4 — regression-detection purpose (advisor).** If the owner says the corpus exists to detect pipeline regressions, and a cheap weakened-pipeline weak arm cannot be built, kill B and C (the two-arm capability-gap premise does not match the purpose).

Not adopted: the skeptic's K4 "kill the two-arm margin rule outright if N>10". That is a rule change, which the brief excludes unless the owner opens it; the finding is recorded and left to the owner.

### Consult record

Both consulted via `herdr agent prompt` on 2026-11-08, replies read from their panes. **Advisor:** needs-clarification is right; time-box the data and catalog blockers; replace K2; adds K4; theatre record may predate the stall branch. I could read only the tail of the advisor reply (its items 1-3 scrolled out of the pane); those are not reflected here. **Skeptic:** needs-clarification is right; verified the cat-cafe numbers, pooled SD, n≈47 and citations; flagged that the "2 strong absent" geotext reading is inference (already tagged so in `diagnosis.md`), noted parked-case losses (particle-swarm, `BENCHMARK.md:695`) as a separate source of failed runs that the card's "7" may or may not include, and added the provider-dead-end trigger. Both read the same draft; neither saw the final text of this section.

---

## Original decision (2026-11-08, before the diagnosis)

## Scorecard

| Criterion | Rating | Justification |
|-----------|--------|---------------|
| Problem validity | adequate | Corpus is 0 of 8 accepted; the same-provider pair failed at n≥3 same-commit (acceptance.yaml ×3). Real, but its consumer and deadline are unrecorded. |
| Evidence strength | weak | Confirmed: margins, readtime no-weak, rule values. Not supported: the card's "flash is the best scorer" premise (flash mean 0.704 < glm-5.3 0.829; died on readtime; 0.018 on theatre). Geotext strong is n=1. Cause of non-separation (pair vs. case vs. harness) is unknown. Theatre and lost-run causes not re-read. |
| Value vs. inaction | adequate | Waiting costs no money and the card has no deadline; the benefit of acting is unquantified. |
| Feasibility / appetite | unknown | B (medium) has no honest bar on current data; C (large) rests on an unverified Anthropic-subscription premise and an ADR-6 re-plumb; D has no trigger. |
| Strategic fit | adequate | Restoring an honest acceptance instrument fits the benchmark docs; no constitution check done. |
| Risk posture | adequate | Main risk (tuning the bar or margin to data) is identified and excluded; B's lost-run handling and C's judge-family move are not yet mitigated. |

## Verdict & Rationale

**needs-clarification.** It is not a `go` because evidence strength is `weak`: the diagnosis that decides between B and C has not been done, and the one factual premise favouring B does not survive checking against the acceptance files. It is not a `kill`: the problem is real and the 0 of 8 tally is a standing gap; what is premature is committing a build-and-prove round. The recommended path (concept Option A) is a zero-spend offline step that the user can clear cheaply, followed by a documented hold on candidate 3 (wait for the z.ai catalog) with explicit re-open triggers.

### Skeptic kill-case (self-run; see process note)

The strongest case for killing the round outright: three same-provider tier comparisons have now failed or inverted (glm-5.2 era and glm-5.3 era), the corpus's consumer is unnamed, and every remedy either changes the semantics of the measurement (B), costs a second budget plus ADR-6 re-plumbing (C), or depends on a vendor (D). A documented kill would "close" the card with the data as the record. Why it is not chosen: a kill would discard the opportunity to learn, for free, whether the cases rather than the arms are the defect (readtime strong 0.22, theatre ~0.02 for both arms point that way), and that answer could make the problem tractable without any new arm. If the offline step shows the cases are not the cause and the owner states no near-term consumer, the correct follow-up is a **kill** (or a parked hold on D) rather than a round.

### Process note for the orchestrator

Superseded: when this decision was first written I did not find `advisor`/`skeptic` as agent types and ran the kill-case myself. They are reachable as named herdr agents (`herdr agent list`) and were consulted for the re-decision above.

## If needs-clarification

- **Blocking questions** (all answerable at zero spend except the owner items):
  - [NEEDS CLARIFICATION: what is the corpus for next — regression detection or capability discrimination — and which roadmap items need an accepted case, by when? (owner)]
  - [NEEDS CLARIFICATION: from existing records, are the 7 lost weak runs flash-specific or harness-wide, and at which stages? (offline)]
  - [NEEDS CLARIFICATION: per-case variance and the n needed to resolve a 0.15 margin; are the cases (readtime, theatre) too flat for any pair? (offline)]
  - [NEEDS CLARIFICATION: which non-deprecated models does the z.ai `zai-coding-plan` catalog list today? (read-only check)]
  - [NEEDS CLARIFICATION: may an Anthropic-family arm run on subscription via `claude -p` unattended? (owner)]
  - [NEEDS CLARIFICATION: how should a lost run count under any single-arm bar? (only if B survives)]
- **Revisit stage**: research (add an offline diagnosis note under `.specify/assessments/arm-reselection-round/`), then re-decide. No paid run is needed for any of it.

## If go — Handoff to `/speckit-specify`

Not applicable (verdict is not `go`). If a later re-decision does reach `go`, the handoff would be: problem = corpus cannot reach `accepted`; approach = whichever of B/C survives the diagnosis; out of scope = changing `SEPARATION_MARGIN`; success = ≥1 `accepted` case under a pre-registered rule; proving runs only on explicit user clearance, screening on 1–2 cases first.
