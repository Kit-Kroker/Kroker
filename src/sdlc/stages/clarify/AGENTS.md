# AGENTS.md — clarify

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned. The legal imports are types and renders, not
  calls: `Constitution`/`render_constitution` and `Requirements`/
  `render_requirements` arrive via step.py's `imports_passed_through` block
  (root AGENTS.md: importing a type another stage produces is not a call).
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- Agents arrive as keyword arguments (`clarify_agent`, `route_agent`, `probe_agent`), never imported from `sdlc.agents.roles` to prevent circular imports during worker boot.
- The activity invocation sequence must preserve the replay invariant: step finishes at `ctx.record`, returning `reqs`, and the workflow performs `_board_publish` and `_retain`.
- Scheduling the validators' `paths_exist` activity (023/FR-205) is gated on `workflow.patched("023-clarify-evidence-paths")` AND brownfield AND `repo_path`; the patch id is a wire name recorded in histories — never renamed. The sorted token list pins the command's input, so a replay re-issues the identical call.

## Temporal notes for this slice

- `ACTIVITIES = []`: Clarify owns no worker activities (the 023 evidence check schedules `sdlc.validators.activities.paths_exist`, owned by the validators package).
- Model and prompt modules use safe imports passed through Temporal workflow sandbox boundaries as needed.

## State

- `StageContext` capabilities provide access to `stage`, `recall`, `cached_stage`, `ask_and_wait`, `judge`, `record`, and `emit`.
- No state is retained on workflow instances by this slice.

## Activities

- No activities are owned by this stage. `ACTIVITIES = []`.

## Tests

    pytest tests/clarify/ -q
