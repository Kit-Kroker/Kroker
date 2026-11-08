# Concept: Arm re-selection round

- **Slug**: arm-reselection-round
- **Created**: 2026-11-08
- **Recommended option**: A (offline diagnosis, then hold on candidate 3) — i.e. do not open a build/proving round yet

The card's three candidates are Options B, C and D. Option A is added because the problem statement leaves open whether the pair, the cases, or the harness is the cause, and that can be answered from existing records at zero spend.

## Options

### Option A — Offline diagnosis, then wait for the catalog (smallest thing; zero spend)
- **Sketch**: Using only existing run records and acceptance files, answer: (1) per-case score variance and the n needed to resolve a 0.15 margin; (2) why the 7 weak runs were lost (flash-specific vs. harness-wide); (3) whether the cases themselves are too flat (readtime strong 0.22, theatre ~0.02 for both arms); (4) what non-deprecated models the `zai-coding-plan` catalog currently offers. Record the findings and a re-open trigger (e.g. a new z.ai model, or a decision that an Anthropic arm is allowed). No code, rule, or case change.
- **Appetite**: small (days or less).
- **Trade-offs**: wins — spends nothing, directly attacks the unknown that decides between B/C, keeps SEPARATION_MARGIN untouched. Sacrifices — corpus stays at 0 of 8 meanwhile; may conclude "case problem", which opens a third remedy (rework or replace cases) the card does not list.
- **Rabbit holes**: the private store (theatre) records are outside the repo; the lost-run causes may need run logs that are not retained.

### Option B — Flash-strong, no weak arm, absolute oracle bar (card candidate 1)
- **Sketch**: Corpus cases are accepted when one arm (flash) clears a pre-registered absolute oracle bar on n≥3 same-commit runs; the weak arm and the margin gap rule are retired for those cases. Acceptance semantics change (new verdict branch, bar constant, `benchmark accept`/`corpus` output, handling of lost runs).
- **Appetite**: medium (weeks: acceptance logic, CLI, tests, BENCHMARK.md contract, plus screening/series runs that are paid).
- **Trade-offs**: wins — z.ai only, cheapest per run, no ADR-6 re-plumbing. Sacrifices — answers a different question (absolute competence, not sensitivity to quality differences; a case any competent model passes is useless as a regression detector, so the existing `saturated` rule needs an analogue); research shows flash mean below glm-5.3 on both cases with data (0.704, 0.593), died on readtime, and ~0.02 on theatre, so no bar set without looking at the data is cleared on more than one case, and any bar set after looking is the tuning the brief forbids.
- **Rabbit holes**: choosing the bar honestly (pre-registration); defining a lost run; flash fragility becomes load-bearing; every existing two-arm record and test assumes the gap semantics.

### Option C — Cross-provider pair under ADR-6 (card candidate 2)
- **Sketch**: Pair a z.ai arm with an arm from another provider (plausibly Anthropic) so the capability gap is real, and keep the gap rule. Reviewer/adversary/judge (currently `anthropic:claude-sonnet-5`) must differ from both arms by model identity, so judge-side roles move to a third family.
- **Appetite**: large (a second provider budget, ADR-6 role re-assignment, the unbuilt model-identity check from the 2026-10-11 ADR-6 amendment may become a precondition, screening and series runs paid).
- **Trade-offs**: wins — most likely to produce a genuine, rule-compatible margin; keeps the acceptance semantics. Sacrifices — largest cost and blast radius; Anthropic access is subscription-only and unattended benchmark use is unverified; the gap's sign can invert on this harness (geotext did under glm-5.2).
- **Rabbit holes**: picking a third family for the judge side; rate limits on subscription; case oracles re-validated per pair.

### Option D — Wait for a new z.ai model (card candidate 3)
- **Sketch**: Do nothing until the catalog offers a model (e.g. glm-5.4+) that yields a plausible in-provider pair; then run screening.
- **Appetite**: small now (no work), unknown elapsed time.
- **Trade-offs**: wins — zero cost, no semantic changes. Sacrifices — no re-open trigger unless someone watches the catalog; corpus stays at 0 of 8 indefinitely; the same-provider tiers may simply be too close to separate again.
- **Rabbit holes**: another arm retirement could invalidate whatever is chosen (four models were deprecated by 2026-10-27).

## Recommendation

Choose **Option A, then stay on D until a trigger fires**. Reasons tied to the goals:
- G1/G2: B cannot be justified honestly on the current evidence (no bar is cleared across cases without post-hoc fitting), and C's feasibility premise (an Anthropic arm on subscription) is unverified and its cost is the largest.
- G3: nothing here justifies a paid screening run yet; A is the free step that tells us which paid step, if any, is worth screening.
- G5: A is the only option that addresses the pair-vs-case-vs-harness uncertainty.
- Wait has no recorded cost (no deadline in the card), so a documented hold is a good outcome.

Re-open triggers to record with the hold: a new non-deprecated z.ai model; owner confirms an Anthropic arm is permitted for unattended runs; offline diagnosis shows the cases (not the pair) are the problem.

## Out of Scope (for the recommended option)

- Any change to `SEPARATION_MARGIN`, the acceptance code, case definitions, or the registry.
- Any paid run (screening or series); any ADR-6 change.
- Fixing flash run fragility, lice's oracle mismatch, dashboard mocks.

## Assumptions to Validate

- Existing run records retain enough detail (stage reach, failure reasons) to classify the 7 lost weak runs. [UNVERIFIED]
- Variance in the existing scores is representative (cat-cafe n=6; geotext strong n=1 is too thin to estimate).
- The corpus has no near-term consumer with a deadline (card says "not scheduled"). Owner to confirm.
- The z.ai catalog can be inspected read-only at no cost. [UNVERIFIED]
