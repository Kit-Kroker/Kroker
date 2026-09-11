# AGENTS.md — qa

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned. The qa stage does not import other stages.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- The step never calls `ctx.gate`: QA is a clean-context validator and holds no direct gates.
- Agents arrive as keyword arguments (`qa_agent`), never imported from `sdlc.agents.roles` to prevent circular imports during worker boot.
- Subprocess exit code `qa_raw.tests_passed` is deterministic ground truth and must never be overridden by model outputs.

## Temporal notes for this slice

- `ACTIVITIES = [run_test_suite, run_lint, security_scan, scoped_security_scan]`.
- All activities run in worker context with bounded timeouts and safe process tree termination (`kill_process_tree`).
- Rule 3 passthrough set: this slice passes through `core/models.py`, `workflows/models.py`, and upstream artifact models.

## State

- `StageContext` capabilities provide access to `run_role`.
- No state is retained on workflow instances by this slice.

## Activities

- `run_test_suite`: runs test runner inside worktree venv with traceback capture.
- `run_lint`: runs project linter inside worktree with diagnostic capture.
- `scan_paths`: pure per-point scan over an explicit path list (one finding per match, with its line).
- `scoped_security_scan`: tracked files at head and base, then the `change_scope` delta (DS4).
- `security_scan`: transitional whole-directory form; removed when the merge step moves to `scoped_security_scan`.

## Fixture convention (diff-scoped gates DS9)

The merge gate's security floor has no exemption for tests or fixtures. New test code never writes scanner-trigger text literally: assemble it at runtime (`"ev" + "al("`), or keep payloads in extensions the scanner does not read. Do not edit existing literal fixture lines — their normalized text is their baseline identity, and an edited line reads as introduced.

## Tests

    pytest tests/qa/ -q
