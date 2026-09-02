# Slice Migration Guide

The step-by-step procedure for extracting an SDLC stage out of the monolithic
`src/sdlc/workflows/feature.py` and into its isolated vertical slice under
`src/sdlc/stages/<stage>/`.

Spec A executes this process for the pilot stages (`clarify` and `qa`);
subsequent epics follow this exact procedure for the remaining stages.

## Prerequisites

Before modifying code, read:
1. [`docs/framework.md`](../framework.md) — the `StageContext` protocol, Temporal
   sandbox rules, and the passthrough principle.
2. The nearest `AGENTS.md` in any directory you touch.

## Migration Procedure (Ordered Checklist)

Follow these eleven steps in strict order:

1. **Map stage couplings (the archaeology step):**
   Read the stage's inlined block in `_pipeline` and list every `self.` attribute
   or method it touches. That list represents the coupling that the migration
   must either eliminate or route through `StageContext`.
2. **Create slice directory:**
   Create `src/sdlc/stages/<stage>/` with the seven canonical slice files:
   `__init__.py`, `step.py`, `activities.py`, `models.py`, `prompts.py`, `<stage>.md`,
   and `AGENTS.md`.
3. **Move produced models into `models.py`:**
   Move the Pydantic models and artifacts that this stage **produces** (not those
   it merely consumes — the producer owns its artifacts).
4. **Move activities into `activities.py`:**
   Move the `@activity.defn` functions this stage owns into `activities.py`.
   Export them in `__init__.py` as `ACTIVITIES: list[Callable]`, add the module to
   `STAGE_MODULES` in `src/sdlc/stages/__init__.py`, and delete the corresponding
   imports from `src/sdlc/worker.py`.
5. **Write `step(ctx, ...)`:**
   Implement `step.py` using `StageContext`. Any `self._x` that is not one of the
   eleven `StageContext` services becomes an explicit function parameter or a
   return value.
6. **Replace inline block in `_pipeline`:**
   Replace the inlined code in `FeatureWorkflow._pipeline` with the call to
   `step(ctx, ...)`. **The activity invocation sequence must remain identical** —
   this is what keeps Temporal replay safe for existing histories.
7. **Move and rename tests:**
   Move stage tests to `tests/<stage>/`, keeping full descriptive basenames
   (e.g., `test_clarify_routing.py`, never shortened to generic names like
   `test_routing.py`). Kroker has no `tests/__init__.py`, so pytest requires
   globally unique basenames across all test directories.
8. **Author slice documentation from templates:**
   Author `<stage>.md` from [`docs/templates/stage.md`](../templates/stage.md)
   and `AGENTS.md` from [`docs/templates/stage-AGENTS.md`](../templates/stage-AGENTS.md).
9. **Update authoritative migration table:**
   In the root [`AGENTS.md`](../../AGENTS.md), update the stage's entry in the
   "Where each stage lives" table from `in feature.py` to `migrated` and point to
   `src/sdlc/stages/<stage>/`.
10. **Re-point call sites (No shims):**
    Re-point every call site of every moved symbol across `src/` and `tests/`.
    **No re-export shims.**
11. **Run tiered verification:**
    Run:
    ```bash
    pytest -m "not slow and not temporal"
    pytest -m temporal
    python scripts/check_file_size.py --full
    pre-commit run --all-files
    ```

## Two Closing Traps

1. **Passing the step module itself through the sandbox:**
   Do not pass the step module itself into `workflow.unsafe.imports_passed_through()`.
   The step module executes sandboxed. Only its third-party/IO imports, model
   modules, the agent registry, and child-workflow classes are passed through.
2. **Carrying `_escalation_round`-shaped state into the slice:**
   Never recreate workflow-instance mutable state inside the slice. Concurrency
   and interleaving make instance state unpredictable. Loop counters and retry
   counts belong in local variables or return envelopes.
