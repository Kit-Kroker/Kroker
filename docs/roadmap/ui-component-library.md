# The UI component library and the Claude Design loop — `E-89`

**Landed 2026-09-06.** Spec:
`docs/superpowers/specs/2026-09-05-c-ui-component-library-design.md`. Plan:
`docs/superpowers/plans/2026-09-05-c-ui-component-library.md`. Contracts:
`interfaces/ui/` (each component's `<name>.md`), the showcase under
`interfaces/ui/showcase/`, the gate at `scripts/check_ui.py`, the adapters at
`interfaces/dashboard/frontend/src/adapters/`. Extends FR-601 (E-10);
introduces the FR-1400 block.

**Problem it closed.** `records/README.md` had specified since July that
whatever is *extracted* from a record — tokens, components, clauses — lives
with the UI code; nothing was ever extracted. The console was a one-way
hand-port of the `records/2026-07-12-factory-console/` canvas: every colour
and font was a literal in a `<style scoped>` block, the frontend was visible
to no gate (a `.vue` that failed to compile merged green), no component
stated what it promises, and no test in the repository would notice if every
component rendered white on white.

**What landed.**

- [x] **The seam.** A source-only npm workspace: `@kroker/ui` at
  `interfaces/ui/` holds presentation components that import no domain type;
  the dashboard consumes it through an alias that resolves in dev, build and
  `vite preview`, and maps `Run`/`InboxItem` onto display primitives in
  `src/adapters/`. A profile that cannot be written as a literal has a domain
  leak in it — that is the ownership test, and a grep test enforces it.
- [x] **The gate.** One Python wrapper, `python scripts/check_ui.py`, is the
  only Node entry point, invoked identically by `.github/workflows/ci.yml`
  and `scripts/verify.py` so the run:/gate parity test holds by construction.
  It owns install, both typechecks, both Vitest workspaces, both Playwright
  tiers, and the Windows detail that `npm` is `npm.cmd`. Node absent means a
  loud skip and exit 0; CI is where the UI is truly gated.
- [x] **The component as the unit of UI work.** Seven components
  (StageDots, StatusPip, FleetRow, FleetTable, AppHeader, Toasts,
  StartRunModal), each with a clause contract (`<name>.md`, underscore IDs),
  named profiles, a Vitest logic spec and a Playwright presentation spec
  citing the clauses via a same-line `// clause:` marker. One profile
  definition feeds the showcase route, both tiers, and the preview bundle.
  `scripts/check_clauses.py` stays advisory and now covers `interfaces/`.
- [x] **Tokens, in two passes.** Pass one was mechanical — every literal
  became `--c-<hex>`, buying the wiring. Pass two renamed to the semantic
  taxonomy of the canvas at `records/2026-09-05-console-restyle/`
  (`--ground-*`, `--line-*`, `--ink-*`, `--accent-*`, `--link`), values
  unchanged. `STATUS_COLORS` became a stable class per kind, so no
  presentation assertion depends on a style-attribute string.
- [x] **The two tiers.** Vitest for logic in jsdom; Playwright (Chromium
  only) for presentation against real CSS — over the showcase profiles and,
  since Task 14, over the assembled SPA itself (`interfaces/ui/app.pw.ts`,
  CONSOLE-1/2) running on `VITE_API=mock`, which is also why the `http`
  provider is now the default with `mock` explicitly selectable.
- [x] **The loop.** Repo → Claude Design is automated: `npm run ds:bundle`
  captures each profile's resolved DOM plus styles into
  `interfaces/ui/dist-ds/<component>/<profile>.html` with the `@dsCard`
  marker as the literal first line, and the push rides the orchestrator's
  `DesignSync`. Claude Design → repo is hand-carried: the canvas lands
  verbatim under `records/<date>-<topic>/` and is never edited, per
  `records/README.md`.

**Known boundaries (recorded, not fixed).**

- ⚠️ **The first canvas is structurally faithful, not a repaint.** Every
  semantic name maps 1:1 onto the value the mechanical pass found; nothing
  changed visually. The reference material examined during planning pointed
  toward a light/editorial aesthetic incompatible with the console's dark,
  dense, monospaced identity, and that direction was left open pending the
  user — so a values-level restyle is a follow-up to scope separately, now
  that the token seams exist to carry it.
- ⚠️ **`check_ui.py` skips loudly when Node is absent** (exit 0), following
  the `_TEMPORAL_IGNORES` precedent. On a machine without Node, "all gates
  pass" does not cover the UI; CI is the only place it is truly gated.
- ⚠️ **The preview bundle's fidelity is structural.** Pseudo-elements and
  keyframes ride the inlined stylesheet; webfont *metrics* depend on the
  linked Google Fonts sheet loading in the Design System pane. Faithfulness
  beyond structure was explicitly de-scoped (spec C §7 risk note).
