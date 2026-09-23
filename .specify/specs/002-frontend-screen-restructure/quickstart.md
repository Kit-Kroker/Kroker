# Quickstart: validating the frontend restructure, DS port and board screen

**Plan**: [plan.md](plan.md) · contracts: [source-layout](contracts/source-layout.md), [board-client](contracts/board-client.md)

## Prerequisites

- Repo root `D:\own\Kroker`, Python venv active (`uv run` or `.venv`), Node installed (the wrapper runs `npm ci`).
- `PLAYWRIGHT_BROWSERS_PATH=D:/own/.pw-browsers` (the wrapper sets it on Windows if unset).
- No stale preview servers on ports 4173/4174 (Playwright reuses them locally).

## 1. Whole-feature gate (after every task group)

```text
python scripts/check_ui.py
```

Expected: every step passes — typecheck (dashboard, ui), builds, vitest-dashboard, ds-bundle, vitest-ui, playwright (showcase + app tiers).

```text
python scripts/check_clauses.py
```

Expected: no `clause with no test:` line and no `test cites unknown clause:` line for any clause this feature adds (`TOKENS-3/4`, `STATUS_PIP-*`, `SHOWCASE-1`, the 13 component prefixes, `CONSOLE-10…`). The script always exits 0 — read the output.

```text
python scripts/check_file_size.py --full
```

Expected: no file over 1000 lines.

## 2. Group A — layout (US1, SC-001–SC-003)

- `interfaces/dashboard/frontend/src/` holds exactly `app/`, `api/`, `shared/`, `features/` (+ `vite-env.d.ts`); `components/`, `views/`, `stores/`, `adapters/`, `composables/`, `styles/`, `constants.ts` are gone.
- `app/boundaries.test.ts` passes in the `vitest-dashboard` step; its self-tests prove each rule flags a planted violation.
- vitest-dashboard pass count ≥ the A0 baseline recorded in the task note.
- `interfaces/AGENTS.md` shows the screen-location table; every folder it names exists (`features/board/` holds only `.gitkeep` until C3).

## 3. Group B — design system (US2, SC-004)

- `cd interfaces/ui` is never needed: the showcase is exercised by the Playwright tier inside `check_ui.py`.
- For each of button, check_row, detail_pane, field, filter_chip, list_row, segmented_control, stat, status_tag, surface, tab_bar, tag, timeline: its directory holds `<Name>.vue`, `<name>.md`, `<name>.profiles.ts`, `<name>.spec.ts`, `<name>.pw.ts`; `showcase/registry.ts` imports its profile set; `src/index.ts` exports it (and `DetailSection`).
- `showcase.pw.ts` (`SHOWCASE-1`) proves slot text renders; slot-using components' `.pw.ts` pass.
- `tokens.pw.ts` passes TOKENS-1…4 (light scope present, exempt from the hex scan).

## 4. Group C — backend slice

```text
pytest -q tests/test_run_state_model.py tests/test_run_summary_build.py tests/test_run_host.py
ruff check .
ruff format --check .
mypy
```

Expected: `project_key` present on `RunState`/`RunSummary` when the run's config has one; `None` otherwise; model field-parity test green.

## 5. Group C — board screen by hand (optional smoke; the app tier automates it)

```text
cd interfaces/dashboard/frontend
set VITE_API=mock   (PowerShell: $env:VITE_API="mock")
npm run dev
```

(Manual smoke only — tasks never invoke npm directly; R4.)

Open `http://localhost:5173/#/runs/<mock run with a board project>?tab=board`:

- Tabs Graph | Board | Gates | Cost; Gates and Cost are disabled; Board is active; the run title and stage strip sit above the tabs.
- Task rows show status, fix attempts and error marks; selecting one shows fields, evidence and a timeline.
- The counter strip says "this run".
- The mock run without a project, the 404 project and the empty project each show their banner or empty state.
- Switch to Graph: the URL loses `?tab`; the graph, gate decisions and pending links behave as before.
- Reload with `?tab=cost` or `?tab=nonsense`: Graph renders and the URL is left alone.
