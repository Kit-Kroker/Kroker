# Contract — `sdlc maintain` CLI, 023b additions

This extends `.specify/specs/023-daper-maintenance-loop/contracts/cli.md`.

## `sdlc maintain enable` (new flags)

| Flag | Meaning | Refusals (exit 2, a message naming what is missing) |
|---|---|---|
| `--execute` | Turn on Execute/Report for this project | Without `--ack-unattended-build-probe`. With `--no-build-probe`. No `gh` on PATH. No `origin` remote. `default_branch` does not resolve |
| `--max-starts-per-cycle N` | 1–3, default 1 | Out of range |
| `--max-starts-per-window N` | 1–10 per rolling 7 days, default 3 | Out of range |
| `--max-reopens N` | 0–2, default 2 | Out of range |
| `--child-timeout-hours N` | 1–168, default 24 | Out of range |

The cap flags without `--execute` are refused ("only meaningful with --execute").

The help text states that disable followed by re-enable resets the 7-day start window.

There is still no `--gate-policy` or `--on-timeout` flag.

## `sdlc maintain incidents` (output additions)

- 2026-11-19 refresh — no single column list existed (the 023 base contract's list was never rolled forward, a staleness pre-existing since 023b, and FR-502 adds a column now). The full list today is `INC-n`, `state`, `key`, `seen`, `attempt`, `reopens`, `eff.conf`, `gate`, `class`, `child`: 023b added `attempt`, `reopens` and `child`; FR-502 (2026-11-19) added `class` — one `<verb>[<CLASS>]` tag per classed action, comma-space-joined, `-` when the plan has none.
- New states render verbatim: `approved`, `queued`, `executing`, `verifying`, `verified`, `reopened`, `closed`.
- For an incident in `verified`, the child id is shown so the operator can find its merge gate in `sdlc inbox`.

## Unchanged

`nudge`, `disable`, and the inbox decision verbs. A repair child's merge gate is a normal `GraphWorkflow` gate in the inbox, decided by `sdlc approve|reject <child-id>`.
