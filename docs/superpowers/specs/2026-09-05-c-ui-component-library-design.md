# C — the UI component library and the Claude Design loop

- **Date:** 2026-09-05
- **Status:** approved design, ready for planning
- **Scope:** C — the console's presentation layer. A design-system package at `interfaces/ui/`, a per-component clause contract, a showcase route, two test tiers that cite clauses, CI and `verify.py` coverage for the Node toolchain, a bidirectional Claude Design loop, and the restyle that the loop's first canvas produces.
- **Satisfies:** E-89 (new), extending FR-601 (dashboard fleet/spine/inbox, closed 2026-08-18 under E-10). Executes the extraction contract already written in `records/README.md`.
- **Baseline:** `main` at `8766cbf`; Vue 3.4, Vite 5, Vitest 1.6; `.nvmrc` pins Node 20.
- **Does not cover:** the agent board's own surface. `/projects/*` stays API-only. No board HTML is written by this spec. `src/sdlc/board/` and `src/sdlc/dashboard/` are read but not modified, except where §8 flips a frontend default.

## Problem

`records/README.md` already specifies this work, and has done since July:

> What is *extracted* from a record -- design tokens, components, and the feature-clause document for each component -- lives with the UI code and is maintained there. The record is the source, never the reference.

Nothing was ever extracted. `records/2026-07-12-factory-console/` holds the canvas the console was hand-ported from, `interfaces/dashboard/frontend/README.md` names it as the prototype, and the port was one-way: the design became Vue and the link died. There is no way to ask what a component promises, no way to see one in isolation, and no way to show Claude Design what the code actually renders.

Four facts about the tree make the gap concrete.

**There are no design tokens.** `src/styles/theme.css` is 44 lines of resets, scrollbar styling and two keyframes. Every colour, size and font is a literal inside a `<style scoped>` block: three grounds (`#0c0f14`, `#090b0f`, `#151a23`), three borders (`#171c25`, `#1e242f`, `#2a3140`) and seven greys (`#d9dfe9`, `#e8edf5`, `#c8cfdb`, `#9db4d8`, `#8a93a5`, `#7d8697`, `#5d6675`). The only named palette in the codebase is `STATUS_COLORS` (`src/constants.ts:37`), which is semantic and correct, and which is consumed as an *inline style binding* (`FleetRow.vue:21`) rather than as a class.

**The frontend is invisible to every gate.** `npm`, `node`, `vitest` and `frontend` appear nowhere in `.github/workflows/ci.yml`, `scripts/verify.py` or `.pre-commit-config.yaml`. Nine Vitest files exist and nothing runs them. A `.vue` file that fails to compile merges green.

**No component states what it promises.** `docs/documentation-rules.md` gives every unit of code three documents -- a clause contract for WHAT, an `AGENTS.md` for HOW, a module docstring for WHY. The UI has none of the three. `interfaces/` has no `AGENTS.md` at all, though it is the one package carrying a second language, a second toolchain and a second test runner.

**Nothing verifies a rendered pixel.** The nine Vitest files run in jsdom, which computes no CSS. The backend's `tests/test_dashboard_e2e.py` never touches the UI. No test in this repository would notice if every component rendered white on white.

## Decision

**The component, not the view, becomes the unit of UI work.** A sibling package at `interfaces/ui/` holds components that take display primitives and know nothing of Kroker's domain. Each carries a clause contract, a set of named profiles, and two tiers of test that cite its clauses. The profiles feed the showcase route, both test tiers, and the preview bundle pushed to Claude Design -- one definition, four consumers.

**The loop is asymmetric, and the spec says so.** Code to Claude Design is automated: a bundle built from the showcase and pushed with `DesignSync`. Claude Design to code is hand-carried: a canvas lands verbatim in `records/`, and a human or agent extracts tokens and clauses from it, exactly as `records/README.md` already requires. Claiming otherwise would promise tooling that does not exist -- a `.dc.html` is not a Vue SFC, and no decompiler makes it one.

**The apparatus is built at constant appearance, then the appearance changes.** Phases 1 through 6 must not alter how the console looks. The restyle is phase 7, after the canvas exists, and it is the first change the new safety net is asked to catch.

## 1. The target tree

```
package.json                      root, workspaces: ["interfaces/*"]  (new)
interfaces/
  AGENTS.md                       router for the interfaces tree      (new)
  ui/                                                                 (new package)
    AGENTS.md
    package.json                  @kroker/ui, source exports, no build
    src/
      tokens/
        tokens.css                every colour, size and font literal
        tokens.md                 TOKENS-n clauses
      components/<name>/
        <Name>.vue
        <name>.md                 <NAME>-n clauses (WHAT)
        <name>.profiles.ts        named profiles
        <name>.spec.ts            Vitest, logic clauses
        <name>.pw.ts              Playwright, presentation clauses
    showcase/
      index.html, main.ts, router stub
    scripts/
      build-ds-bundle.ts          showcase -> dist-ds/ via Playwright capture
  dashboard/
    frontend/                     unchanged location; consumes @kroker/ui
      src/adapters/               domain -> display primitives          (new)
scripts/check_ui.py               the single Node entry point           (new)
```

