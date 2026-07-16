# Schedules as files + nightly reflect (E-12, E-13)

**Date:** 2026-07-16
**Roadmap:** §9.3 (`E-12`, `E-13`), §8 item 3
**Requirements:** FR-404 (partial — see Scope)
**Design input:** [`vercel/eve`](https://github.com/vercel/eve) — "the filesystem is the authoring interface"

## Problem

`reflect()` exists as a Temporal activity (`src/sdlc/memory/activities.py:94`) and is
registered on the worker (`src/sdlc/worker.py:73`), but nothing ever calls it. There is no
Temporal `Schedule` anywhere in the codebase. FR-404 ("a scheduled reflect job SHALL
consolidate learnings nightly") is therefore unmet, and SC-4 / SC-6 have no calibration
signal accruing — nothing else in the system produces one.

This is the smallest item in §9 and the only one that starts that signal.

## Findings that changed the task as written

Three facts from the code contradict the roadmap's phrasing of E-12/E-13. The roadmap is
amended as part of this work (see Roadmap amendments).

1. **Temporal Schedules start workflows, not activities.** E-13's "invoking the existing
   `reflect()` activity" is not directly buildable; a Schedule's action is `start-workflow`.
   A thin `ReflectWorkflow` wrapper is required.

2. **A schedule has no run to inherit config from.** `FeatureWorkflow` reads bank names,
   `backend`, and `base_url` from the per-run `PipelineConfig` (`cfg.memory.project_bank`).
   A nightly schedule is not attached to a run, and no registry of projects exists to
   discover banks from. The yaml asset therefore carries its own memory config and an
   explicit bank list.

3. **`org_bank` has no writers.** `MemoryConfig` defines `org_bank: str = "org"`
   (`src/sdlc/models.py:376`), but every `_retain` call site in `feature.py` passes
   `cfg.memory.project_bank`. `reflect(org)` would consolidate an empty bank permanently.
   The org half of FR-404 is not blocked on scheduling; it is blocked on nothing writing to
   that bank.

## Scope

**In scope:** the schedule mechanism (`schedules/*.yaml` → Temporal Schedules via an
explicit CLI apply), a `ReflectWorkflow` wrapper, and one schedule asset —
`schedules/nightly-reflect.yaml` — reflecting **project banks only**.

**Out of scope:** the retro *stage* (§1 item 13, `RunSummary`); org retains; E-14's DAPER
maintenance timer.

**FR-404 remains `[ ]` ⚠️ partial after this ships.** Project reflect runs nightly; org
reflect has no writers. It does not get an `[x]`. Shipping the org schedule as a permanent
no-op behind a checked box was considered and rejected — that is exactly the drift §§1–7
exist to catch.

**Honest value bound:** this starts the SC-4/SC-6 signal accruing *only if runs execute
with `memory.enabled=true`* — it defaults to `False` (`models.py:373`). Nightly reflect
consolidates what retains have written; with no real runs against a Hindsight backend it
will faithfully consolidate an empty project bank. The mechanism is a prerequisite, not a
sufficient condition.

## Architecture

```
schedules/*.yaml → load_schedules() → sdlc schedules apply → Temporal Schedule
                                                                    │ (3am)
                                                                    ▼
                                                            ReflectWorkflow
                                                                    │ per bank
                                                                    ▼
                                                          reflect activity → backend
```

### Decision: explicit CLI apply, not worker boot

E-12 says "registered at worker boot", the faithful reading of eve's thesis (the directory
*is* the registry). Rejected: schedules are server-side mutable state, not local config.
Boot-time reconcile means N workers race the same reconcile, and a worker restart silently
rewrites production schedules — a deploy would change scheduling behaviour with no diff
shown to anyone.

Files remain the source of truth; mutating live schedules becomes a deliberate act with a
visible diff. **Trade-off accepted:** drift is possible if someone forgets to run apply.
A boot-time *validate* (fail-closed on yaml/server mismatch, mirroring `validate_registry()`)
was considered as a mitigation and deferred — it can be added later at the same seam without
reworking anything here.

### Components

| Component | Job |
|---|---|
| `schedules/<id>.yaml` | The asset. Filename is the schedule id. |
| `src/sdlc/schedules/loader.py` | `load_schedules(dir) -> list[ScheduleAsset]`, `validate_schedules()`. Fail-closed. |
| `ScheduleAsset` (in `models.py`) | Pydantic model; validates cron + bank list at load time. |
| `src/sdlc/workflows/reflect.py` | `ReflectWorkflow` — loops banks, executes `reflect` per bank. No other logic. |
| `src/sdlc/schedules/apply.py` | Reconcile: create / update / report drift / `--prune`. |
| `src/sdlc/cli.py` | `schedules apply [--dry-run]`, `schedules list`. |

`loader.py` deliberately mirrors `agents/loader.py`'s shape (same fail-closed
`RegistryError` idiom). E-1 will want this same pattern for `agents/<role>/`; whichever
lands first sets the precedent.

