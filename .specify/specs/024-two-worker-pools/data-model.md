# Data model — round 024 (two worker pools)

`S/` = `src/sdlc/`. This round adds no storage and no new workflow state. Everything here is configuration, or one optional input field.

## `S/pools.py` (new leaf module; imports only the stdlib and `temporalio.api`)

| Name | Kind | Value / rule |
|---|---|---|
| `HARNESS_QUEUE_DEFAULT` | `str` | `"ai-sdlc-harness"`. It is documented, and used only when an operator sets `KROKER_HARNESS_QUEUE` to the empty-but-on sentinel `"default"` |
| `HARNESS_ACTIVITIES` | `frozenset[str]` | the 28 names in research R2's harness rows |
| `PoolMode` | `StrEnum` | `ALL = "all"`, `CORE = "core"`, `HARNESS = "harness"` |
| `on_harness(opts, queue)` | pure fn | research R3 |
| `resolve_harness_queue(env=os.environ)` | pure fn | `None` if unset or blank; `HARNESS_QUEUE_DEFAULT` if `"default"`; else the value. Names must match `^[A-Za-z0-9._-]{1,200}$`, else `ValueError` |
| `require_harness_poller(client, queue, …)` | async fn | research R6. Raises `HarnessQueueUnpolled` |
| `HarnessQueueUnpolled` | `RuntimeError` subclass | the message names the queue and the remedy (`KROKER_WORKER_POOL=harness`) |
| `pool_boot_plan(mode, queue, cap)` | pure fn → `PoolBootPlan` | validates the R5 refusals; it is the unit-testable core of `worker.main` |
| `PoolBootPlan` | frozen dataclass | `core_worker: bool`, `harness_worker: bool`, `janitor: bool`, `cap: int \| None`, `queue: str \| None` |

### `pool_boot_plan` truth table

| mode | queue | cap | → core_worker | harness_worker | janitor | result |
|---|---|---|---|---|---|---|
| all | — | — | ✓ | ✗ | ✓ | today, exactly |
| all | — | set | | | | **refuse** (a cap without a queue) |
| all | q | any | ✓ (all activities) | ✓ (harness set, cap) | ✓ | |
| core | — | any | | | | **refuse** (core needs a queue) |
| core | q | any | ✓ (core activities only) | ✗ | ✗ | the cap is ignored, with a warning |
| harness | — | any | | | | **refuse** |
| harness | q | any | ✗ | ✓ (cap) | ✓ | |
| any | any | < 1 | | | | **refuse** |

## The routing field (R1)

`harness_queue: str | None = Field(default=None, exclude_if=lambda v: v is None)` is added to:
- `PipelineConfig`
- `TriageInput`
- `AssessmentInput`
- `TidyUpInput`
- `DeploymentInput`
- `CrewTaskInput`
- `CaseSpec`
- `MaintenanceConfig`

**Validation:** the same name regex as `resolve_harness_queue`, checked by a field validator.

**Invariant:** the field is set only by client start paths (research R6), and it is never mutated inside a workflow. Children copy it verbatim.

### Inheritance (child start sites)

| Parent | Child start | How it is copied |
|---|---|---|
| benchmark | `S/benchmarks/workflow.py:373` | `_cell_config` (`:90`) sets `cfg.harness_queue = spec.harness_queue` |
| tidy-up | `S/workflows/tidyup.py:194, 204, 229` | `fix_cfg.model_copy(update={"harness_queue": inp.harness_queue})`; `TriageInput(…, harness_queue=…)` |
| assessment | `S/workflows/assessment.py:371` | `TriageInput(…, harness_queue=inp.harness_queue)` |
| maintenance | `S/workflows/maintenance.py:189`; `S/workflows/maintenance_execute.py:260, 491, 505` | from `state.cfg.harness_queue`, into the `TriageInput` / child `PipelineConfig` |
| graph → crew | `S/stages/code/step.py:280` | `CrewTaskInput(…, harness_queue=cfg.harness_queue)` |
| graph → deploy | `S/stages/deploy/step.py:138` | `DeploymentInput(…, harness_queue=cfg.harness_queue)` |
| pipeline child | `S/workflows/pipeline_child.py:53, 82` | free: `run_input.cfg` already carries it |

## Environment (research R5)

| Var | Read by | Meaning |
|---|---|---|
| `KROKER_WORKER_POOL` | `worker.main` | the pool mode (default `all`) |
| `KROKER_HARNESS_QUEUE` | `worker.main` and every client start path | the harness queue. Unset means single pool, routing off |
| `KROKER_HARNESS_CAP` | `worker.main` | `max_concurrent_activities` for the harness `Worker` |
