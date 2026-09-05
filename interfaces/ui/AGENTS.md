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
non-empty value. A suite that pins a palette value breaks when Task 16
renames the tokens.

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
