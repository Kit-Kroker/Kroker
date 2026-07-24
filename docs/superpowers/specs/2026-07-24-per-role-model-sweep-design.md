# E-37 — Per-role model sweep at the benchmark boundary

| | |
|---|---|
| Status | Design — approved to plan |
| Date | 2026-07-24 |
| Roadmap item | E-37 (§9.8); folds E-26 |
| Anchors | US-4, FR-701 (economics), ADR-6, OQ-B2, OQ-E2 |
| Supersedes open question | OQ-B2 (judge independence under model sweep) — answered here |

## 1. Problem

The benchmark's **model × role** axis (BENCHMARK.md §3.2) exists to reproduce
Cursor's economics result: pair a frontier *architect* with a cheaper *developer*
and measure whether quality holds ($1,339 vs $10,565 on the same task). That
experiment **cannot be expressed today**:

- Proposer-role models (`architect`, `planner`, `reviewer`, `clarifier`,
  `analyst`, `qa`) are frozen at import in `STAGE_MODELS`
  (`agents/roles.py:86`), a module-level constant built once from
  `REGISTRY = load_registry()`. The workflow calls `STAGE_MODELS["architect"]`
  directly. There is **no per-run override path** for a proposer's model.
- `PipelineConfig.roles` carries only the three *harness* roles
  (`dev`/`test`/`devops`). The existing benchmark "model" axis
  (`_cell_config`, `benchmarks/workflow.py:48`) overrides those three to one
  **uniform** model per cell — it never touches a proposer.
- ADR-6 (developer-family ≠ reviewer-family, plus the `deep_review` clause) is
  validated **only at boot** by `validate_registry`. A benchmark cell that
  swept `dev` into the reviewer's family would silently violate ADR-6, and
  nothing checks it per cell.

E-26 named the blocker: `PipelineConfig()` is constructed *inside* the workflow
(`feature.py`), so its default cannot read a per-project file, and a per-cell
override must resolve **at the boundary** and satisfy ADR-6 **per run**, not
just at boot. E-37 builds that machinery and wires it at the benchmark boundary
(as *arms*) and at the CLI boundary (as `--role-model`).

Scope note: E-37 delivers the **capability** — per-run role→model resolution,
per-run ADR-6 validation, and the arm shape to express a sweep. Actually
*running* a sweep and reading the numbers is runtime measurement, out of scope.

## 2. Approach (decisions taken)

1. **Matrix shape = named arms**, not a per-role cartesian and not uniform+pins.
   A case declares a small list of explicit role→model *mixes*; each mix is one
   cell arm. This matches the real experiment (a handful of deliberate mixes,
   e.g. `frontier-arch` vs `all-cheap`) and avoids a combinatorial grid.
2. **Judge stays fixed per case; validated at expansion.** One `judge_model`
   keeps cells comparable (quality measured on the same instrument). At matrix
   expansion the judge's family is checked against *every* model in *every*
   arm; a collision fails the whole matrix loudly. (Answers **OQ-B2**: the
   judge does **not** re-resolve per cell.)
3. **Arms override models only.** The harness axis (`harnesses`) stays a
   separate axis applied uniformly to the three harness roles. Per-role
   *harness* selection is out of scope (proposers carry no harness).
4. **CLI gets a minimal `--role-model role=model` flag** through the same
   per-run ADR-6 guard, so US-4 (per-project role config) becomes real rather
   than benchmark-only.

## 3. Components

### 3.1 Per-run role→model resolver (`workflows/feature.py`)

Add a resolver on the workflow:

```python
def _role_model(self, cfg: PipelineConfig, role: str, stage: str) -> str:
    """The model this run uses for `role`. A per-run override in cfg.roles
    wins; otherwise the registry default (STAGE_MODELS[stage])."""
    rc = cfg.roles.get(role)
    if rc is not None and rc.model is not None:
        return rc.model
    return STAGE_MODELS[stage]
```

Replace every `STAGE_MODELS[stage]` call site in `feature.py` (proposer and
harness alike) with `self._role_model(cfg, role, stage)`. The `(role, stage)`
mapping is the existing `STAGE_ROLES` inverse; where a call site already knows
the role (harness roles via `cfg.roles.get(task.role, ...)`) it passes it
directly.

**Memoization (correctness-critical).** `_cached_stage` (`feature.py:384`)
currently keys on `STAGE_MODELS[stage]`. It MUST key on the *resolved* model,
or a per-arm model change leaves the key unmoved and serves a result computed
by a different model — the exact hazard E-3's note describes. Change the memo
key to the resolved model. (Benchmark cells run with `memoization_enabled=False`
by default, but the CLI override path may enable it, so this is not optional.)

### 3.2 `cfg.roles` may carry proposer overrides (`models.py`)

`PipelineConfig.roles` keeps its harness-only **default** (unchanged, so
`_validate_pipeline_mirror` still passes — it checks the class default via
`PipelineConfig().roles`, not an instance). The type already allows any string
key; E-37 documents that a *constructed* `PipelineConfig` MAY carry proposer
roles as overrides, populated only at a boundary (never inside the workflow).
No schema change beyond a comment clarifying the invariant.

### 3.3 Per-run ADR-6 validation (`agents/loader.py`)

New pure function:

```python
def validate_run_roles(resolved: dict[str, RoleConfig]) -> None:
    """Re-run the ADR-6 family-inequality invariants against a run's fully
    resolved role→model map (registry defaults + per-run overrides). Called at
    every boundary that constructs a non-default PipelineConfig."""
```

