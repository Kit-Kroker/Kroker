# Data Model: 004

No persisted schema is added. Three small shapes change or appear.

## Role model resolution (derived, not stored)

| Value | Source | Used for |
|---|---|---|
| registry model | `agents/<role>/agent.yaml` via `STAGE_MODELS` / `REGISTRY` | default call, default key, default label |
| run model | `resolve_role_model(cfg, stage)` (unchanged) | label, price, ADR-6, memo key input |
| forwarded model | `forwarded_model(cfg, role)`: the override if present and different from the registry model, else `None` | the `model=` argument; the guard |

Invariant: when the forwarded model is not `None`, it equals the label the caller passed to `_run_role`. Violation is a non-retryable failure of that call.

## ResearchDeps (changed)

| Field | Type | Rule |
|---|---|---|
| `research_model` | `str \| None`, default `None` | Omitted from serialization when `None`, so no-override activity inputs are byte-identical. Set only when the run overrides `research` with a non-registry model. Must cross to the activity when set. |

Existing fields and the model's `extra` policy are unchanged.

## Memo key model slot (changed value, same shape)

| Case | Slot value |
|---|---|
| run model == registry model | `<model>` (as today) |
| run model != registry model | `fwd1:<model>` |

`content_key(stage, input_json, prompt_sha, model_id, upstream_recall_ref)` keeps its signature.

## Proposer override validation result

Not a stored entity. A rejected override raises `RegistryError` (CLI, benchmark) or yields a graph `Problem` with a new problem code (graph validation). Message carries role, offending string, accepted form.

## Benchmark inventory row (research artifact, `inventory.md`)

`location`, `bench_run_id`, `case`, `arm`, `role`, `labelled_model`, `answering_model` (registry), `evidence path`. Locations with no records get one row saying so.
