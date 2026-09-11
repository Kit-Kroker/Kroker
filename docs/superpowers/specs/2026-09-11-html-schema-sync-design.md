# HTML schema pages — sync to main `76b8d91`

| | |
|---|---|
| Date | 2026-09-11 |
| Status | Approved by the reviewer (r2, after r1 FIXES-NEEDED was folded in); advisor consensus in `.workspace/tmp/advisor-schemas-sync-2.md`. Awaiting the user gate on rulings R1–R3 (§8). |
| Scope | `docs/schemas/*.html` only. Docs-only; no product code. |
| Baseline | `main` @ `76b8d91` |

## 1. Contract and what "sync" means

The six pages mirror the living docs on `main` (`README.md:133-139`). Prose
and statuses follow `ROADMAP.md` + `docs/roadmap/*.md`, `ARCHITECTURE.md`,
`BENCHMARK.md`, and `agents/`. Code paths and line numbers follow the code
wherever a page describes the code in its own voice, because README says the
pages are "checked against actual code". `ARCHITECTURE.md` is itself stale in
places (§6), and a page must not re-import that staleness.

One exception. roadmap.html's item notes quote their source text verbatim
under the page's own extraction rule. When the source text names a dead path,
the note keeps that path. The fix belongs in the source (§6), because an
edited note would stop mirroring it.

Out of scope, as rulings to confirm at the user gate (§8):
- **Register-only landings.** C2 test freeze, C3 `MERGE_REQUIRED_CHECKS`/
  `MISCONFIGURED`, C4 pairing audit, B4 `SDLC_FLEET_PENDING_CAP`, E4
  `plan_drift`, C7 calibration ledger, C8 lens tombstones, F2 `sdlc doctor`,
  and F4 Markdown renders stay out, along with register section H and its
  `Designed` status. None of them has a footprint in `ARCHITECTURE.md`,
  `ROADMAP.md` or `docs/roadmap/`; grep counts are 0 for
  `MERGE_REQUIRED_CHECKS`, `SDLC_FLEET_PENDING_CAP`, `plan_drift`,
  `tombstone` and `doctor`. The gap belongs to the living docs (§6).
- Editing `ARCHITECTURE.md`, `ROADMAP.md`, the register, `src/`, `tests/`.

## 2. The window is larger than briefed

`1ccb9c8` (2026-09-02) only **moved** the pages: 22 +/- link lines, no content.

| Page | Last content commit | Self-stamp |
|---|---|---|
| roadmap.html | `a806ae3` 2026-08-19 | DATA `lastVerified: "2026-08-18"` |
| architecture-schema.html | `fd66efd` 2026-08-18 | footer "Verified 2026-08-18" |
| agents-schema.html | `05715af` 2026-08-18 | "Verified 2026-08-17" |
| research-stage-schema.html | `f6d4437` 2026-08-16 | — |
| benchmark.html | `f6d4437` 2026-08-16 | — |
| benchmark-analysis.html | `f6d4437` 2026-08-16 | `generated_at` 2026-08-15 |

Reproduce with `git log --follow --format='%h %ad %s' --date=short --
docs/schemas/<page>`. The window therefore also contains E-85, E-86, E-88
(crew), E-50, the 2026-09-02 ROADMAP §§9-17 split into `docs/roadmap/`, and
the B0 stage-slice moves (2026-09-04/05).

## 3. Per-page verdict and edit list

### 3.1 roadmap.html — STALE (status + items + notes)

Method: targeted edits to the hand-extracted `ROADMAP` DATA block, keeping
the page's documented rule (`[x]`→done, `[ ] ⚠️`→partial, `[ ]`→notstarted,
`—`→notmeasurable). Sources: `ROADMAP.md` + `docs/roadmap/*.md` (post-split),
and `BENCHMARK.md` for the `OQ-B*`/`OQ-P*` series.

Status flips (page → source):

