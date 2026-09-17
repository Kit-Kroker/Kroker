# Herdr v3: spec-kit crew setup — design

**Date:** 2026-09-17
**Status:** approved (design), pre-implementation
**Scope:** personal dev tooling under `.workspace/` plus repo-level spec-kit scaffold. Does not touch `src/sdlc/`.

## 1. Context and decision record

The herdr crew evolved through two generations of tab-builder scripts in
`.workspace/bin/`:

- **v1** (`herdr-plan`, `herdr-exec`): three seats — planner | advisor /
  reviewer. Process spine: superpowers skills (brainstorming → spec →
  plan → execution).
- **v2** (`herdr-plan-v2`, `herdr-exec-v2`): plan tab grew to
  planner | advisor / skeptic / reviewer; exec tab to
  executor | qa-happy / qa-chaos / reviewer / scribe. Standing protocol
  (`.workspace/orchestration-protocol.md`) and human manual
  (`.workspace/orchestration-guide.md`) codified gates, seat contracts,
  verification, and integration.

**v3 replaces the superpowers process spine with GitHub
[spec-kit](https://github.com/github/spec-kit)** (SDD toolkit: `specify`
CLI, `/speckit-*` agent skills, `.specify/` artifact tree, built-in
checklists). Decisions taken at brainstorming:

| Question | Decision |
|---|---|
| Where v3 lives | `.workspace/` of Kroker (same as v1/v2), not a standalone factory |
| Role of spec-kit | **Full SDD**: real `/speckit-*` commands, real `specify init` scaffold, artifacts in `.specify/`, gates use spec-kit checklists |
| Seat topology | Keep v2 seats, adapted to spec-kit phases |
| Process scope | SDD **plus** `bug` and `assess` extensions (all three spec-kit entry points) |
| Agent→seat mapping | Same as v2 (incl. glm-shim qa seats) |
| Constitution | Generated once through a crew run, user gate on the result |
| Script structure | **Approach C**: shared layout lib + briefs as editable `.md` + thin per-mode entry scripts |

## 2. Scaffold (one-time repo preparation)

1. `uv tool install specify-cli` (Python 3.11+ present).
2. `specify init . --integration claude --integration opencode
   --integration gemini` in the Kroker root. Exact multi-integration
   syntax verified against `specify init --help` at implementation time.
   If `agy` cannot consume gemini-integration commands this is not a
   blocker: skeptic/advisor seats work from briefs alone and never need
   slash commands.
3. `specify extension add bug` and `specify extension add assess`.
4. `.specify/` is committed to the repo (specs, templates, checklists,
   memory). Verify `.gitignore` does not exclude it.
5. `/speckit-*` command files land in `.claude/commands/` and
   `.opencode/`; claude and opencode seats get native skills.

## 3. Modes, seats, flows

| Mode | Topology (kind) | Flow |
|---|---|---|
| **constitution** (one-time) | planner (claude) \| advisor (claude) / skeptic (agy) / reviewer (opencode) — plan-v2 layout | planner runs `/speckit-constitution` seeded from repo rules (AGENTS.md, orchestration protocol, 1000-line ceiling, no-attribution, cross-stage bans, worktree norm) → **user gate** on the constitution |
| **plan** | v2 plan layout: planner \| advisor / skeptic / reviewer | planner: `/speckit-specify` → **GATE 1** (spec.md) → `/speckit-plan` → reviewer validates via `.specify/templates/checklists/` plan checklist → `/speckit-tasks` → reviewer via tasks checklist; advisor/skeptic consultations as in v2 |
| **exec** | v2 exec layout: executor \| qa-happy / qa-chaos (glm-shim) / reviewer (agy) / scribe (claude) | executor: `/speckit-implement` against tasks.md; qa seats write RED tests per task before each GREEN step; reviewer gates every diff (per-task, blocking); final `/speckit-converge`, loop until `Converged`, **stop-guard: max 3 iterations** then stop and report; scribe updates living docs after convergence |
| **bug** | bug-lead (opencode) \| qa-happy / qa-chaos (glm-shim) / reviewer (agy) | `/speckit-bug-assess` → **gate: assessed-cause verdict** → qa write RED regression tests → `/speckit-bug-fix` → `/speckit-bug-test`; missing verification is not success; artifacts in `.specify/bugs/<slug>/` |
| **assess** | assessor (claude) \| advisor (claude) / skeptic (agy) — no repo writes | `/speckit-assess-intake → research → define → shape → decide`; artifacts in `.specify/assessments/<slug>/`; outcome go / needs-clarification / kill → **user gate** |

