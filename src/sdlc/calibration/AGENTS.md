# calibration/ — editing rules

This package exists because of audit row 8: a proposer's self-reported
`confidence` could skip a human gate with nothing behind it. See
`docs/superpowers/specs/2026-09-10-c7-confidence-gate-design.md`.

**`auto_decision_for` takes the calibration verdict as a required parameter.**
Do not give it a default. A default makes "no evidence was fetched"
indistinguishable from "the evidence passed" — the same defect, one layer up.

**`insufficient_data` is not an error state.** Cold-start buckets, unknown
models, and failed lookups all resolve to it, and it is treated exactly like
`uncalibrated` at the decision. Never collapse it into either neighbour.

**Never pool `LabelSource` populations.** The source is folded into
`bucket_key` so pooling requires building a different key on purpose. A
judge-backed label and a proxy-backed label are not the same measurement.

**No gate name is special-cased.** The merge gate does not auto-approve
because it is never sampled (no ledger row is written for it —
`CalibrationSample.outcome_label` is NOT NULL, so an unlabelled row cannot
exist), not because any code knows its name. Keep it that way — a named rule
is a rule someone can delete.

**`labels.py`, `verdict.py`, `decision.py` and `models.py` are pure.** No
`temporalio`, no I/O, no `ctx`. SQLite lives in `store.py`, reached only
through `activities.py`.

**The agreement constants are a starting position.** `THRESHOLD` and
`EPSILON` are inherited from the rubric-judge loop, which tuned them against
a different population (ruling OQ9(3)). Re-derive them from real collected
samples; do not treat the current values as settled.
