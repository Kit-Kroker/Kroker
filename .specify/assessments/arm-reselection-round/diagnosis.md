# Offline Diagnosis: why the glm-5.3 / flash pair did not separate

- **Slug**: arm-reselection-round
- **Created**: 2026-11-08
- **Cleared by user**: offline only. Reads of committed files and local files; no paid runs, no model/provider calls, no network. Nothing written outside `.specify/assessments/arm-reselection-round/`.
- **Owner questions NOT answered and NOT assumed**: (1) what the corpus is for; (2) whether an Anthropic subscription arm may run unattended.

Statements are tagged `[file:line]` for committed evidence, `[derived]` for arithmetic done in this session on that evidence, `[inference]` where I am reasoning past the record, and `[UNVERIFIABLE]` where the record is not on this machine.

## What is and is not available offline

- **Run records and logs are not on this machine.** `runs/benchmarks/` does not exist (only `runs/pipeline/` is present); the recorder default is `runs/benchmarks` [`src/sdlc/benchmarks/recorder.py:17`] and the series wrote to a Windows host volume `D:/own/Kroker/runs` [`.workspace/tasks/2026-10-27-r019-reprove-separation-reruns.md`, command block]. A filesystem search for the series' bench ids (`1793263254`, `1793592253`) found them only inside the two `acceptance.yaml` files. `docker-compose.override.yml` and `.env` (which hold the private-store path) are also absent, and `SDLC_PRIVATE_CASES_ROOT` is unset here [`src/sdlc/benchmarks/paths.py:26`]. So **per-run failure logs, stage-reach records of lost runs, and the whole `theatre-box-office` record are unavailable**; everything below about those is limited to committed summaries.
- **Committed evidence that does exist:** three `acceptance.yaml` files with per-run scores, run ids and `stall_points` (graded runs only) [`benchmarks/cases/{cat-cafe-monitoring,deveval-geotext,deveval-readtime}/acceptance.yaml`], the decision code [`src/sdlc/benchmarks/acceptance.py`], and prose in `BENCHMARK.md`, the series card and `docs/roadmap/last-verified-log.md`.
- **Structural limit:** `check_separation` counts only `status == "graded"` runs; others are skipped or counted `not_comparable` [`acceptance.py` loop at ~100-120]. A *lost* run therefore never appears in `acceptance.yaml`. Lost-run counts can only be inferred from missing bench ids, and `not_comparable` (cat-cafe 11, geotext 2, readtime 2) mixes other-oracle and other-arm graded runs, so a missing id is not proof of loss.

## (a) The "7 lost weak runs": flash-specific or harness-wide?

**Verdict: cannot be established from committed data; the evidence on hand argues against "flash-specific" as the card states it.**

1. **The "7" is prose only.** It appears in `BENCHMARK.md:77-78` ("Weak-arm fragility was systemic (7 lost weak runs)"), the series card ("clarify/architect/plan/review") and `docs/roadmap/last-verified-log.md:13`. No committed file lists the seven runs, their arms' stages or causes. `[UNVERIFIABLE]`
2. **Visible gaps by bench id** (a bench id is `bench-<case>-<epoch>`; both arms of one bench share the id) `[derived]` from the run_ids:
   - cat-cafe: strong graded in 6 benches; weak graded in 5 of those plus the carried 2026-10-16 run `1792148180` [`cat-cafe-monitoring/acceptance.yaml:44-56, 66-80`]. Bench `1793291808` (2026-10-29T16:36Z) has a strong run and **no weak run** → **1 weak run absent**.
   - readtime: strong graded in 3 benches; weak in **none** [`deveval-readtime/acceptance.yaml:26-41`] → **3 weak absent** (consistent with "died at clarify 3/3", `BENCHMARK.md:698`).
   - geotext: weak graded in 3 benches (`1793542173`, `1793553763`, `1793569657`); strong graded in **only** `1793569657` [`deveval-geotext/acceptance.yaml:26-40`] → **2 strong runs absent**, 0 weak absent.
   - theatre: unavailable. `[UNVERIFIABLE]`
   Visible total: **4 weak absent** (1 cat-cafe + 3 readtime), **2 strong absent** (geotext). The card's 7 therefore leaves ~3 weak unaccounted for (theatre and/or pre-fix cycles).