spec-kit specifics folded into the seats:

- The plan-tab **reviewer** judges by spec-kit checklists
  (`.specify/templates/checklists/`) — replacing
  superpowers:writing-plans criteria.
- New-work artifacts move from `docs/superpowers/specs|plans/` to
  `.specify/specs/<slug>/` (spec.md, plan.md, tasks.md). Existing
  superpowers directories remain as history; no migration.

## 4. File layout (approach C)

```
.workspace/
  crew/v3/
    modes/
      constitution.md   # per-mode brief files
      plan.md
      exec.md
      bug.md
      assess.md
    lib/
      _crew.sh          # shared: tab create, splits, agent start,
                        # glm-shim PATH seeding, brief parsing
  bin/
    herdr-v3-constitution   # thin entries (~30 lines): crew_run <mode> "<brief>"
    herdr-v3-plan
    herdr-v3-exec
    herdr-v3-bug
    herdr-v3-assess
    herdr-v3-*-popup       # keybinding wrappers, modeled on v2 popups
```

**Brief file format:** a header declaring the layout (seat order,
split directions/ratios, agent kinds, shim flags) followed by
`## seat: <name>` sections; a section body becomes that seat's opening
brief. Editing briefs never touches bash.

- `SEAT_PREFIX` mechanism kept (parallel tabs of the same mode).
- glm-shim: qa seats only (exec, bug), same PATH-seeding mechanics
  (`MSYS_NO_PATHCONV=1 herdr pane run`), shim dir never enters global
  PATH.
- Keybindings in herdr `config.toml`: `prefix+alt+p` / `prefix+alt+e`
  are repointed at the v3 popups; v2 scripts stay invocable manually.
  Final key choice confirmed at implementation.

## 5. Protocol and guide updates

- `orchestration-protocol.md` — phase gates rewritten to SDD:
  constitution (once) → specify → GATE 1 (spec) → plan + tasks →
  GATE 2 → implement (TDD; per-task reviewer gate, enforced not
  self-policed) → converge (≤3 loops) → orchestrator verification
  (`herdr-verify` unchanged) → ff `main` → push. Two new triage exits:
  bugs route to `herdr-v3-bug`, register ideas to `herdr-v3-assess`.
  Task inbox, sizing/batching, driving-and-waiting lessons carry over
  unchanged.
- `orchestration-guide.md` — manual updated: seat table, three entry
  points (feature / bug / idea), file map pointing at `.specify/` for
  new work.

## 6. Error handling

- Missing `specify` on PATH or missing `.specify/` → fail fast with the
  install/init command to run.
- Modes validation: entry script fails with a clear message when a
  declared `## seat:` section is absent from the brief file.
- Converge not converged within 3 loops → stop, diagnose, orchestrator
  ruling (mirrors plan stop-guards).
- v2 resilience rules carried over verbatim: re-verify agent identity
  after start/restart, `ctrl+c` (not `esc`) for stuck opencode,
  "disregard stale draft" tail on every crew prompt, quota degradation
  posture.

## 7. Verification

- `bash -n` on all scripts; shellcheck where available.
- `--layout-only` smoke flag on every entry: builds the tab, starts
  agents, prints the pane/seat map, sends no briefs.
- Scaffold acceptance: `specify --version`; `speckit-*.md` present in
  `.claude/commands/` and `.opencode/`; `.specify/` tracked by git.
- Final acceptance: one live constitution run through
  `herdr-v3-constitution` (it is also the first real use).

## 8. Out of scope

- Standalone/factory packaging (orca_factory-style) of the crew.
- Migrating historical superpowers specs/plans into `.specify/`.
- Any change to `src/sdlc/` or the product pipeline.
- Remote machines / `herdr machine` integration.
