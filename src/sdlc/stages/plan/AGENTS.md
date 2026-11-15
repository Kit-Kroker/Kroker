# AGENTS.md — plan

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned: plan accepts architecture spec and requirements, executing independently.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- Handlers live on the workflow class's MRO, never in this slice.
- The slice exports `step`, `prompt_digest`, and `ACTIVITIES = []`.
- Downstream requirements and architecture are consumed without modifying caller state.
- Task-graph checks are imported from `sdlc.validators.pure` (FR-205): the slice's own `validation.py` was deleted — no alias, no re-implementation. `dag_acyclic` presupposes `deps_resolve`; `validate_task_graph` is the composed form.
- `DevTask.covers` is planner-produced metadata: the planner prompt names it only when a `requirements_doc` with stories rides the run, and `plan_check`'s coverage halt reads it. Board rendering omits it (`board/render.py:_OMITTED` — recorded, deliberate).

## Temporal notes for this slice

- `ACTIVITIES = []`.
- Rule 3 passthrough set: `core/models.py`, `workflows/models.py`, `architecture`, `clarify`, `constitution`, `requirements`.
- Memoization key incorporates prompt salt via `prompt_digest(cfg)`; the cache key itself concatenates `constitution_digest` and `requirements_doc.digest` under the omitted-while-`""` rule (PLAN-1.7) — a flag-off run keys byte-identically to a run without those artifacts.
- The graph's `plan_check` node owns the ordered check family (PLAN-1.8, order is contract; FR-301: failures revise the planner before `gate.plan`, halting only on an exhausted loop or a pre-FR-301 pinned graph) and the post-pass board sync (on reordered graphs the sync waits for the gate's publish); this slice schedules no validation of its own.
- Lazy exports in `__init__.py` break circular imports with benchmarks models.
- **Replay: the FR-301 gate-side `plan_valid` conjunct is declared incompatible with in-flight pre-branch runs — no `workflow.patched`.** The conjunct runs on pre-FR-301 pinned graphs too, not only reordered ones, so a run whose recorded history holds a SOFT plan auto-approve short-circuit can now open a human gate on replay (`workflows/gates.py` wait/timer commands where history holds none) — a command mismatch. The mismatch requires both: the run's `(plan, author_model)` bucket is `calibrated` (none exists yet; exposure today is ~zero) AND `cfg.plan` is looser than the `PlanConfig()` defaults (24 files / 12 criteria), so a plan plan_check passed under `cfg.plan` still fails the conjunct's `task_size`. Before deploying a worker built from this branch, `temporal workflow list --query "ExecutionStatus='Running' AND (WorkflowType='GraphWorkflow' OR WorkflowType='TidyUpWorkflow')"` must print nothing; terminate or finish those runs first (or accept the bounded exposure knowingly).

## State

- `StageContext` provides access to `revisable_stage`, `cached_stage`, `run_role`, `judge`, `record`, `retain`, `recall`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/plan/ -q
