# Idea Research: Arm re-selection round

- **Slug**: arm-reselection-round
- **Created**: 2026-11-08
- **Evidence confidence (overall)**: medium — repo evidence is high-confidence for the public and cat-cafe cases; the private `theatre-box-office` case and everything about z.ai catalog timing, a second paid provider, and Anthropic arm feasibility are unverified.

Verification baseline: `benchmarks/cases/*/acceptance.yaml` at main `9a302401` (kroker_commit `7a43462c`), `BENCHMARK.md` (markers and §5.1), `src/sdlc/benchmarks/acceptance.py`, `docs/adr.md` ADR-6, `benchmarks/config.yaml`. No web fetches. No paid runs.

## Card numbers vs. evidence (hypotheses checked)

| Card claim | Verdict | Evidence |
|---|---|---|
| margins 0.000 / 0.074 / 0.125 vs 0.15 bar | **Confirmed** | cat-cafe 0.1250, geotext 0.0741 (acceptance.yaml); theatre 0.000 per BENCHMARK.md only (private store, not inspectable here); `SEPARATION_MARGIN = 0.15` at `acceptance.py:15` |
| readtime weak arm died at clarify 3/3 | **Confirmed as "no weak runs"** | readtime acceptance.yaml: `weak.run_ids: []`, note "no weak arm runs". "Clarify" cause is from BENCHMARK.md prose only (run records not re-read) |
| "n up to 6/arm" | **Partly misleading** | Only cat-cafe has n=6/arm. geotext has **strong n=1**, weak n=3. readtime strong n=3, weak n=0. theatre n=3 valid cycles per BENCHMARK.md |
| "flash was the series' best scorer (0.92–0.94 on cat-cafe, above glm-5.3's mean)" | **Not supported as a summary** | Flash cat-cafe scores: 0.833, 0.0, 0.75, 0.917, 0.778, 0.944 → mean **0.704**, below glm-5.3's **0.829**. 0.917/0.944 are the two best of six runs; one flash run scored 0.0. glm-5.3's max is 0.917 and its min is 0.694 (more consistent). One flash score (0.833, run `1792148180`) is a carried cross-commit run, not same-commit |
| "7 lost weak runs across the series" | **Unverifiable here** | Only BENCHMARK.md/card prose. Consistent with cat-cafe weak `stall_points` having 5 entries for 6 scores, and readtime 0 weak |
| flash-strong "turns two arms separate into clearing an absolute bar" | **Not demonstrated** | flash means by case: cat-cafe 0.704, geotext 0.593, readtime none, theatre 0.018. No candidate bar that is not post-hoc fitted is cleared on more than one case |

## Users & Demand

- The only consumer is the project itself: the corpus tally is **0 of 8 accepted/provisional, 0 of 2 private**, so there is currently no accepted benchmark case for measuring pipeline changes. — [source: BENCHMARK.md §5.1 corpus table; `d5d76150`] (confidence: high)
- No external user demand or deadline is recorded; the card is "Not scheduled — opens on the user's word". — [source: card] (high)
- What the corpus is *for* (detecting pipeline regressions vs. discriminating models) is not stated in the card. — [ASSUMPTION: BENCHMARK.md §5 treats strong/weak separation as validity evidence that a case discriminates quality] (medium)

## Prior Art

- **glm-5.2 / glm-5.3-flash pair (pre-R019):** cat-cafe was provisional (+0.361, n=1), geotext inverted (−0.556), readtime near-tie (+0.083), theatre flat. Separation was already weak or an n=1 artifact before the model retirement. — [BENCHMARK.md corpus table] (high)
- **R019 re-pair to glm-5.3 / flash:** the same-provider re-pair, tested at n≥3 same-commit, did not separate. This is the second pairing within one provider that failed, suggesting same-family tiers (strong vs. flash) are close on these tasks. — [acceptance.yaml ×3; markers] (high on the fact, medium on the generalization)
- **Archived confound:** "carried flash evidence is cross-commit confounded (research D-3)"; the series fixed this by rerunning both arms on `7a43462c`. cat-cafe's weak pool still includes one carried run. — [BENCHMARK.md break marker; cat-cafe weak run_ids] (high)
- **R015 screening precedent:** `parked` cases were screened by cheap runs (hone saturated, stocktrends degenerate). Screening before full series is established practice. — [BENCHMARK.md :691-703] (high)
- **Existing absolute-style verdicts:** `decide()` already has `saturated` (strong 1.0 on all runs) and `degenerate` (strong 0.0 on all runs) branches, i.e. absolute-score semantics exist at the edges. — [`acceptance.py`, `decide()`] (high)

## Market & Context

- **Option 3 (wait):** z.ai deprecated glm-5.2, glm-4.7, glm-5-turbo and glm-5.2-highspeed in the `zai-coding-plan` catalog by 2026-10-27, so the catalog churns, and churn is also an ongoing arm-retirement cost. Whether a glm-5.4+ exists or when is not evidenced. — [BENCHMARK.md break marker] (medium; timing is an ASSUMPTION)
- **Cost of doing nothing:** no paid spend, no accepted corpus cases, so benchmark-gated claims (ROADMAP "Last-verified" items) stay unprovable; the tally has not moved off 0 of 8 across the R019 series. — [ROADMAP / BENCHMARK.md] (medium)
- **Cost already sunk:** the series ran 2026-10-27 → 11-03 including a 39h host outage, two lost smokes, an ADR-6 id-collision fix. — [r019 card errata] (high)