| Item | Page | Source | Cause |
|---|---|---|---|
| FR-601 | done | partial | 2026-09-11 correction (run-detail/inbox are stubs) |
| FR-917 | notstarted | partial | E-50 landed 2026-09-02 |
| E-50 | notstarted | done | landed 2026-09-02 (`docs/roadmap/tier-2-edcr.md:148`) |
| US-7 | notstarted | partial | E-86 chat agent shipped; MCP pending |
| FR-107 | partial | notstarted | older error: already wrong at the 08-18 extraction |
| FR-305 | partial | notstarted | older error |
| FR-915 | partial | notstarted | older error |

New items (append in source order): FR-1400 … FR-1406 (all done,
`ROADMAP.md` §2 "Component library (FR-1400)"); E-85 (done,
`docs/roadmap/tier-0-triage.md`); E-86 (done, `docs/roadmap/filesystem-first.md:70`,
an id-keyed checkbox); OQ-14 (`docs/roadmap/pipeline-as-data.md:151`).
**E-88 and E-89 stay out of DATA.** Neither is an id-keyed checkbox:
`docs/roadmap/crew.md` keys its checkboxes "Step 1…3", and E-89 appears only
inline. E-88 reaches the page through the stage-8 note, and E-89 through the
FR-1400 items.

**US-6 and US-8 stay in DATA.** `9bfe73e` (2026-08-20, `feat(operator)`)
rewrote US-7 and removed the US-6 and US-8 lines from ROADMAP §5, leaving a
blank line in their place. A feature commit deleting two user stories looks
accidental, not like a ruling, so the page keeps them at their last source
wording (`git show a806ae3:ROADMAP.md`). The loss goes to the inbox task (§6)
and is confirmed at the user gate (§8, R3).

Note text refreshed to current source wording. The list is **non-exhaustive**:
it names what the `a806ae3`→main diff shows, and the rule is that any item
exec touches carries its current source wording. The items are E-11
(re-exports `sdlc/operator/tools.py`), E-50, E-72 (`core/models.py` anchors),
E-73, E-76, FR-601, FR-704 (the 2026-09-11 correction note), FR-917, NFR-4
(rewrite) and US-7.

Non-item blocks:
- `stages[8]` (code) note gains the crew clause (E-88, opt-in per role config).
- Recommended-next-increments #6: E-22/E-23 struck, "(landed in E-32)".
- Cross-ordering §14 paragraph: replace with `docs/roadmap/ordering.md` item 7
  as of `fa4663d` ("record only" ruling, prerequisites (a)–(c)).
- `meta.lastVerified` → `2026-09-11`; footer "Regenerated …" date and recap
  → 2026-09-11 with a one-line summary of the above.

Unchanged and verified: ADRs (13/21 done), §0 phases, §4 SC, §7 STRUCT.

### 3.2 architecture-schema.html — STALE (crew, DAPER status, component-layer paths)

Mirror the `ARCHITECTURE.md` deltas since `05715af`:
- Component layers: add a `CrewTaskWorkflow (E-88)` row (round loop, four
  brakes, per-round checkpoints, its own `tool_approval`/question gates).
- Pipeline DAG: stage 8 may run as a crew (`HarnessKind.CREW` is a
  composition mode, not a CLI; the child returns the same `HarnessRunResult`).
- Agent architecture: the crew as assets (`crew/roles/*.yaml`,
  `crew/layouts/code.yaml`), its three rules (one writer = the lead; every
  non-lead differs in model family from the lead, ADR-6; a role's harness
  must be installed), the `write_root` fence, and round files as untrusted input.
- Maintenance (DAPER): "designed, not built (P4)" banner.

Component-layers module paths (page lines ~655-750). **Older errors, all
of them:** none of these paths has ever existed in git history (`git log
--all -- src/sdlc/<path>` is empty for each). They are design-era names.
Retarget each row to its real home. Values are at `76b8d91`; exec
re-verifies each with `git ls-files`.

