# Contract: corpus staleness and re-label output (round 019)

## §1 `benchmark corpus`: stale column (FR-009)

Output format is unchanged: the same columns, widths and tally line
(`B/corpus.py` `render_corpus_status`). Only the set of rows that print
`yes` in the Stale column grows.

The RED tests, written first in `tests/test_benchmark_corpus.py`, call
`corpus_status(cases_root=tmp)` over synthetic case directories. Each case
gets a `case.yaml` with two arms and an `acceptance.yaml` written via
`save_acceptance`, plus a stub `oracle/` whose identity matches the record.
Oracle drift is never the cause in these tests.

| # | Case role | Record separation (strong, weak) | Case (strong_arm, weak_arm) | Expected `stale` | In tally if provisional? |
|---|---|---|---|---|---|
| T1 | corpus | (A, B) | (C, B), strong changed | `True` | no |
| T2 | corpus | (A, B) | (A, C), weak changed | `True` | no |
| T3 | corpus | (A, None) | (A, B), weak newly declared | `True` | no |
| T4 | corpus | (None, None), a "no strong_arm configured" record | (A, B) | `True` | no |
| T5 | corpus | `separation: null` | (C, D) | `False` | yes |
| T6 | parked | sentinel (None, None) | (A, B) | `False` | n/a (not corpus) |
| T7 | corpus | (A, B) | (A, B), unchanged | `False` | yes, and the tally line counts it |

- T1 and T7 together pin the tally effect. With both records `provisional`,
  the tally line reads `1 of 8 accepted or provisional`. T1's row is not
  counted.
- Every test fails before the `B/corpus.py` change except T5, T6 and T7,
  which pin unchanged behaviour. The RED run must show exactly T1–T4
  failing.

## §2 Re-label output (FR-005, FR-007)

`python -m sdlc.cli benchmark accept --case <id>` prints one line:
`<case_id>: <verdict>[ (<reason>)]`. The expected lines, per research D-3:

```
cat-cafe-monitoring: not_assessed
deveval-geotext: not_assessed
deveval-readtime: not_assessed
deveval-lice: rejected (reference)
deveval-hone: not_assessed
deveval-particle-swarm-optimization: not_assessed
deveval-stocktrends: not_assessed
theatre-box-office: not_assessed
```

Any other line fires SG-2. The written file must also satisfy
data-model §2's gated fields.

## §3 `benchmark corpus` after Step 4 and Step 5

- **Tally line**: `0 of 8 accepted or provisional, 0 of <EXIT_PRIVATE>
  private`, where `EXIT_PRIVATE` is the existing constant.
- **Stale column**: no row prints `yes`, because each record was re-written
  against the current arms.
- **Unchanged rows**: the rows for todo-api-greenfield (smoke),
  add-login-greenfield and crew-probe (probe) are identical to
  `baseline.md`.
