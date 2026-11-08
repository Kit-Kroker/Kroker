# Problem Definition: Corpus has no working acceptance instrument

- **Slug**: arm-reselection-round
- **Created**: 2026-11-08
- **Inputs used**: intake.md, research.md

## Problem Statement

The benchmark corpus currently cannot accept any case (0 of 8 accepted or provisional): the only acceptance instrument, a strong-vs-weak margin of 0.15, was measured on the only available same-provider pair (`glm-5.3` / `glm-5.3-flash`) at n≥3 same-commit and failed on every assessable case, with the weak arm also frequently failing to finish runs. As a result, nothing in the repo can currently be *proven* to discriminate quality changes, and each further paid rerun of the current pair would spend money on an already-answered question.

A sub-problem that sits underneath the one above: it is not established whether the failure is a property of the **pair** (arms too close in capability on these tasks), the **cases** (oracles too hard/flat: readtime strong 0.22, theatre ~0.02 for both arms), or the **harness/pipeline** (weak runs lost at clarify/architect/plan/review). The choice of remedy depends on which.

## Affected Users & Stakeholders

- **Users**: maintainers/orchestrator agents who need benchmark evidence to back claims about pipeline changes (ROADMAP "Last-verified" items) — today they get none from the corpus. — [research: Users & Demand]
- **Stakeholders**:
  - Repo owner (sole decision-maker; clears paid runs per SC-006; controls provider budgets, Anthropic is subscription-only).
  - Whoever relies on ADR-6 invariants — any arm change touches reviewer/adversary/judge model choice.
- [NEEDS CLARIFICATION: are there downstream consumers (roadmap items, release gates) blocked on an accepted case, and by when?]

## Goals

- G1. The corpus can again reach a defensible `accepted` verdict on at least one case, using an acceptance rule fixed *before* looking at new data.
- G2. The acceptance rule remains honest: it is not tuned to the previously observed margins (0.000 / 0.074 / 0.125) or scores.
- G3. Further paid spend is gated on a screening step that can fail cheaply, rather than another full series on an unscreened premise.
- G4. ADR-6 invariants stay true (author model differs from reviewer/adversary/judge by model identity) under whatever arm set results.
- G5. The reason the current pair failed (pair vs. case vs. harness fragility) is understood well enough to choose a remedy, at no spend (existing records only).

## Non-Goals

- Lowering `SEPARATION_MARGIN` (or any threshold) to fit existing data. (Brief, explicit.)
- Any paid run during assessment. Proving runs only on explicit user clearance.
- Fixing flash's run fragility, the lice 30/31 oracle mismatch, or the dashboard mock refresh (separate cards).
- Choosing and designing the solution — that belongs to `shape`/`specify`.
- Re-adjudicating the R019 verdicts themselves; they stand under the rule as written.

## Success Metrics

- Number of corpus cases at `accepted` — baseline **0 of 8** (0 of 2 private). Target: ≥1, with the target and rule stated before the proving run. [NEEDS CLARIFICATION: owner's required number; the research gives no figure]
- Fraction of arm runs lost before grading — baseline: readtime weak 3/3 lost; "7 lost weak runs" series-wide (card figure, unverified here). Target: [NEEDS CLARIFICATION].
- Pre-registration: acceptance rule and thresholds committed before any proving run (binary; qualitative check by diff order).
- Paid-spend discipline: zero paid runs before explicit clearance; screening on 1–2 cases precedes any full series (binary).
- ADR-6 check passes for all roles under the new arm set (binary, existing validator).

## Cost of Inaction

The corpus stays at 0 of 8; benchmark claims remain unprovable and the "Last-verified" tally cannot move. No money is lost by waiting (no ongoing spend), but the pending question stays open indefinitely and z.ai's catalog churn (four models deprecated by 2026-10-27) may force another arm change anyway. Doing nothing for now is a real, cheap option, not a null option. — [research: Market & Context]

## Open Questions

- [NEEDS CLARIFICATION: what is the corpus's intended purpose — detect pipeline regressions, or discriminate model capability? Options differ on this.]
- [NEEDS CLARIFICATION: owner's required number and timing of accepted cases (cost of waiting).]
- [NEEDS CLARIFICATION: is the pair, the cases, or the harness the dominant cause of non-separation? (Answerable offline from existing records: variance, stall points, lost-run causes.)]
- [NEEDS CLARIFICATION: current non-deprecated z.ai catalog entries beyond glm-5.3 / flash.]
- [NEEDS CLARIFICATION: is an Anthropic-family arm on subscription via `claude -p` permitted for unattended benchmark loops?]
- [NEEDS CLARIFICATION: how a lost (non-graded) run counts toward any single-arm bar.]
- [NEEDS CLARIFICATION: power requirement: n needed to resolve a 0.15 margin at observed variance (offline).]
