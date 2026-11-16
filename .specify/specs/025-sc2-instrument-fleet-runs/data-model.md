# Data model — round 025

All additions are defaulted and additive; a pre-025 summary JSON loads unchanged.

| Model | Field | Type | Meaning |
|---|---|---|---|
| `GateOutcomeSummary` | `raised_at` | `datetime \| None = None` | when the gate opened for a human (`GATE_AWAITED.at`); None = never opened for a human, or legacy |
| `ClarificationOutcome` | `raised_at` | `datetime \| None = None` | `CLARIFICATION_ASKED.at` |
| `ClarificationOutcome` | `answered_at` | `datetime \| None = None` | `CLARIFICATION_ANSWERED.at` for that question; None if unanswered |
| `RunSummary` | `operator_instrumented` | `bool = False` | True on every summary written by the 025 builder; separates "measured zero" from "pre-025" |

Derived (not stored), in `S/benchmarks/operator_time.py`:

- `ENGAGEMENT_CAP_S = 600`.
- `Interaction(kind, key, raised_at, decided_at)`; human gates, plus one per clarification batch `(stage, raised_at)` with at least one `answered_by == "human"` question, `decided_at` = the batch's latest `answered_at`.
- `RunOperatorTime(state, interactions, engaged_s, wait_s)` with `state in {not_measured, zero, measured}`. **not_measured** if the marker is false or any human interaction lacks a raise time; **zero** if the marker is true and there are no human interactions.
- `engaged_s = sum(min(decided - raised, cap))`; `wait_s = sum(decided - raised)`; overlap is not merged (upper bound, stated).

`SCRollup` gains: `commits` (set), `commit_flag`, `policy_mix`, `evidence_tier`, `sc2_extra` (zero count, human-touched median and max, wait median). `SCRate` is unchanged; SC-2 and SC-2-all are two `SCRate` rows (criterion names `SC-2` and `SC-2-all`, target `<=15 min`, values in minutes).
