# Data Model: glm-5.2 Arm Retirement (round 019)

No new entity and no new field. This round changes values in existing
config and records, and one derived flag (`CorpusRow.stale`) gains a
second cause.

## §1 Case (`case.yaml`), re-paired form

The same edit applies to all eight cases: seven in the repo plus
`PRIV/cases/theatre-box-office`. Every other key is unchanged.

| Key | Before | After |
|---|---|---|
| `strong_arm` | `zai-coding-plan-glm-5.3-flash` | `zai-coding-plan-glm-5.3` |
| `weak_arm` | `zai-coding-plan-glm-5.2` | `zai-coding-plan-glm-5.3-flash` |
| `arms[]` | `zai-coding-plan-glm-5.2` (dev/test/devops = `zai-coding-plan/glm-5.2`), then `zai-coding-plan-glm-5.3-flash` | `zai-coding-plan-glm-5.3` (dev/test/devops = `zai-coding-plan/glm-5.3`), then `zai-coding-plan-glm-5.3-flash`, unchanged byte-for-byte |
| `models` | `[zai-coding-plan/glm-5.2]` | `[zai-coding-plan/glm-5.3, zai-coding-plan/glm-5.3-flash]` |
| `extra_args_by_model` | `{zai-coding-plan/glm-5.2: [--variant, max]}` (cat-cafe, theatre only) | key removed |
| `role` | unchanged (`corpus` or `parked`) | unchanged |

**FR-006 comment block**: YAML comments directly above `strong_arm:`.

```yaml
# R019 2026-10-27: glm-5.2 retired (zai-coding-plan catalog deprecated it;
# opencode refuses resolution -> ProviderModelNotFoundError). Old pair:
# strong glm-5.3-flash / weak glm-5.2. New pair (GATE 1 Q0=A): strong
# glm-5.3 / weak glm-5.3-flash. Prior verdict: <verdict> [<reason>],
# <strong mean> vs <weak mean>[, note]. Re-proving needs reruns of both
# arms on one commit (follow-up card 2026-10-27-r019-reprove-separation-reruns).
```

Values come from `baseline.md`, which is captured from `git show HEAD:` before
any accept. For parked cases with no separation, write "Prior verdict:
not_assessed (parked)".

**Validation** (existing `CaseSpec`, `B/models.py:402–419`): both arm names
are declared and differ. `models` is non-empty.

## §2 Acceptance record (`acceptance.yaml`), after re-label

The file is written by `save_acceptance`, never by hand. Expected values
(research D-3):

| Field | cat-cafe / geotext / readtime / theatre | lice | hone / pso / stocktrends |
|---|---|---|---|
| `verdict` | `not_assessed` | `rejected` | `not_assessed` |
| `reason` | `null` | `reference` | `null` |
| `note` | `no strong arm runs` | the reference detail (30/31 …) | `separation not assessed for parked case` |
| `oracle_id` | unchanged | unchanged | unchanged |
| `separation.strong.arm` | `zai-coding-plan-glm-5.3` | `zai-coding-plan-glm-5.3` | `null` (sentinel) |
| `separation.strong.run_ids` | `[]` | `[]` | — |
| `separation.weak.arm` | `zai-coding-plan-glm-5.3-flash` | `zai-coding-plan-glm-5.3-flash` | `null` |
| `separation.weak.run_ids` | the case's existing flash run id(s) | `[]` (no stored lice runs) | — |
| `separation.not_comparable` | ≥ the count of glm-5.2 graded runs | 0 | 0 |
| `kroker_commit` | the 8-char HEAD passed as `KROKER_COMMIT` | same | same |

**Lice correction (reviewer plan pass 1, gap 1).** Lice's current record
has `separation: null` because it was written by an offline accept. An
online re-label computes a separation for every corpus case regardless of
the reference result (`cli.py:526–546`), so the new record carries the
computed shape above. The verdict is unaffected: `decide()` checks the
reference first (`acceptance.py:175`).

Gated fields (SG-2): `verdict`, `reason`, `separation.strong.arm`, and an
empty `separation.strong.run_ids`. Logged only: `oracle_tests`, reference
and floor counts, `not_comparable`.

## §3 Corpus row staleness (`B/corpus.py`)

`CorpusRow.stale: bool | str` (unchanged type). The decision order:

1. No record → `"not assessed"` (unchanged).
2. Oracle drift → `True` (unchanged): the current oracle id differs from
   `record.oracle_id`, or the oracle is gone while the record has one.
3. **New, arm drift → `True`.** It applies when `spec.role == CORPUS` and
   `record.separation is not None` and:

   ```
   (sep.strong.arm if sep.strong else None, sep.weak.arm if sep.weak else None)
       != (spec.strong_arm, spec.weak_arm)
   ```
4. Otherwise → `False`.

The tally (unchanged) counts only `role == CORPUS and stale is False and
verdict in {accepted, provisional}`.

**Known limits** (research D-6): name-only comparison; `separation: null`
records are never arm-stale.

## §4 Shipped harness defaults

| Location | Before | After |
|---|---|---|
| `agents/test/agent.yaml` `model` | `zai-coding-plan/glm-5.2` | `zai-coding-plan/glm-5.3` |
| `S/core/models.py` `PipelineConfig.roles["test"].model` | `zai-coding-plan/glm-5.2` | `zai-coding-plan/glm-5.3` |
| `tests/conftest.py` mirror fixture `test` | `…glm-5.2` | `…glm-5.3` |
| `B/importers/deveval.py` `models` default | `["zai-coding-plan/glm-5.2"]` | `["zai-coding-plan/glm-5.3"]` |