3. **Hypothesis "fragility is flash-specific" is not supported.** Geotext's strong arm has two absent benches and its strong figure rests on n=1. The absence could be loss or `not_comparable` (2 on geotext [`geotext/acceptance.yaml:45`]), so this is `[inference]`, but the card's framing ("weak arm systemically fragile") reads the asymmetry as a flash trait while the same data shows a strong-arm gap on a different case. Readtime is the one clean flash-only failure (0 of 3).
4. **The ADR-6 collision explains pre-fix losses only.** The adversary/weak-arm id collision "silently killed every weak cell" until `7a43462c` [`last-verified-log.md:13`; commit `7a43462c` dated 2026-10-28T23:39+01:00 = 22:39Z]. Every bench id with a weak result in the three files is dated 2026-10-29 or later [`derived` from epochs: 1793263254 = 2026-10-29T08:40Z … 1793609614 = 2026-11-02T08:53Z], i.e. **after** the fix, except the carried `1792148180` (2026-10-16). So the collision cannot account for the post-fix absences in the table above; it may account for some of the card's seven if pre-fix cycles were counted. `[inference]`
5. **Stage of loss.** Only the card's prose names stages ("clarify/architect/plan/review") and readtime "clarify" [`BENCHMARK.md:698`]. Which loss was which, and whether any were provider 429/5xx rather than model behaviour (backoff landed in `dea09d36`, 2026-10-27 [`git log`]), is not recoverable offline. `[UNVERIFIABLE]`
6. **Stall points of graded runs** (the only stage data committed): cat-cafe strong deploy ×4, merge ×2; cat-cafe weak deploy ×4, merge ×1 (5 entries for 6 scores, so one weak graded run has no `stage_reach`) [`cat-cafe-monitoring/acceptance.yaml:57-64, 81-86`]; geotext weak merge ×3, strong merge [`geotext/acceptance.yaml:27-30, 40-43`]; readtime strong merge, deploy, merge [`readtime/acceptance.yaml:32-36`]. So graded runs of **both** arms reach deploy/merge and stop there; scores reflect partial pipeline completion.

**What a real answer needs** (outside this clearance): the run records under `runs/benchmarks` on the host that ran the series, or `benchmark` record exports.

## (b) Variance, power, and whether readtime / theatre are too flat

All figures `[derived]` from the per-run scores in the acceptance files.

| Case / arm | n | scores | mean | sample SD |
|---|---|---|---|---|
| cat-cafe strong | 6 | .694 .722 .889 .861 .917 .889 [`cat-cafe:44-56`] | 0.829 | 0.095 |
| cat-cafe weak | 6 | .833 0.0 .75 .917 .778 .944 [`cat-cafe:66-80`] | 0.704 | 0.353 |
| cat-cafe weak, 0.0 run dropped | 5 | (as above) | 0.844 | 0.085 |
| geotext strong | 1 | .667 [`geotext:26`] | 0.667 | undefined |
| geotext weak | 3 | .333 .556 .889 [`geotext:36-39`] | 0.593 | 0.280 |
| readtime strong | 3 | .333 .167 .167 [`readtime:26-31`] | 0.222 | 0.096 |
| readtime weak | 0 | none | none | none |

1. **The cat-cafe "margin" is not distinguishable from zero.** Difference 0.125, Welch SE 0.149, t ≈ 0.84. The weak arm's mean is driven by one 0.0 run. **Without that single run the weak mean (0.844) exceeds the strong mean (0.829)**, so the 0.125 gap and the card's "flash best scorer" both depend on how one failure is treated. The card's 0.92-0.94 figures are the two highest of six flash scores, but they sit beside a 0.0 and the means are 0.704 vs 0.829 [`cat-cafe:66-80`].
2. **Runs needed to resolve a 0.15 margin** (two-sided α = 0.05, power 0.80, normal approx., n = 2((1.96+0.84)·SD/0.15)²):

   | per-arm SD | n per arm |
   |---|---|
   | 0.10 | 7 |
   | 0.15 | 16 |
   | 0.20 | 28 |
   | 0.30 | 63 |
   | cat-cafe pooled SD 0.259 | **47** |

   The rule requires only `MIN_RUNS_PER_ARM = 3` [`acceptance.py:17`, `:248`] and compares means against 0.15 with no variance test [`acceptance.py:~133`, `:241-243`]. At the observed spread, n = 3 per arm cannot reliably tell a true 0.15 gap from none, so **acceptance at n = 3 is largely luck in either direction**. This is a property of the rule, not a reason to lower the margin; it bears on how many runs any pair would need. (The within-arm SD is inflated by failure runs; if failures are scored separately from graded quality the SD could be ~0.09 as in the strong arm, giving n ≈ 6-7. That is a measurement-design question, not decided here.)
3. **Readtime is a floor case for this strong model.** Strong mean 0.222 (max 0.333) [`readtime:26-31`]; all three strong runs stop at merge or deploy [`readtime:32-36`]. A pair on this case would be separating two arms near the floor. It is not "too flat" in the SD sense (strong SD 0.096) but its headroom is low, and with 0 weak runs it yields no separation evidence at all. Whether a stronger arm clears it is untested.
4. **Theatre: both arms flat, but the record is not available.** `BENCHMARK.md:706-709` gives strong 0.018 vs weak 0.018, margin 0.000, "both arms flat on the oracle, n=3 valid cycles"; the earlier round-016 pair also scored 0.0179 each and "failed at `merge`" [`BENCHMARK.md:710-716`]. The brief suggests treating this as an unassessed stall. **Checked against the rule, the recorded verdict (`rejected no_separation`) means the stalled condition did not fire.** The stalled branch needs every graded run in both arms to have `stage_reach`, credit ≤ 0.05, one shared `last_stage`, and that stage not completed [`acceptance.py:195-221`, `STALL_EPSILON` at `:16`]. Credits of 0.018 satisfy the second condition, so the recorded outcome implies at least one of: some run lacked `stage_reach`, or the runs did not share one last stage, or a stage completed. Which one cannot be determined without the private record. `[UNVERIFIABLE]` and `[inference]`. Consequence: the 2026-11-03 theatre `rejected` label may be a mislabel of a stall (an under-specified record) rather than a measured null; the older round-016 note already says a stalled evaluation would give `not_assessed` [`BENCHMARK.md:714-716`]. This is the one item where the card's reading (theatre = no separation) and the code's own rule may disagree.
5. **Too flat for any pair?** For theatre the evidence is consistent with a floor (0.018 under two pairs, two eras) but cannot be confirmed offline. For readtime the evidence is a low ceiling for the strong arm only. Neither can be declared "unseparable by any arm" from this data; that claim would need at least one run of a third model on them.

