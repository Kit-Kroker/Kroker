# Contract — `sdlc maintain` CLI (023a)

Every verb is a stateless shell over Temporal (FR-604, ADR-8). Exit 0 means success. Exit 2 is an argparse usage error. Exit 1 is a refused operation, with a one-line reason on stderr.

| Verb | Args | Behaviour |
|---|---|---|
| `sdlc maintain enable <project>` | `--repo PATH` (required), `--branch NAME` (default `main`), `--advisory-source {none,osv}`, `--threshold F`, `--gate-timeout-hours N`, exactly one of `--ack-unattended-build-probe` / `--no-build-probe` | Validates `MaintenanceConfig`. Refuses when the path is not a git work tree. Starts `maint-<project>` with a fresh `MaintenanceState` and prints `enabled maint-<project>`. "Already enabled" → exit 1 |
| `sdlc maintain nudge <project>` | — | Signals `nudge`. A workflow that is not found → exit 1, `not enabled: <project>` |
| `sdlc maintain incidents <project>` | `--all` (include terminal), `--state` (print the summary) | Queries `incidents` / `maintenance_state` and prints a table: `INC-n  state  key  seen  eff.conf  gate` |
| `sdlc maintain disable <project>` | — | Signals `disable` and prints `disabling maint-<project>` |

Repair decisions use the existing verbs on the run id (`sdlc approve|reject maint-<project> …`), per R11. If T-R11 shows they cannot resolve a GateHost-only run, `sdlc maintain decide <project> <gate> {approve,reject} [--comment]` is added over the same transport.

There are no gate-policy flags. `--gate-policy` / `--on-timeout` are not accepted, and argparse rejects them as unknown (exit 2). The validator refusal in SC-003 covers the programmatic path (`MaintenanceConfig(..., gates=...)` → `ValidationError` naming `gates`).

`sdlc inbox` additionally lists pending `MaintenanceWorkflow` gates (R11).

`sdlc schedules apply [--dry-run]` accepts maintenance-kick assets (R10).