`interfaces/ui/` is a **source** package. It has no `dist/`, no library build and no emitted type declarations: `exports` maps to `./src/*`, and Vite resolves `.vue` and `.ts` directly. A compiled package for one consumer would buy nothing and cost a second watch process plus perpetually stale `.d.ts` files. The alias must be configured for `vite preview` as well as the dev server, or the Playwright web server resolves nothing.

## 2. Ownership

**The UI package never imports a Kroker domain type.** `FleetRow.vue:3` currently imports `../../api/types` and `../../composables/status`. If `interfaces/ui/` did the same it would depend on its own consumer; if it copied the types they would drift. Components therefore accept display primitives -- resolved strings, booleans, enumerated kinds -- and the dashboard owns `src/adapters/`, which maps `Run` and `InboxItem` onto them.

The test that governs this: **a component's props must be constructible without importing anything from `interfaces/dashboard/`.** A profile that cannot be written as a literal has a domain leak in it.

**Ownership of clauses follows the artifact boundary.** `docs/documentation-rules.md` requires a co-located document to change in the same commit as the behaviour it describes. A component's `.md` and its `.vue` move together, or the diff is incomplete.

## 3. The profile

A profile is a named, static description of one component in one state. It is **not** a bare prop dictionary: `FleetRow.vue:13` is a `<RouterLink>`, and mounting it without an ambient router throws. The descriptor is therefore

```ts
interface Profile {
  name: string               // kebab, unique within the component
  summary: string            // one line, shown in the showcase and on the ds card
  props: Record<string, unknown>
  slots?: Record<string, string>
  provide?: Record<string | symbol, unknown>
  route?: { path: string }   // satisfied by the showcase router stub
}
```

Four consumers, one definition:

1. **The showcase route** renders each profile inside a wrapper carrying `id="showcase-<component>-<profile>"`. The id lives on the wrapper, never on the component root, so test infrastructure never constrains a component's own markup.
2. **Playwright presentation specs** navigate to the showcase and assert against that id.
3. **Vitest logic specs** may mount a profile, and may also construct synthetic props directly. Profiles are not a mandate on unit tests: a purely invisible internal branch must not be forced to register a visible showcase state.
4. **The preview bundle** (§7) emits one HTML file per profile.

Profiles are isolated per wrapper. Shared global state -- body classes, font loading, module-level singletons -- must not leak between profiles rendered on one route.

## 4. Clause scheme

Component clauses are `<COMPONENT>-N` and `<COMPONENT>-N.M`, anchored to an `FR-xxx`, `NFR-x` or `E-xx` per `docs/modes/feature-clause-writing.md`.

**Component identifiers use underscores, never hyphens.** `scripts/check_clauses.py:17` matches `^#{2,4}\s+([A-Z][A-Z0-9_]*-\d+(?:\.\d+)*)\b`. A heading `### STATUS_BADGE-1` parses; `### STATUS-BADGE-1` does not match at all, and would be silently reported as zero clauses. The naming rule adapts to the scanner rather than the scanner to the naming, because the scanner is shared with thirteen migrated slices and this spec has no business widening a regex those depend on.

`check_clauses.py` gains two things and stays **advisory, always exiting 0**. `docs/documentation-rules.md` bans repurposing the product's own criterion-to-test traceability (`untraced_criteria`, FR-106) as this repository's development harness without a decision saying so, and spec A refused the enforcing version for that reason. Nothing in C changes that argument.

- Declarations additionally from `interfaces/**/*.md`, excluding `AGENTS.md`.
- Citations additionally from `interfaces/**/*.spec.ts` and `interfaces/**/*.pw.ts`, matching a **same-line comment marker**: `it('renders every supplied run', ...)  // clause: FLEET_TABLE-1`.

A comment marker rather than a helper function, because `check_clauses.py` is a textual scanner with no TypeScript parser, and because Vitest and Playwright are different runners whose signatures a helper would have to wrap twice. Same-line anchoring is what stops a marker from outliving the test it labels.

## 5. Tokens, in two passes

The console's palette was never designed; it accreted. Inventing semantic names for thirteen accidental hex values, and then discarding that taxonomy when the canvas brings its own, is judgment work done twice.

**Pass one (phase 4) is mechanical.** Every literal becomes a non-semantic variable named for its value -- `--c-0c0f14`, `--c-8a93a5` -- declared in `tokens.css` and referenced everywhere else. No name asserts meaning. What this buys is the *wiring*: every `<style scoped>` block across the tree stops holding literals, and that plumbing survives the restyle untouched.