| Row | Page cites | Real home |
|---|---|---|
| Workflows | `workflows/factory.py` | `src/sdlc/workflows/feature.py` (the row's own note already says the class is `FeatureWorkflow`) |
| Per-task loop | `workflows/task.py` | `src/sdlc/workflows/task_host.py` (`TaskHost`) |
| Gate helper | `workflows/gates.py` | unchanged (exists) |
| Maintenance | `workflows/maintenance.py` | no module; the path becomes "— (not built, P4)" |
| Retro / reflect | `workflows/retro.py` | `src/sdlc/stages/retro/` + `src/sdlc/workflows/reflect.py` |
| Harness adapters | `harness/adapters.py` (line ~690) | `src/sdlc/harness/` (`base.py`, `claude_code.py`, `opencode.py`, `cursor.py`, `registry.py`); the only one of these that is drift, flattened `db1af1c` 2026-09-04 |
| Repo activities | `activities/repo.py` | `src/sdlc/vcs/` (`git.py`, `worktree.py`, `integration.py`) |
| QA activities | `activities/qa.py` | `src/sdlc/stages/qa/activities.py` |
| Memory activities | `activities/memory.py` | `src/sdlc/memory/activities.py` |
| Cartography | `activities/cartography.py` | `src/sdlc/stages/context/activities.py` + `src/sdlc/context/` |
| Notify | `activities/notify.py` | `src/sdlc/notify/activities.py` |
| Deploy | `activities/deploy.py` | `src/sdlc/deploy/activities.py` + `src/sdlc/stages/deploy/activities.py` |
| Agent registry | `agents/loader.py` | `src/sdlc/agents/loader.py` |
| Deterministic agents | `agents/deterministic.py` | `src/sdlc/gate.py` (quality gate) + `src/sdlc/observability/export.py` (summary/export) |

The Deterministic agents note "constitution + summary/export absent" becomes
"constitution absent", status still partial. That note was also an older
error: export landed with E-32, per FR-704's 2026-09-11 correction.
`src/sdlc/agents/` defines no deterministic role.

Footer "Verified 2026-08-18" → 2026-09-11. Unchanged and verified: the ADR
tally "13 / 21 satisfied", the SC list, the increments.

### 3.3 agents-schema.html — STALE (paths + crew roles)

- Header "contract source-of-truth: `src/sdlc/models.py`" → the per-owner
  model modules (`src/sdlc/core/models.py` for config/envelopes, each stage's
  `models.py` for its artifacts); "Verified 2026-08-17" → 2026-09-11.
- Harness adapter section (line ~688): `src/sdlc/harness/adapters.py` →
  `src/sdlc/harness/` (the five-module split). Line pills: `adapters.py:48`
  → `base.py:41` (`CONTEXT_WINDOWS`), `adapters.py:79` → `base.py:72`
  (`ENV_ALLOWLIST`), `adapters.py:172` → `base.py:196` (the per-adapter
  `containment` capability field). Values are at `76b8d91`; exec
  re-resolves each by `grep -n` on the symbol.
- File map: the `adapters.py` row → the five-module split, with `HARNESSES`
  and `check_harness_versions` in `registry.py`; the `CONTRACT src/sdlc/models.py`
  layer label (line ~1697) likewise; drop the "ARCHITECTURE §14 targets
  `tests/fakes/fake_harness.py`" note (line ~1744). ARCHITECTURE no longer
  says that; `tests/fakes/` holds the stubs.
- New short block "Crew roles (E-88)": `crew/roles/{coder,critic}.yaml`, not
  in `agents/registry.yaml`; one-writer rule; ADR-6 family rule applied to
  non-lead roles. No per-role numbered section.
- Role count 17 stays (matches the 17 `agents/` role dirs).

### 3.4 research-stage-schema.html — STALE (paths)

Behaviour unchanged since 08-16 (`git log f6d4437..76b8d91 --
src/sdlc/stages/research` shows only moves/lint/type commits). The edits
are mechanical retargets:
- `src/sdlc/research/<f>.py` → `src/sdlc/stages/research/<f>.py` (budget_store,
  deps, merge, prompts, protocol, retain, stage, toolset, verify).
- `tests/test_research_*.py` → `tests/research/test_research_*.py`;
  `tests/test_architect_research_tool.py` → `tests/architecture/`.
- `src/sdlc/models.py` (lines ~355, ~1773, and `:731` at ~474) →
  `src/sdlc/stages/research/models.py`. `:731` was the grounded-finding
  class, now `GroundedFinding` at `models.py:24`. `feature.py:1726` → the
  `research_enabled` branch (`feature.py:533`). Exec re-resolves both lines.
- `agents/loader.py` (lines ~1440, ~1460) → `src/sdlc/agents/loader.py`.
- Related-docs mono labels `docs/<page>.html` → `docs/schemas/<page>.html`.
- "16-role registry" → "17-role registry" (older error).

### 3.5 benchmark.html — CURRENT (no edit)

Source `BENCHMARK.md`: `git log f6d4437..76b8d91 -- BENCHMARK.md` is empty.
Its last change, `0495d60`, is dated 2026-08-12 and precedes the page's
08-16 sync. The page's `../../BENCHMARK.md` links resolve. All six code
cites resolve under `src/sdlc/` (`benchmarks/workflow.py` :440/:549,
`benchmarks/waste_matrix.py` :826, `benchmarks/agreement_matrix.py` :858,
`benchmarks/experiments.py` :1060, `src/sdlc/benchmarks/vetoes.py` :1223).

### 3.6 benchmark-analysis.html — UNTOUCHED here (see ruling R1)

`runs/benchmarks/` is absent: it is gitignored and there are no local runs.
`scripts/aggregate_benchmarks.py` raises `FileNotFoundError` before writing.
The page is a generated data snapshot (21 runs, 2026-08-15), not a
living-doc mirror. Exec must not run the aggregator.

## 4. File-size exemption

Verified: `scripts/check_file_size.py` `EXEMPT_PATTERNS` includes
`"docs/schemas/*"` (line 56), and AGENTS.md exempts generated artifacts.
The pages run 310–1777 lines and are exempt.

## 5. Acceptance checks for exec (all mechanical)

Throwaway scripts live under `.workspace/tmp/` and are not committed.

1. **Dead-path sweep.** For each edited page, extract every
   `[A-Za-z0-9_][A-Za-z0-9_./-]*\.py` token. Each must resolve to a
   `git ls-files` entry, either equal to it or ending in `/<token>`. The
   unresolved set must equal exactly this allowlist:
   - research: `web_search.py`, `fetch_page.py`, `tools/web_search.py`,
     `tools/fetch_page.py` (the text says they were removed);
     `_wiring.py` (a brace pattern, `test_research_{fanout,stage}_wiring.py`,
     both of which exist).
   - agents: `prompt/agent.py` (validation-rule prose, not a path).
   - roadmap: only tokens that also appear verbatim in the item's source
     text (§1 exception). At `76b8d91` these are `harness/adapters.py`,
     `tests/test_toolchain_go.py`, `validators.py`, `fake_harness.py`, and
     the designed-only `sdlc/graph/model.py` and `validate.py`.
   - architecture: none.
2. **Removed strings.** `src/sdlc/models.py`, `src/sdlc/research/`,
   `tests/fakes/fake_harness.py`, `workflows/factory.py`, `activities/` and
   `16-role` return no matches in the three non-roadmap edited pages.
   `harness/adapters.py` returns no matches in architecture-schema.html or
   agents-schema.html. roadmap.html is covered by check 1's source-subset rule.
3. **Roadmap parity, both directions.** Re-extract id→status from
   `ROADMAP.md` + `docs/roadmap/*.md` by the page's rule.
   - (a) Zero status mismatches against DATA.
   - (b) Every source checkbox id is in DATA.
   - (c) Every DATA id appears in `ROADMAP.md` + `docs/roadmap/*.md` +
     `BENCHMARK.md`, except `STRUCT-1…5`, which the page synthesises for
     §7's unnumbered list, and `US-6`/`US-8`, kept per §3.1 and R3.
4. **FR-601 wording.** Status `partial`, and the note contains "run-detail",
   "inbox" and "not built".
5. **Counts.** The agents page's "17 roles" equals the `agents/` role-dir
   count (`ls -d agents/*/ | wc -l`).
6. **Untouched, and still correctly so.**
   `git diff --quiet 76b8d91 -- docs/schemas/benchmark.html
   docs/schemas/benchmark-analysis.html`, and
   `git log --oneline f6d4437..76b8d91 -- BENCHMARK.md` prints nothing.
7. **DATA parses.** A `node` script (v25 is available) slices the
   `const ROADMAP = {…};` literal out of roadmap.html and evaluates it
   standalone without error. Per-status item totals must equal the
   pre-edit totals adjusted by exactly the §3.1 flips and additions.
8. `python scripts/check_file_size.py` and the pre-commit hooks pass.

## 6. Inbox task (filed by exec in `.workspace/tasks/`, not fixed here)

One task, "living docs lag main", recording:
- `ARCHITECTURE.md` §14 tree still shows `src/sdlc/models.py`,
  `activities.py`, `harness/adapters.py` and a flat `research/`, with no
  `stages/` and no `core/models.py`.
- ROADMAP/docs/roadmap still cite dead paths: `ROADMAP.md:101`
  (`tests/test_toolchain_go.py`) and `ROADMAP.md:256`,
  `docs/roadmap/filesystem-first.md:106,276` (`harness/adapters.py`).
  Also check the old `models.py:NNN` cites at `ROADMAP.md:298-302` and
  `filesystem-first.md:79`.
- `9bfe73e` dropped US-6 and US-8 from ROADMAP §5, apparently by accident.
- None of ARCHITECTURE.md, ROADMAP.md or docs/roadmap/ describes the register
  landings C2, C3, C4, B4, E4, C7, C8, F2 or F4.

It proposes a living-docs sync, after which the pages would follow.

## 7. Commit split

One commit per edited page (4), in this order: roadmap, architecture,
agents, research-stage. Subject form: `docs(schemas): sync <page> to main`.
Each commit carries only its page. The inbox task is untracked scratch and
is not committed. Messages are subject + body only, with no attribution
trailers, committed via `git commit -F <msgfile>`, one path per `git add`.

## 8. Rulings for the user gate

- **R1. benchmark-analysis.html.** Keep the 2026-08-15 snapshot frozen
  (recommended), or regenerate it from a machine that holds
  `runs/benchmarks/` as a separate task.
- **R2. Register-only landings.** Keep them out of the pages until the
  living docs carry them (recommended, advisor agrees). The alternative is
  to add them to the pages now, ahead of the living docs.
- **R3. US-6 / US-8.** Keep them in roadmap.html at their last source
  wording, and have the inbox task restore them in ROADMAP (recommended).
  The alternative is to treat the 2026-08-20 deletion as intended and drop
  them from the page.

## 9. Rulings and pivot (user gate, 2026-09-11)

- **R1: superseded by a pivot.** The user declined both R1 options and
  ended the hand-sync of `docs/schemas/*.html` altogether. It is replaced by
  a generated documentation site that re-reads its sources and refreshes
  itself. No plan hand-edits the six pages. The site is designed in
  `docs/superpowers/specs/2026-09-11-docs-site-design.md`.
- **R2: ruled as recommended, and carried into the site design.** The site
  mirrors the living docs only. Register-only landings (C2, C3, C4, B4, E4,
  C7, C8, F2, F4) appear on it when the living docs grow them, never from the
  register directly.
- **R3: ruled keep + restore, and carried into the site design.** US-6 and
  US-8 stay visible. Their restoration in `ROADMAP.md` is folded into the site
  phase's plan, because the generator cannot render what ROADMAP lacks. It
  rides the normal gates.

What survives of this spec: §§2–3 and §6 are input to the site design. They
catalogue what diverged in the hand-maintained pages and why: the move that
was mistaken for a sync, the older errors, the stale design-era paths, and
the living-doc lag. §§5 and 7 no longer apply as written.
