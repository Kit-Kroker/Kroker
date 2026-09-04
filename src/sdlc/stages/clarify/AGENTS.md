# AGENTS.md — clarify

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned. The clarify stage does not import other stages.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- Agents arrive as keyword arguments (`clarify_agent`, `route_agent`, `probe_agent`), never imported from `sdlc.agents.roles` to prevent circular imports during worker boot.
- The activity invocation sequence must preserve the replay invariant: step finishes at `ctx.record`, returning `reqs`, and the workflow performs `_board_publish` and `_retain`.

## Temporal notes for this slice

- `ACTIVITIES = []`: Clarify currently executes agent proposer roles and uses no stage-owned worker activities.
- Model and prompt modules use safe imports passed through Temporal workflow sandbox boundaries as needed.

## State

- `StageContext` capabilities provide access to `stage`, `recall`, `cached_stage`, `ask_and_wait`, `judge`, `record`, and `emit`.
- No state is retained on workflow instances by this slice.

## Activities

- No activities are owned by this stage. `ACTIVITIES = []`.

## Tests

    pytest tests/clarify/ -q