**Pass two (phase 7) is semantic.** The canvas defines the taxonomy; the mechanical names are renamed to it in one largely mechanical pass, and values change with them.

Two things falsify "tokens.css holds every literal" on day one, and both are resolved rather than excused:

- **`STATUS_COLORS` becomes a stable class per kind.** Today the colour is bound inline (`:style="{ background: meta.color }"`), which makes any presentation assertion depend on a style-attribute string. Each status kind instead maps to a stable class -- the reference project's `item.Access.itemClass()` pattern -- backed by a token. This is what makes a Playwright assertion about status legible.
- **Fonts get token names.** `'IBM Plex Sans'` and `'IBM Plex Mono'` appear as string literals twenty-three times across the components' `<style>` blocks, and are loaded from Google Fonts in `index.html`. The families become `--font-sans` and `--font-mono`; the `index.html` link stays, since self-hosting is a separate concern this spec does not open.

**Assertions must never pin a hex value or a pixel.** Playwright specs in phases 3 through 6 assert structure, stable classes, and that a custom property *resolves to something* -- never what it resolves to. A suite that pins the old palette burns down at exactly the moment phase 7 needs it.

## 6. The two test tiers

**Vitest** keeps the existing idiom -- jsdom, `@vue/test-utils`, `data-testid`, Pinia where a store is genuinely involved -- and covers logic clauses: what renders given what input, what is emitted, how an edge case degrades.

**Playwright** covers presentation clauses in a real browser with real CSS, against two targets:

1. the showcase route, per profile;
2. **the real Factory Console**, running on the mock provider. A safety net stretched only over the showcase misses regressions in the pages that actually ship. The mock provider makes the whole SPA runnable headless with no backend, so this costs one more Vite server and no Temporal.

Chromium only, `--with-deps` in CI, cached.

`vue-tsc --noEmit` will typecheck the new `.pw.ts` files and the `ui` package, so `@playwright/test` types and the `tsconfig` include paths are part of phase 2, not an afterthought.

## 7. The loop

**Claude Design to repo (hand-carried).** A canvas lands verbatim under `records/<YYYY-MM-DD>-<topic>/` -- the `.dc.html` plus the `support.js` it loads -- and is never edited afterwards, per `records/README.md`. Extraction of tokens and clauses is authored work, reviewed like any other diff. This direction is **not** automated, and this spec does not pretend it is.

**Repo to Claude Design (automated).** `npm run ds:bundle` drives `scripts/build-ds-bundle.ts`, which:

1. serves the showcase;
2. for each profile, navigates Playwright to `#showcase-<component>-<profile>` and serializes the resolved DOM together with the styles that apply to it;
3. writes `interfaces/ui/dist-ds/<component>/<profile>.html`, **prepending** `<!-- @dsCard group="..." -->` as the literal first line after serialization, because bundlers strip leading comments and the marker's position is load-bearing;
4. writes nothing else -- `_ds_manifest.json` is compiled by the Design System pane from the markers, not by this repository.

Playwright capture rather than `@vue/server-renderer`: SSR would demand scoped-style extraction, mock injection and slot handling, which is a small project of its own, and its output would be what a server *thinks* the component renders. The browser tier is already being installed for §6, and what it captures is by construction what the component actually renders.

`dist-ds/` is git-ignored. The push itself is an **orchestrator-run** step (§10).

## 8. The HTTP provider

`src/api/http.ts` is a complete `DashboardApi` implementation -- every method, SSE `subscribe` against `/events`, and field mappings matching the live backend (`run_id`, `cost_usd_total`, `awaiting:*`). `ROADMAP.md:279` already records FR-601 as closed and states that the `http` provider serves live Temporal state.

What remains is a default and a stale document. `src/api/client.ts:9` selects mock unless `VITE_API === 'http'`, and `frontend/README.md` calls `http.ts` "reserved for the future FastAPI provider ... not yet wired", which is false. Phase 6 flips the default to `http`, keeps `mock` explicitly selectable (the Playwright app tier and the showcase both depend on it), and corrects the README.

## 9. CI and `verify.py`

**One wrapper, invoked identically from both sides.** `tests/test_verify.py:43` collects every `run:` value in `ci.yml`, exempts only `pip install`, and asserts each has a matching gate in `scripts/verify.py`. A bare `run: npm ci` therefore fails the suite. Moving the UI job into a second workflow file would be worse: `test_verify.py:16` reads `ci.yml` by fixed path, so parity would quietly stop being checked -- the precise drift that test exists to catch.

Both sides therefore run `python scripts/check_ui.py`. `_gate_key` reduces a command to its first two non-flag tokens after stripping `python`, so the two sides match by construction. The wrapper owns install, typecheck, Vitest, both Playwright tiers, and -- critically -- the Windows detail that `npm` is `npm.cmd`, which makes a bare `subprocess.run(["npm", ...])` raise `FileNotFoundError` rather than fail a gate.