## Data & Constraints

- **Acceptance code surface for no-weak (Option 1):** `weak_arm: str | None` is already optional in `models.py:403`, and `ArmEvidence` for weak is optional in `check_separation`. But `decide()` returns `NOT_ASSESSED, "no weak arm runs"` whenever the weak arm lacks scores (`acceptance.py` after the degenerate branch), and `SEPARATION_MARGIN` is only a gap. So a no-weak mode needs a new verdict branch, a bar constant, and `benchmark accept`/`corpus` and test changes (`tests/test_benchmark_acceptance*.py`, `test_benchmark_corpus.py`, `test_benchmark_matrix.py`). — [src grep] (high that the work is needed; effort estimate is ASSUMPTION)
- **Absolute bar needs a pre-registered threshold:** with flash means 0.704 / 0.593 / n.a. / 0.018, any bar that makes more than cat-cafe pass would be tuned to the data, which is the same dishonesty the brief excludes for the margin. And readtime strong is only 0.222, so a bar on the *strong* arm would reject readtime too. — [acceptance.yaml; derived] (high on numbers, derived inference)
- **Reliability is a precondition of any bar:** flash lost runs at clarify/architect/plan/review; a single-arm design inherits that fragility without a comparator to absorb it, and a lost run counts how? (undefined). — [BENCHMARK.md marker, card] (medium)
- **ADR-6 constraints (Option 2):** reviewer/architect critic/plan critic/judge must differ from the author **by model, not only provider prefix** (2026-10-11 amendment, plan not built). Today's judge is `anthropic:claude-sonnet-5` and the adversary moved to it (`7a43462c`). An Anthropic-family arm would collide with the judge/adversary and force a third family for all of them. — [docs/adr.md ADR-6; `benchmarks/config.yaml`] (high)
- **Provider budget:** the card says Anthropic access is subscription-only. The Kroker harness set includes `claude -p`, but whether a benchmark arm may be run on a subscription (rate limits, ToS, unattended loops) is not established here. — [card; AGENTS.md harness list] (low) — [NEEDS CLARIFICATION]
- **Pair-selection hazard:** any new pair is again judged on the same 0.15 margin. Cross-provider capability gaps are real but their sign can invert on this harness (geotext inverted under glm-5.2). — [BENCHMARK.md] (medium)
- **Paid-run discipline:** screening/series runs need explicit user clearance (SC-006). Assessment spends nothing. — [card] (high)

## Evidence Against the Idea

- **The card's headline rationale for Option 1 is weaker than stated.** Flash's mean is *below* strong's on both rerun cases with data, flash scored 0.0 once, and it died entirely on readtime. Flash is the *less* reliable arm; making it the sole arm removes the comparator that tolerated its failures.
- **Option 1 is not the same question.** "Pipeline + model clears an oracle bar" does not establish that a case discriminates between pipeline changes; it could be saturated at a model's strength and would pass the bar without sensitivity. The existing `saturated` rule would need an analogue.
- **Margin shortfalls are small relative to noise.** cat-cafe strong scores range 0.694–0.917, weak 0.0–0.944; with σ that large at n=6 the 0.125 margin is not distinguishable from 0.15 or from 0. geotext's strong arm is n=1. The "does not separate" verdict is firm only for the rule as written, not for the underlying capability gap. (A power question, not a case for lowering the margin.)
- **Option 3 costs nothing and may dominate** if the benchmark is not blocking any near-term decision: no recorded deadline exists.
- **Option 2's costs are the largest** (second budget, ADR-6 re-plumbing of judge/adversary/reviewer/critics, possibly the unbuilt ADR-6 model-identity check) with an unverified feasibility premise.
- No evidence was found that a better in-provider pairing exists today. z.ai's catalog contents beyond glm-5.3 / flash were not checked.

## Gaps & Open Questions

- [NEEDS CLARIFICATION: what is the corpus used for in the next ~quarter (ROADMAP items blocked on an accepted case)? This sets the cost of waiting.]
- [NEEDS CLARIFICATION: does the current z.ai `zai-coding-plan` catalog list any non-deprecated model other than glm-5.3 / glm-5.3-flash (e.g. a mid tier)? Cheap, read-only check; not done here.]
- [NEEDS CLARIFICATION: is an Anthropic-family author arm via `claude -p` on subscription permitted for unattended benchmark loops, and what is the rate-limit exposure?]
- [NEEDS CLARIFICATION: theatre-box-office (private store) records and the 7 lost weak runs' root causes were not re-read; are the lost runs flash-specific or harness-wide?]
- [NEEDS CLARIFICATION: how should a lost (non-graded) run count against a single-arm bar?]
- [NEEDS CLARIFICATION: is a distinguishing power analysis (n required for margin 0.15 at observed variance) wanted? It is free (offline) and bears on whether any pair could be accepted at n=3.]

## Sources

- `.workspace/tasks/2026-11-03-arm-reselection-round.md` (repo, read)
- `.workspace/tasks/2026-10-27-r019-reprove-separation-reruns.md` (repo, read)
- `benchmarks/cases/{cat-cafe-monitoring,deveval-geotext,deveval-readtime}/acceptance.yaml` and `case.yaml` (repo, read, commit `9a302401`)
- `BENCHMARK.md` lines 34-80, 630-730 (repo, read)
- `src/sdlc/benchmarks/acceptance.py`, `models.py:403` (repo, read)
- `docs/adr.md` ADR-6; `benchmarks/config.yaml` (repo, read)
- No URLs fetched.