## (c) z.ai coding-plan catalog today (repo files and docs only)

**Result: the repo contains no catalog listing, and no non-deprecated model beyond the two in use is evidenced.**

- Committed facts about the catalog: z.ai deprecated `glm-5.2`, `glm-4.7`, `glm-5-turbo` and `glm-5.2-highspeed` in the `zai-coding-plan` catalog, and opencode filters deprecated models at resolution (`ProviderModelNotFoundError`) [`BENCHMARK.md:34-38`]; the glm-5.3 family declares no opencode variants [`BENCHMARK.md:40-42`]; `zai:glm-5.2` requests on the coding endpoint are answered by glm-5.3, "the served model follows the endpoint" [`README.md:322-324`].
- Models in use in the repo: `zai-coding-plan/glm-5.3` (dev/test/devops defaults, `src/sdlc/core/models.py:374-376`; `agents/test/agent.yaml:3`, `agents/devops/agent.yaml:3`), `zai:glm-5.3` (proposer roles, e.g. `agents/clarify/agent.yaml:2`, `agents/architect/agent.yaml:2`), and `zai:glm-5.3-flash` (`agents/discover/agent.yaml:2`). A grep of `src agents benchmarks/config.yaml pyproject.toml` for `glm-5.[4-9]` or `glm-6` returned nothing.
- Not found: any pricing table, model list or opencode model cache in the repo. A local `~/.cache/opencode` contains only `bin`; I did not read user configs outside the repo and made no provider call, per the clearance.
- **Therefore** (i) the claim "a glm-5.4+ may arrive" is unevidenced in the repo; (ii) which other models the current catalog lists is `[UNVERIFIABLE]` offline; answering it needs a provider/CLI listing (one cheap, read-only call), which this clearance does not cover.
- Side note relevant to pair design: the proposer reviewer ships as `zai:glm-5.3` while the dev arm model is `zai-coding-plan/glm-5.3`, the same weights that the ADR-6 amendment says the family check does not catch [`docs/adr.md` ADR-6 amendment, "Amended 2026-10-11"; `agents/reviewer/agent.yaml:5`]. Any new pair inherits that unresolved identity check.

## Effect on the hypotheses (card / decision.md / skeptic's notes)

| Hypothesis | Status after diagnosis |
|---|---|
| Weak-arm fragility is the dominant failure and is flash-specific | **Not established.** 4 weak and 2 strong benches visibly missing; readtime is the only clean flash-only loss; logs absent. |
| Flash is the strong scorer, so flash-strong clears a bar | **Contradicted for the mean** (0.704 vs 0.829) and fragile to one run (0.844 without the 0.0 run, higher than strong). Not a basis for a bar. |
| The pair does not separate | **Holds under the rule**, but the rule at n=3 cannot resolve 0.15 at observed spread (n≈47/arm at pooled SD, 6-7 if failures are excluded). The non-separation is a weak finding, not a strong negative. |
| Cases (readtime, theatre) may be the problem | **Partly supported:** readtime strong 0.22, theatre ~0.02. Theatre's `rejected` label may be a stall mislabel; unverifiable offline. |
| A future z.ai model will give a pair | **Unevidenced** in repo. |
| Absolute-bar acceptance can be set without tuning | **No evidence for any bar** that is not post-hoc; also lost-run handling is undefined (lost runs are invisible to the current rule). |

## Remaining gaps (not answerable at this clearance)

- [NEEDS CLARIFICATION: owner — corpus purpose and the near-term consumer.]
- [NEEDS CLARIFICATION: owner — may an Anthropic-family arm run on subscription via `claude -p` unattended?]
- [NEEDS CLARIFICATION: run records from the host volume `D:/own/Kroker/runs` (or exports) to classify the 7 losses by arm, stage and cause. Zero spend, but data not on this machine.]
- [NEEDS CLARIFICATION: private-store `theatre-box-office` record (commit `64a96ac` in the private store) to resolve stall vs no-separation.]
- [NEEDS CLARIFICATION: a read-only provider/CLI model listing to settle (c); not covered by this clearance.]