It reuses the exact dev/reviewer and deep_review family-inequality logic that
`validate_registry` runs at boot — factored into a shared helper so there is
one implementation of the invariant, not two. `resolved` is built by layering
the run's overrides on top of the registry's role map, so a run that overrides
only `dev` still gets checked against the registry's `reviewer`.

This closes the latent hole: the uniform sweep could already put `dev` in the
reviewer's family with nothing checking it.

### 3.4 Arms on `CaseSpec` (`benchmarks/models.py`)

```python
class Arm(BaseModel):
    name: str                                # cell-id component; git-safe
    default: str | None = None               # model for unspecified roles
    role_models: dict[str, str] = {}         # role -> model overrides

class CaseSpec(BaseModel):
    ...
    arms: list[Arm] = []                     # per-role model mixes
    # `models` retained for backward compat: desugared to one arm per model
    # (Arm(name=safe(m), default=m)) when `arms` is empty.
```

`Arm.resolve(registry_defaults) -> dict[str, str]`: the full role→model map
for the arm = `{role: role_models.get(role, default or registry_model)}` for
every role. `default=None` with a role unspecified means "keep the registry
default for that role".

`BenchmarkCell` gains `arm_name: str` and `role_models: dict[str, str]` (the
resolved map). `cell_id` becomes `case#harness#arm_name`.

### 3.5 Expansion & judge guard (`benchmarks/matrix.py`)

`expand_matrix`:
- desugars `models` → arms when `arms` is empty (backward compat);
- for each arm, resolves the full role→model map;
- collects every distinct model across every arm and checks
  `judge_family ∉ {family(m) for every model in every arm}` — extends the
  current harness-only check; raises `SameFamilyJudgeError` on collision;
- emits `harnesses × arms` cells.

### 3.6 `_cell_config` builds `cfg.roles` from the arm (`benchmarks/workflow.py`)

Instead of one uniform `RoleConfig(harness, model)` for every harness role,
build `cfg.roles` from the arm's resolved map: harness roles get
`RoleConfig(harness=cell.harness, model=arm_model)`, proposer roles get
`RoleConfig(kind="proposer", model=arm_model)` **only when the arm overrides
them** (an unspecified proposer is left out of `cfg.roles`, so `_role_model`
falls back to the registry default). Call `validate_run_roles` on the resolved
map before launching the child; a violation records a failed cell, never a
silent bad run. The research-provider injection (§`_cell_config` today) is
unchanged.

### 3.7 CLI `--role-model` (`cli.py`)

`sdlc start` gains a repeatable `--role-model role=model` flag. Parsed into
`cfg.roles` overrides, then `validate_run_roles(resolved)` runs before the
workflow starts; a violation exits non-zero with the ADR-6 message. This is the
US-4 surface: a per-project role→model choice that fails closed on ADR-6.

## 4. Data flow

```
CaseSpec.arms ──expand_matrix──▶ cells (harness × arm, judge validated)
   each cell ──_cell_config──▶ PipelineConfig{roles: arm's resolved map}
                                    │ validate_run_roles (ADR-6 per cell)
                                    ▼
                             FeatureWorkflow(idea, cfg)
                                    │ _role_model(cfg, role, stage)  ← per run
                                    │   → override else STAGE_MODELS
                                    ▼
                    per-role BenchmarkRecord.model / RoleUsage (E-33)
```

CLI: `--role-model` → cfg.roles overrides → `validate_run_roles` → same
`FeatureWorkflow` path.

## 5. Testing

- **Resolver**: `_role_model` returns override when present, registry default
  otherwise; a harness role and a proposer role both resolve correctly.
- **Memo key moves with the model**: two runs identical except a per-role model
  override produce different `content_key`s (guards the E-3 hazard).
- **Per-run ADR-6**: `validate_run_roles` raises when an override puts `dev` in
  the reviewer's family; passes when families differ; the `deep_review` clause
  fires when that role is overridden into `dev`'s family.
- **Latent-hole regression**: a uniform-`models` desugared arm that collides
  with the reviewer family is now rejected (was silently allowed).
- **Arm resolution**: `default` fills unspecified roles; `role_models`
  overrides win; `default=None` keeps registry defaults.
- **Expansion judge guard**: judge sharing a family with any model in any arm
  raises `SameFamilyJudgeError`; a clean matrix expands to `harnesses × arms`.
- **Backward compat**: a case with `models` and no `arms` expands exactly as
  before (one arm per model).
- **CLI**: `--role-model` parses `role=model` pairs; an ADR-6-violating pair
  exits non-zero.

## 6. Out of scope (named follow-ons)

- Report/heatmap **slicing by arm** beyond the per-role attribution E-33
  already provides (thin follow-on).
- Per-role **harness** selection (arms override models only).
- Actually running a sweep / reading the economics numbers (runtime
  measurement).
- OQ-E2 (regression-gate half of E-4) — separate item.

## 7. ADR-6 restatement

The invariant is unchanged; its *enforcement points* grow from one to three,
all sharing one implementation:
1. **Boot** — `validate_registry` over the registry (unchanged).
2. **Benchmark boundary** — `validate_run_roles` over each arm's resolved map.
3. **CLI boundary** — `validate_run_roles` over `--role-model` overrides.

A per-run override MUST satisfy ADR-6 for that run; the judge MUST differ in
family from every producer model in the matrix.