**When Node is absent, `check_ui.py` skips loudly and exits 0.** This follows `scripts/verify.py:24`, where the temporal tier already skips a named set on Windows. The cost is stated plainly: on a machine without Node, `verify.py` reporting "all gates pass" no longer covers the UI, and CI becomes the only place the UI is truly gated. The alternative -- making Node a hard local dependency for every Python contributor -- was judged the worse trade.

CI pins Node from `.nvmrc` (currently 20; the local machine runs 25.9.0, and pinning is what surfaces that drift) and caches both the npm download and the Playwright browser.

## 10. Orchestrator-run steps

Two steps cannot run in a planning or coding pane, because `DesignSync` and Claude Design authoring live in the orchestrator session. The plan marks them explicitly and specifies their artifacts precisely enough to execute verbatim.

- **O-1 (phase 5): push the previews.** `list_projects`, then `get_project` to confirm the target is `PROJECT_TYPE_DESIGN_SYSTEM` (the type is immutable at creation, so pushing to a regular project never makes it one); `finalize_plan` with `localDir` = `interfaces/ui/dist-ds` and `writes` = `["<component>/**/*.html"]`; then `write_files` with a `localPath` per file. No `register_assets` -- the cards are built from the `@dsCard` markers §7 emits.
- **O-2 (before phase 7): land the canvas.** Author a canvas from the pushed previews; save the export to `records/2026-09-05-console-restyle/` as `<Name>.dc.html` plus its `support.js`, verbatim and unedited. Nothing else enters that directory.

## 11. Clauses

This spec introduces **E-89** and the `FR-1400` block. `docs/documentation-rules.md` requires `ROADMAP.md` to describe `main` only, so the anchors are declared here and each ROADMAP entry lands in the same diff as the code that satisfies it -- never ahead of it.

- **FR-1400** component library -- `interfaces/ui/` holds presentation components that import no domain type.
- **FR-1401** every component carries a clause contract co-located with it.
- **FR-1402** every component carries at least one profile, rendered by the showcase.
- **FR-1403** presentation clauses are verified in a real browser.
- **FR-1404** design tokens are the only place a colour, size or font literal appears.
- **FR-1405** the showcase is exportable as a Claude Design preview bundle.
- **FR-1406** the Node toolchain is gated in CI.

## 12. Deliverables

1. Root `package.json` with `workspaces`, and `.gitignore` entries for root `node_modules` and `interfaces/ui/dist-ds`.
2. `interfaces/AGENTS.md` and `interfaces/ui/AGENTS.md`.
3. `interfaces/ui/` with `tokens.css`, `tokens.md`, and seven migrated components, each with `.vue`, `.md`, `.profiles.ts`, `.spec.ts` and `.pw.ts`.
4. The showcase route and its router stub.
5. `interfaces/dashboard/frontend/src/adapters/`.
6. `scripts/check_ui.py`; a `ui` job in `ci.yml`; matching gates in `scripts/verify.py`.
7. `check_clauses.py` extended to `interfaces/**`; a component `.md` template in `docs/templates/`.
8. `scripts/build-ds-bundle.ts`.
9. `VITE_API` default flipped; `frontend/README.md` corrected.
10. `records/2026-09-05-console-restyle/` and the restyle.
11. `.gitignore` amended so `docs/superpowers/plans/` is tracked (see Risks).

## Risks

**The plan document for this spec is currently untracked.** `.gitignore:14` is `docs/superpowers/*` with only `!docs/superpowers/specs/` re-included, yet 47 plans are committed and 76 exist on disk, and `docs/documentation-rules.md` lists `docs/superpowers/plans/` as a write-once durability class. New plans are being silently dropped. Deliverable 11 adds `!docs/superpowers/plans/`. This is a defect C found rather than caused, and it is fixed in C's first phase, because C's own plan is otherwise invisible to review.

**The preview builder is the largest single unknown.** Both critique agents named it independently. Serializing a live DOM with its computed styles into a standalone HTML file is not difficult in principle, but faithfulness -- fonts, pseudo-elements, keyframes -- is where it will cost time. Phase 5 is the phase most likely to overrun, and it is deliberately placed after the console is already fully covered by tests, so an overrun delays the loop rather than the safety net.

**Seven components is the largest scope item.** If phase 4 proves slower than planned, the honest cut is to migrate fewer components fully rather than all seven partially: a component without its clause document and both test tiers is not migrated, and half-migrated components would leave the tree worse than not starting.

**A restyle judged against mock data is a restyle judged against fiction.** This is why phase 6 (the `http` default) precedes phase 7 (the restyle), rather than trailing it as the smaller change.