### Asset format

```yaml
# schedules/nightly-reflect.yaml
spec:
  cron: "0 3 * * *"
  timezone: UTC
action:
  workflow: ReflectWorkflow
  banks: ["project:default"]
  backend: hindsight
  base_url: "http://localhost:8088"
```

### Decision: deletion is opt-in

A schedule live on the server with no matching yaml is **reported as drift, not deleted**.
`--prune` deletes. Delete-by-default turns "checked out an old branch and ran apply" into an
outage.

### Decision: per-bank activity execution

`ReflectWorkflow` executes the `reflect` activity once per bank rather than once for all
banks. One bank's backend failure then retries independently without re-reflecting the
others, using Temporal's own retry policy. Costs nothing — the loop exists either way.

### CLI integration

`sdlc schedules apply` fits the existing `argparse` sub-subcommand pattern already
established by `benchmark` (`cli.py:58-64`). No new CLI machinery.

## Error handling

| Failure | Handling |
|---|---|
| Bad yaml (typo'd cron, unknown workflow, empty banks) | Fails at `load_schedules()` during apply, before touching Temporal. Fail-closed. |
| Temporal unreachable during apply | CLI errors, exits nonzero. Apply is per-schedule; a mid-list failure leaves earlier schedules applied. `--dry-run` and re-running make this recoverable. |
| Backend unreachable at 3am | The `reflect` activity raises (it already does — unlike `recall_snapshot`, which degrades to an empty snapshot by design). Temporal retries, then the workflow fails visibly. |

The last is deliberate and unchanged: a failed nightly reflect must be visible as a failed
workflow, not a silent no-op. That is precisely eve's documented failure mode ("no 404, no
failed-delivery banner — silence") that §9.6 exists to avoid.

## Testing

Follows the existing `tests/fakes/` pattern from the P1 e2e work.

- **`load_schedules()`** — valid asset; bad cron; unknown workflow name; missing/empty banks; empty directory.
- **Reconcile** (fake Temporal client) — create when absent; update when changed; no-op when identical; drift reported not deleted; `--prune` deletes.
- **`ReflectWorkflow`** (fake `reflect` activity) — N banks produce N executions; one bank failing does not skip the rest.
- **Regression guard** — assert `reflect` is registered on the worker *and* reachable from a schedule. The original FR-404 bug was a registered activity that was never called; this is the test that would have caught it.

## Roadmap amendments

Part of this work, not a follow-up:

- **E-12** — "at worker boot" → "via `sdlc schedules apply`".
- **E-13** — drop "project + org scope"; note the `ReflectWorkflow` wrapper.
- **New item** — nothing retains to `org_bank`; cross-project consolidation has no writers.
  This is the real remaining FR-404 blocker and is currently invisible in the tracker.
- **FR-404** — stays `[ ]` ⚠️ partial, annotated with which half is live.
