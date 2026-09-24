# interfaces/ui/ — AGENTS.md

Local invariants for the `@kroker/ui` design-system package.

## Clause IDs use underscores, never hyphens

`scripts/check_clauses.py` matches `^#{2,4}\s+([A-Z][A-Z0-9_]*-\d+)`.
A heading `### STATUS_PIP-1` parses; `### STATUS-PIP-1` silently matches
nothing. Name clause prefixes after the component directory:
`stage_dots/` → `STAGE_DOTS-N`.

## Clause citation marker

Cite a clause on the same line as the test that covers it:

```ts
it('renders one mark per stage', () => { ... })  // clause: STAGE_DOTS-1
```

Same-line anchoring is mandatory: `check_clauses.py` is a textual scanner
with no TypeScript parser, and a marker that drifts away from its test is
indistinguishable from an uncovered clause.

## No hex values in Playwright assertions

Playwright specs must never assert a hex colour or a pixel measurement.
Assert structure (DOM elements, counts), stable CSS classes
(`cmp-stage-dot-active`), and that a custom property resolves to a
non-empty value. A suite that pins a palette value breaks on the next
token pass: pass three replaced every value at once.

## Tokens

`src/tokens/tokens.css` is the only place a colour, size or radius value
is written; components consume `var(--*)`. The contract is
`src/tokens/tokens.md`:

- No bare hex in a component stylesheet (TOKENS-2). Pixel values in a
  component's own `<style>` are allowed.
- Dark lives on `:root`, light on `[data-theme='light']`. A new colour,
  shadow or backdrop token needs both declarations (TOKENS-3).
- Pass-two names (`--ground-0..5`, `--ink-tertiary`, `--accent*`,
  `--status-blocked`, …) survive only as `var()` aliases of pass-three
  tokens, and only for one release (TOKENS-4). New code uses pass-three
  names.

## Profile descriptor shape

```ts
interface Profile {
  name: string           // kebab-case, unique within the component
  summary: string        // one line; shown in the showcase and the ds card
  props: Record<string, unknown>
  slots?: Record<string, string>
  provide?: Record<string | symbol, unknown>
  route?: { path: string }
}
```

The `id` for each profile in the showcase DOM is
`showcase-<component>-<profile>` (computed by `profileId(component, profile)`
from `src/profile.ts`).

`slots` values are text. The showcase passes each entry to the
component as named-slot content (`default` fills the default slot),
interpolated and never rendered with `v-html` (`showcase/showcase.md`
SHOWCASE-1). A profile whose component needs slot content must declare
it, or the showcase renders an empty control.

## Adding a component

1. Create `src/components/<name>/` with five files: `<Name>.vue`,
   `<name>.md` (clauses `<NAME>-N`), `<name>.profiles.ts`,
   `<name>.spec.ts` (Vitest) and `<name>.pw.ts` (Playwright).
2. Add the profile set to `showcase/registry.ts` in the same change. A
   `.pw.ts` looks up `#showcase-<name>-<profile>`, which exists only once
   the set is registered. The registry runs from primitives to screens.
   Put the new set at its layer and don't reorder existing entries.
   `ProfileSet.group` names the Design System pane section (`Primitives`,
   `Forms`, `Status`, `Data`, `Shell`, `Fleet`, `Graph`, …).
3. Export the component and its public prop types from `src/index.ts`.
   Consumers import from the `@kroker/ui` barrel.
4. Done means `python scripts/check_ui.py` is green, and the
   `python scripts/check_clauses.py` report shows no
   `clause with no test: <NAME>-*` line and no dangling citation. The
   script always exits 0, so read its output.

## Assembled-console clauses

`app.md` (`CONSOLE-N`) holds the contract for the shipped dashboard
rather than for one component. `app.pw.ts` covers it against a
`VITE_API=mock` build. Cite `CONSOLE-N` there. For TypeScript,
`check_clauses.py` scans only `*.spec.ts` and `*.pw.ts`, so a citation in a dashboard `*.test.ts`
is invisible to it.

## Showcase id placement

The showcase `id` attribute lives on the **wrapper article**, never on the
component root element. This rule keeps test infrastructure from
constraining a component's own markup.

## Running this package's tests

Before running Playwright locally, always ensure `PLAYWRIGHT_BROWSERS_PATH` is set to avoid filling up the primary system drive:

```bash
export PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
# Windows PowerShell:
# $env:PLAYWRIGHT_BROWSERS_PATH="D:/own/.pw-browsers"
```

```bash
# Vitest (logic specs)
npm run test --workspace @kroker/ui

# Typecheck
npm run typecheck --workspace @kroker/ui

# Playwright (presentation specs — needs a browser install the first time)
npm run test:pw --workspace @kroker/ui

# Both tiers via the Python wrapper
python scripts/check_ui.py
```
