# C — UI Component Library and Claude Design Loop: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Factory Console's Vue SPA into a documented, clause-bearing component library that is gated in CI, visible in a showcase, exportable to Claude Design, and restyled from the canvas that export produces.

**Architecture:** A source-only npm workspace package at `interfaces/ui/` holds presentation components that import no domain type. Each component carries a clause contract, named profiles, a Vitest logic spec and a Playwright presentation spec. One profile definition drives the showcase route, both test tiers, and the Claude Design preview bundle. A single Python wrapper, `scripts/check_ui.py`, is the only Node entry point, invoked identically by CI and `verify.py`.

**Tech Stack:** Vue 3.4, Vite 5, Vitest 1.6, `@vue/test-utils` 2.4, Playwright (Chromium only), TypeScript 5.4, `vue-tsc` 2.0, npm workspaces, Python 3.11.

**Spec:** `docs/superpowers/specs/2026-09-05-c-ui-component-library-design.md`

## Global Constraints

- **File-size ceiling: 1000 physical lines.** `interfaces/` is already in scope (`scripts/check_file_size.py:37`); `*/dist/*` and `*/node_modules/*` are already exempt. No change to that script is needed or permitted by this plan.
- **Root `AGENTS.md` ceiling: 250 lines.** Do not inline component contracts there.
- **Clause identifiers use underscores, never hyphens.** `### STATUS_BADGE-1` parses; `### STATUS-BADGE-1` silently matches nothing (`scripts/check_clauses.py:17`).
- **Clause citation marker is a same-line comment:** `// clause: FLEET_TABLE-1`.
- **`check_clauses.py` stays advisory and always exits 0.** Never make it a gate.
- **Playwright assertions must never pin a hex value or a pixel measurement.** Assert structure, stable classes, and that a custom property resolves to a non-empty value.
- **`interfaces/ui/` must never import from `interfaces/dashboard/`.** Props are display primitives.
- **Phases 1–6 must not change how the console looks.** Appearance changes only in phase 7.
- **`@dsCard` must be the literal first line** of every generated preview file.
- **Node pinned from `interfaces/dashboard/frontend/.nvmrc` (currently `20`).**
- **Chromium only** for Playwright.
- **ARCHITECTURE.md / ROADMAP.md describe `main` only.** A ROADMAP entry for an `FR-14xx` lands in the same commit as the code satisfying it, never ahead of it.

---

## Phase 1 — The workspace and the seam

### Task 1: Track plans, and create the npm workspace

**Files:**
- Modify: `.gitignore:14`
- Create: `package.json` (repo root)
- Test: `tests/test_plans_are_tracked.py`

**Interfaces:**
- Produces: a root npm workspace covering `interfaces/*`; `docs/superpowers/plans/` under version control.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plans_are_tracked.py
"""Plans are a durability class, not scratch (spec C, Risks).

docs/documentation-rules.md lists docs/superpowers/plans/ as write-once
documentation, but .gitignore excluded it while 47 plans were already
committed. New plans were being silently dropped.
"""

import subprocess
from pathlib import Path


def _ignored(path: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", path], capture_output=True).returncode == 0


def test_plans_directory_is_tracked():
    assert not _ignored("docs/superpowers/plans/example.md"), (
        "docs/superpowers/plans/ is git-ignored; new plans would never be committed"
    )


def test_specs_directory_is_still_tracked():
    assert not _ignored("docs/superpowers/specs/example.md")


def test_superpowers_scratch_is_still_ignored():
    assert _ignored("docs/superpowers/scratch/notes.md")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_plans_are_tracked.py -v`
Expected: `test_plans_directory_is_tracked` FAILS; the other two PASS.

- [ ] **Step 3: Fix `.gitignore`**

Add the negation immediately after the existing `!docs/superpowers/specs/` line:

```gitignore
docs/superpowers/*
!docs/superpowers/specs/
!docs/superpowers/plans/
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_plans_are_tracked.py -v`
Expected: 3 passed.

- [ ] **Step 5: Create the root workspace**

```json
{
  "name": "kroker-interfaces",
  "private": true,
  "workspaces": ["interfaces/ui", "interfaces/dashboard/frontend"]
}
```

Note: `interfaces/dashboard/frontend` is listed explicitly rather than as `interfaces/*`, because the frontend is nested two levels deep and a single-segment glob would not reach it.

- [ ] **Step 6: Add the new ignores**

Append to `.gitignore`:

```gitignore
node_modules/
interfaces/ui/dist-ds/
```

- [ ] **Step 7: Install and confirm the lockfile moved to root**

Run: `npm install`
Expected: a root `package-lock.json` appears and `interfaces/dashboard/frontend/package-lock.json` is superseded. Delete the nested lockfile — a workspace has exactly one.

- [ ] **Step 8: Confirm the existing suite still passes**

Run: `npm run test --workspace sdlc-dashboard`
Expected: the 9 existing Vitest files pass, unchanged.

- [ ] **Step 9: Commit**

```bash
git add .gitignore package.json package-lock.json tests/test_plans_are_tracked.py
git rm --cached interfaces/dashboard/frontend/package-lock.json
git add -A interfaces/dashboard/frontend
git commit -m "build: npm workspace at root, and track superpowers plans

docs/superpowers/plans/ was git-ignored while 47 plans were already
committed and documentation-rules.md lists it as a durability class.
New plans were silently dropped; this plan was the first casualty.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe"
```

---

### Task 2: The `@kroker/ui` package, its alias, and the two AGENTS.md routers

**Files:**
- Create: `interfaces/ui/package.json`, `interfaces/ui/tsconfig.json`, `interfaces/ui/src/index.ts`
- Create: `interfaces/AGENTS.md`, `interfaces/ui/AGENTS.md`
- Modify: `interfaces/dashboard/frontend/vite.config.ts`, `interfaces/dashboard/frontend/tsconfig.json`, `interfaces/dashboard/frontend/package.json`

**Interfaces:**
- Consumes: the root workspace from Task 1.
- Produces: `@kroker/ui` importable from the dashboard as source, in dev, build, **and `vite preview`**.

- [ ] **Step 1: Create the package manifest**

```json
{
  "name": "@kroker/ui",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "exports": {
    "./tokens.css": "./src/tokens/tokens.css",
    "./*": "./src/*"
  }
}
```

No `main`, no `build` script, no `dist`. Vite resolves `.vue` and `.ts` from source.

- [ ] **Step 2: Declare the dependency and the alias**

In `interfaces/dashboard/frontend/package.json`, add to `dependencies`:

```json
"@kroker/ui": "*"
```

In `interfaces/dashboard/frontend/vite.config.ts`, add a `resolve.alias` entry. It must sit outside `server`, so that `build` and `preview` resolve it too — a `server`-only alias breaks the Playwright web server, which runs `vite preview`:

```ts
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@kroker/ui': fileURLToPath(new URL('../../ui/src', import.meta.url)),
    },
  },
  // ... existing server.proxy and test blocks unchanged
})
```

- [ ] **Step 3: Write a smoke component that proves the seam**

```vue
<!-- interfaces/ui/src/components/status_pip/StatusPip.vue -->
<script setup lang="ts">
defineProps<{ kind: string; pulsing?: boolean }>()
</script>

<template>
  <span class="cmp-status-pip" :class="[`cmp-status-pip-${kind}`, { 'is-pulsing': pulsing }]" />
</template>

<style scoped>
.cmp-status-pip {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}
</style>
```

This component takes a `kind` string, not a `Run`, and imports nothing. That is the ownership rule from spec §2 in its smallest form.

- [ ] **Step 4: Write the failing test proving the alias resolves**

```ts
// interfaces/dashboard/frontend/src/api/seam.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusPip from '@kroker/ui/components/status_pip/StatusPip.vue'

describe('the @kroker/ui seam', () => {
  it('resolves a component from the ui package by package name', () => {
    const w = mount(StatusPip, { props: { kind: 'running' } })
    expect(w.find('.cmp-status-pip-running').exists()).toBe(true)
  })
})
```

- [ ] **Step 5: Run it to verify it fails**

Run: `npm run test --workspace sdlc-dashboard`
Expected: FAIL — `Failed to resolve import "@kroker/ui/..."`.

- [ ] **Step 6: Make it pass**

Vitest reads `resolve.alias` from `vite.config.ts`, so Step 2's alias is the implementation. Re-run and confirm.

Run: `npm run test --workspace sdlc-dashboard`
Expected: PASS.

- [ ] **Step 7: Confirm typecheck sees the package**

Add to `interfaces/dashboard/frontend/tsconfig.json` under `compilerOptions`:

```json
"paths": { "@kroker/ui/*": ["../../ui/src/*"] }
```

Run: `npm run typecheck --workspace sdlc-dashboard`
Expected: no errors.

- [ ] **Step 8: Write `interfaces/AGENTS.md`**

A router, not an encyclopedia. It must state: the tree holds two packages; `ui/` is the design system and `dashboard/frontend/` consumes it; `ui/` may not import from `dashboard/`; the Node toolchain is gated only through `python scripts/check_ui.py`; the 1000-line ceiling already covers this tree; and that per-component contracts live in each component's own `.md`.

- [ ] **Step 9: Write `interfaces/ui/AGENTS.md`**

Local invariants only: the underscore rule for clause IDs, the `// clause:` marker form, the ban on hex values in Playwright assertions, the profile descriptor's shape, the rule that showcase ids live on the wrapper and never on a component root, and how to run just this package's tests.

- [ ] **Step 10: Commit**

```bash
git add interfaces/ui interfaces/AGENTS.md interfaces/dashboard/frontend
git commit -m "feat(ui): @kroker/ui source package and the dashboard alias

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe"
```

---

## Phase 2 — The Node gate

### Task 3: `scripts/check_ui.py`, the CI job, and the verify parity

**Files:**
- Create: `scripts/check_ui.py`
- Modify: `scripts/verify.py:40-49`, `.github/workflows/ci.yml`
- Test: `tests/test_check_ui.py`, existing `tests/test_verify.py`

**Interfaces:**
- Consumes: the workspace from Task 1.
- Produces: `python scripts/check_ui.py` — the single Node entry point. Signature: `main(argv: list[str] | None = None) -> int`.

**Why one wrapper:** `tests/test_verify.py:43` scrapes every `run:` in `ci.yml`, exempts only `pip install`, and asserts a matching `verify.py` gate. A bare `run: npm ci` fails that test. `_gate_key` takes the first two non-flag tokens after stripping `python`, so `python scripts/check_ui.py` on both sides matches by construction.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_ui.py
"""The Node gate's contract (spec C §9)."""

import subprocess
import sys
from pathlib import Path

from scripts.check_ui import STEPS, main


def test_skips_cleanly_when_npm_is_absent(monkeypatch):
    monkeypatch.setattr("scripts.check_ui.shutil.which", lambda _: None)
    assert main([]) == 0


def test_says_so_loudly_when_it_skips(monkeypatch, capsys):
    monkeypatch.setattr("scripts.check_ui.shutil.which", lambda _: None)
    main([])
    assert "SKIPPED" in capsys.readouterr().out


def test_every_step_is_a_workspace_aware_npm_invocation():
    for _, args in STEPS:
        assert args[0] in {"ci", "run", "exec"}


def test_ci_invokes_this_script_and_never_npm_directly():
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    runs = [ln.split("run:", 1)[1].strip() for ln in ci.splitlines() if "run:" in ln]
    assert any("check_ui.py" in r for r in runs), "ci.yml must invoke the wrapper"
    assert not any(r.startswith(("npm", "npx")) for r in runs), (
        "a bare npm/npx run: line breaks tests/test_verify.py parity"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_check_ui.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.check_ui'`.

- [ ] **Step 3: Write the wrapper**

```python
# scripts/check_ui.py
"""The Node gate (spec C §9). One entry point for every JavaScript check.

Invoked identically by .github/workflows/ci.yml and scripts/verify.py.
tests/test_verify.py reduces a command to its first two non-flag tokens,
so both sides naming `python scripts/check_ui.py` is what keeps the
parity test green while npm runs underneath. A bare `run: npm ci` in
ci.yml fails that test, and hiding the UI job in a second workflow file
is worse: test_verify.py:16 reads ci.yml by fixed path, so parity would
silently stop being checked.

npm is npm.cmd on Windows. subprocess.run(["npm", ...]) raises
FileNotFoundError there rather than failing a gate, so every invocation
resolves the real executable through shutil.which first.

Node absent means skip loudly and exit 0, following the _TEMPORAL_IGNORES
precedent (verify.py:24). The cost is deliberate and stated in spec C
§9: on a machine without Node, "all gates pass" does not cover the UI,
and CI is the only place the UI is truly gated.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

DASH = "sdlc-dashboard"
UI = "@kroker/ui"

# (label, npm argv). Cheapest first, same principle as verify.py's GATES.
STEPS: tuple[tuple[str, list[str]], ...] = (
    ("install", ["ci"]),
    ("typecheck", ["run", "typecheck", "--workspace", DASH]),
    ("vitest-dashboard", ["run", "test", "--workspace", DASH]),
    ("vitest-ui", ["run", "test", "--workspace", UI]),
    ("playwright-browser", ["exec", "--", "playwright", "install", "--with-deps", "chromium"]),
    ("playwright", ["run", "test:pw", "--workspace", UI]),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    npm = shutil.which("npm")
    if npm is None:
        print(
            "SKIPPED: npm is not on PATH, so the UI gate did not run.\n"
            "         This machine's `all gates pass` does NOT cover the UI.\n"
            "         CI runs this gate on every push (spec C, §9).",
            flush=True,
        )
        return 0

    failed: list[str] = []
    for label, args in STEPS:
        print(f"=== ui: {label} ===", flush=True)
        if subprocess.run([npm, *args]).returncode != 0:
            failed.append(label)

    if failed:
        print(f"\nUI FAILED: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("\nui gate passes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the npm scripts the wrapper calls**

In `interfaces/ui/package.json`, add:

```json
"scripts": {
  "test": "vitest run",
  "test:pw": "playwright test"
}
```

- [ ] **Step 5: Add the `verify.py` gate**

In `scripts/verify.py`, append to `GATES` after `pytest-temporal` — it is the most expensive gate, and `GATES` is ordered cheapest-first:

```diff
     (
         "pytest-temporal",
         [sys.executable, "-m", "pytest", "-m", "temporal", "-q", *_TEMPORAL_IGNORES],
     ),
+    ("ui", [sys.executable, "scripts/check_ui.py"]),
 )
```

- [ ] **Step 6: Add the CI job**

In `.github/workflows/ci.yml`, add a second job. It must contain exactly **one** `run:` line:

```yaml
  ui:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-node@v4
        with:
          node-version-file: interfaces/dashboard/frontend/.nvmrc
          cache: npm

      - uses: actions/setup-python@v7
        with:
          python-version: "3.11"

      - uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: playwright-${{ hashFiles('package-lock.json') }}

      # One run: line, deliberately. tests/test_verify.py asserts every
      # run: in this file has a matching gate in scripts/verify.py; the
      # browser install and every npm call live inside the wrapper.
      - name: UI gate
        run: python scripts/check_ui.py
```

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_check_ui.py tests/test_verify.py -v`
Expected: all pass, including `test_every_ci_gate_is_in_verify`.

- [ ] **Step 8: Run the real gate**

Run: `python scripts/check_ui.py`
Expected: on a machine with Node, the steps run and the script reports `ui gate passes`. `playwright` will fail until Task 5 adds a spec — accept a failing `playwright` step here only if `interfaces/ui/playwright.config.ts` does not yet exist; otherwise fix before committing.

- [ ] **Step 9: Commit**

```bash
git add scripts/check_ui.py scripts/verify.py .github/workflows/ci.yml tests/test_check_ui.py interfaces/ui/package.json
git commit -m "ci: gate the Node toolchain through one wrapper

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe"
```

---

## Phase 3 — Profiles, the showcase, and the first migrated component

### Task 4: The profile descriptor and the showcase harness

**Files:**
- Create: `interfaces/ui/src/profile.ts`, `interfaces/ui/showcase/index.html`, `interfaces/ui/showcase/main.ts`, `interfaces/ui/showcase/Showcase.vue`, `interfaces/ui/showcase/registry.ts`, `interfaces/ui/vite.config.ts`, `interfaces/ui/playwright.config.ts`

**Interfaces:**
- Produces: `Profile` (exact shape below); `defineProfiles(component, group, profiles)`; a showcase served at `/` rendering every registered profile inside `#showcase-<component>-<profile>`.

- [ ] **Step 1: Define the profile type**

```ts
// interfaces/ui/src/profile.ts
import type { Component } from 'vue'

export interface Profile {
  /** kebab-case, unique within the component */
  name: string
  /** one line, rendered in the showcase and used as the ds card subtitle */
  summary: string
  props: Record<string, unknown>
  slots?: Record<string, string>
  provide?: Record<string | symbol, unknown>
  /** satisfied by the showcase router stub; components using RouterLink need it */
  route?: { path: string }
}

export interface ProfileSet {
  /** snake_case, matches the component directory and the clause ID prefix */
  component: string
  /** Design System pane section, e.g. "Fleet" */
  group: string
  target: Component
  profiles: Profile[]
}

export function defineProfiles(set: ProfileSet): ProfileSet {
  const seen = new Set<string>()
  for (const p of set.profiles) {
    if (seen.has(p.name)) {
      throw new Error(`${set.component}: duplicate profile "${p.name}"`)
    }
    seen.add(p.name)
  }
  if (set.profiles.length === 0) {
    throw new Error(`${set.component}: a component must declare at least one profile`)
  }
  return set
}

/** The single source of the DOM id every consumer agrees on. */
export function profileId(component: string, profile: string): string {
  return `showcase-${component}-${profile}`
}
```

- [ ] **Step 2: Write the failing test for the id contract and the guards**

```ts
// interfaces/ui/src/profile.spec.ts
import { describe, it, expect } from 'vitest'
import { defineProfiles, profileId } from './profile'

const Stub = { template: '<i />' }

describe('profiles', () => {
  it('builds the showcase id every consumer agrees on', () => {
    expect(profileId('stage_dots', 'all-done')).toBe('showcase-stage_dots-all-done')
  })

  it('rejects a duplicate profile name', () => {
    expect(() =>
      defineProfiles({
        component: 'x', group: 'G', target: Stub,
        profiles: [
          { name: 'a', summary: 's', props: {} },
          { name: 'a', summary: 's', props: {} },
        ],
      }),
    ).toThrow('duplicate profile')
  })

  it('rejects a component with no profile', () => {
    expect(() =>
      defineProfiles({ component: 'x', group: 'G', target: Stub, profiles: [] }),
    ).toThrow('at least one profile')
  })
})
```

- [ ] **Step 3: Run it**

Run: `npm run test --workspace @kroker/ui`
Expected: PASS (the implementation in Step 1 satisfies it — this test locks the contract for later tasks).

- [ ] **Step 4: Write the showcase renderer**

```vue
<!-- interfaces/ui/showcase/Showcase.vue -->
<script setup lang="ts">
import { profileId } from '../src/profile'
import { REGISTRY } from './registry'
</script>

<template>
  <main class="showcase">
    <section v-for="set in REGISTRY" :key="set.component">
      <h2>{{ set.component }}</h2>
      <article
        v-for="p in set.profiles"
        :key="p.name"
        :id="profileId(set.component, p.name)"
        class="showcase-profile"
      >
        <h3>{{ p.name }}</h3>
        <p>{{ p.summary }}</p>
        <!-- The id is on this wrapper, never on the component root, so
             test infrastructure never constrains a component's markup. -->
        <div class="showcase-stage">
          <component :is="set.target" v-bind="p.props" />
        </div>
      </article>
    </section>
  </main>
</template>
```

- [ ] **Step 5: Write the router stub**

`FleetRow.vue:13` is a `<RouterLink>`; mounting it without an ambient router throws, and a live router would hijack navigation inside the showcase. `showcase/main.ts` installs a memory-history router with one catch-all route so links resolve and go nowhere:

```ts
// interfaces/ui/showcase/main.ts
import { createApp } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import Showcase from './Showcase.vue'
import '../src/tokens/tokens.css'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:catchAll(.*)', component: { template: '<div />' } }],
})

createApp(Showcase).use(router).mount('#app')
```

- [ ] **Step 6: Add the Vite and Playwright configs**

`interfaces/ui/vite.config.ts` sets `root: 'showcase'` and a Vitest `jsdom` block mirroring the dashboard's. `interfaces/ui/playwright.config.ts` declares Chromium only and a `webServer` running `vite preview` against the showcase — which is why Task 2's alias had to live outside `server`.

- [ ] **Step 7: Verify the showcase boots**

Run: `npm run dev --workspace @kroker/ui`
Expected: the showcase serves and renders the `StatusPip` section from Task 2 once it is registered.

- [ ] **Step 8: Commit**

```bash
git add interfaces/ui
git commit -m "feat(ui): profile descriptor and the showcase harness

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe"
```

---

### Task 5: Migrate `StageDots` whole — contract, profiles, both tiers

`StageDots` is the right pilot: 57 lines, no store, and its entire job is mapping state to marks — the same shape as the reference project's `entry_list`.

**Files:**
- Create: `interfaces/ui/src/components/stage_dots/{StageDots.vue,stage_dots.md,stage_dots.profiles.ts,stage_dots.spec.ts,stage_dots.pw.ts}`
- Delete: `interfaces/dashboard/frontend/src/components/fleet/StageDots.vue`
- Modify: `interfaces/dashboard/frontend/src/components/fleet/FleetRow.vue:6`

**Interfaces:**
- Consumes: `Profile`, `defineProfiles`, `profileId` from Task 4.
- Produces: `StageDots` with props `{ dots: StageDot[] }` where `StageDot = { stage: string; state: DotState }` and `DotState = 'pending' | 'active' | 'done' | 'blocked' | 'failed' | 'skipped'`. The dashboard's adapter (Task 11) produces this array; the component never sees a `Run`.

- [ ] **Step 1: Write the clause contract**

```markdown
<!-- interfaces/ui/src/components/stage_dots/stage_dots.md -->
# Stage Dots Component

Renders one mark per pipeline stage, in supplied order, showing how far a
run has progressed. The caller owns stage identity, stage order, and the
resolution of a run's position into per-stage states; the component owns
the mark vocabulary and its visual behaviour.

## Requirements

### STAGE_DOTS-1
A Stage Dots renders exactly one mark per supplied stage, in supplied
order. [FR-1400]

### STAGE_DOTS-1.1
An empty stage list renders no marks and is not an error: a run whose
pipeline is not yet resolved has nothing to show. [FR-1400]

### STAGE_DOTS-1.2
An unknown state fails rendering rather than falling back to a default.
A silently-wrong progress mark is worse than a visible failure. [FR-1401]

### STAGE_DOTS-2
Each mark carries its state as a stable class, `cmp-stage-dot-<state>`,
independent of the colour that class resolves to. [FR-1404]

### STAGE_DOTS-3
The `active` and `blocked` states are the only animated marks. [FR-1403]

### STAGE_DOTS-4
Each mark exposes its stage name and state as an accessible title, so a
mark is identifiable without colour vision. [NFR-4]

## Failure modes

An unknown state raises at render time (STAGE_DOTS-1.2). A missing
`dots` prop is a caller error and renders nothing (STAGE_DOTS-1.1).
```

- [ ] **Step 2: Write the profiles**

```ts
// interfaces/ui/src/components/stage_dots/stage_dots.profiles.ts
import { defineProfiles } from '../../profile'
import StageDots from './StageDots.vue'

const S = ['intake', 'clarify', 'architecture', 'code', 'review', 'qa', 'deploy']
const all = (state: string) => S.map((stage) => ({ stage, state }))

export default defineProfiles({
  component: 'stage_dots',
  group: 'Fleet',
  target: StageDots,
  profiles: [
    { name: 'untouched', summary: 'A queued run: every stage pending.', props: { dots: all('pending') } },
    { name: 'mid-flight', summary: 'Four done, one active, the rest pending.',
      props: { dots: S.map((stage, i) => ({ stage, state: i < 4 ? 'done' : i === 4 ? 'active' : 'pending' })) } },
    { name: 'blocked', summary: 'Held at a gate — the blocked mark pulses.',
      props: { dots: S.map((stage, i) => ({ stage, state: i < 3 ? 'done' : i === 3 ? 'blocked' : 'pending' })) } },
    { name: 'every-state', summary: 'All six states in sequence, for mark comparison.',
      props: { dots: ['pending', 'active', 'done', 'blocked', 'failed', 'skipped'].map((state, i) => ({ stage: S[i], state })) } },
    { name: 'empty', summary: 'An unresolved pipeline renders no marks and is not an error.', props: { dots: [] } },
  ],
})
```

- [ ] **Step 3: Write the failing Vitest logic spec**

```ts
// interfaces/ui/src/components/stage_dots/stage_dots.spec.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StageDots from './StageDots.vue'

const dots = (...states: string[]) => states.map((state, i) => ({ stage: `s${i}`, state }))

describe('StageDots', () => {
  it('renders one mark per stage in supplied order', () => {  // clause: STAGE_DOTS-1
    const w = mount(StageDots, { props: { dots: dots('done', 'active', 'pending') } })
    const marks = w.findAll('[data-testid="stage-dot"]')
    expect(marks).toHaveLength(3)
    expect(marks[0].classes()).toContain('cmp-stage-dot-done')
    expect(marks[2].classes()).toContain('cmp-stage-dot-pending')
  })

  it('renders nothing for an empty stage list', () => {  // clause: STAGE_DOTS-1.1
    const w = mount(StageDots, { props: { dots: [] } })
    expect(w.findAll('[data-testid="stage-dot"]')).toHaveLength(0)
  })

  it('fails rendering on an unknown state', () => {  // clause: STAGE_DOTS-1.2
    expect(() => mount(StageDots, { props: { dots: dots('sideways') } })).toThrow(/sideways/)
  })

  it('titles each mark with its stage and state', () => {  // clause: STAGE_DOTS-4
    const w = mount(StageDots, { props: { dots: [{ stage: 'qa', state: 'active' }] } })
    expect(w.find('[data-testid="stage-dot"]').attributes('title')).toBe('qa · active')
  })
})
```

- [ ] **Step 4: Run it to verify it fails**

Run: `npm run test --workspace @kroker/ui`
Expected: FAIL — `StageDots.vue` does not exist.

- [ ] **Step 5: Write the component**

```vue
<!-- interfaces/ui/src/components/stage_dots/StageDots.vue -->
<script setup lang="ts">
import { computed } from 'vue'

export type DotState = 'pending' | 'active' | 'done' | 'blocked' | 'failed' | 'skipped'
export interface StageDot { stage: string; state: DotState }

const STATES: readonly string[] = ['pending', 'active', 'done', 'blocked', 'failed', 'skipped']

const props = defineProps<{ dots: StageDot[] }>()

// STAGE_DOTS-1.2: an unknown state is a product fault, not a default.
const marks = computed(() =>
  props.dots.map((d) => {
    if (!STATES.includes(d.state)) {
      throw new Error(`StageDots: unknown state "${d.state}" for stage "${d.stage}"`)
    }
    return { ...d, title: `${d.stage} · ${d.state}` }
  }),
)
</script>

<template>
  <span class="cmp-stage-dots">
    <span
      v-for="m in marks"
      :key="m.stage"
      data-testid="stage-dot"
      class="cmp-stage-dot"
      :class="`cmp-stage-dot-${m.state}`"
      :title="m.title"
    />
  </span>
</template>

<style scoped>
.cmp-stage-dots { display: flex; gap: 3px; }
.cmp-stage-dot { width: 9px; height: 9px; border-radius: 2px; }
</style>
```

Colours are deliberately absent here — they arrive with the token pass in Task 7, keyed off `cmp-stage-dot-<state>`.

- [ ] **Step 6: Run the logic tier**

Run: `npm run test --workspace @kroker/ui`
Expected: 4 passed.

- [ ] **Step 7: Write the Playwright presentation spec**

```ts
// interfaces/ui/src/components/stage_dots/stage_dots.pw.ts
import { test, expect } from '@playwright/test'

const at = (profile: string) => `#showcase-stage_dots-${profile}`

test('each state carries its stable class', async ({ page }) => {  // clause: STAGE_DOTS-2
  await page.goto('/')
  const marks = page.locator(`${at('every-state')} [data-testid="stage-dot"]`)
  await expect(marks).toHaveCount(6)
  for (const state of ['pending', 'active', 'done', 'blocked', 'failed', 'skipped']) {
    await expect(page.locator(`${at('every-state')} .cmp-stage-dot-${state}`)).toHaveCount(1)
  }
})

test('only active and blocked animate', async ({ page }) => {  // clause: STAGE_DOTS-3
  await page.goto('/')
  const animated = async (sel: string) =>
    page.locator(sel).evaluate((el) => getComputedStyle(el).animationName)
  // Asserts that an animation resolves, never which colour or duration.
  expect(await animated(`${at('every-state')} .cmp-stage-dot-active`)).not.toBe('none')
  expect(await animated(`${at('every-state')} .cmp-stage-dot-blocked`)).not.toBe('none')
  expect(await animated(`${at('every-state')} .cmp-stage-dot-done`)).toBe('none')
})

test('an unresolved pipeline renders no marks', async ({ page }) => {  // clause: STAGE_DOTS-1.1
  await page.goto('/')
  await expect(page.locator(`${at('empty')} [data-testid="stage-dot"]`)).toHaveCount(0)
})
```

- [ ] **Step 8: Register the profiles and run the browser tier**

Add the profile set to `showcase/registry.ts`, then:

Run: `npm run test:pw --workspace @kroker/ui`
Expected: 3 passed.

- [ ] **Step 9: Repoint the dashboard and delete the old component**

In `FleetRow.vue`, replace the local import with `import StageDots from '@kroker/ui/components/stage_dots/StageDots.vue'`, and pass an adapted `dots` array. Delete `src/components/fleet/StageDots.vue`.

Run: `npm run test --workspace sdlc-dashboard`
Expected: `FleetTable.test.ts`'s "renders 14 stage dots per row" still passes.

- [ ] **Step 10: Commit**

```bash
git add -A interfaces
git commit -m "feat(ui): migrate StageDots with its contract and both test tiers

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe"
```

---

### Task 6: Extend `check_clauses.py` to `interfaces/`, and add the component template

**Files:**
- Modify: `scripts/check_clauses.py:40-52`
- Create: `docs/templates/component.md`
- Test: `tests/test_check_clauses_ui.py`

**Interfaces:**
- Consumes: `stage_dots.md` and its two spec files from Task 5 as live fixtures.
- Produces: an advisory report covering UI clauses alongside stage clauses.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_clauses_ui.py
"""The clause report reaches the UI tree (spec C §4)."""

import pathlib

from scripts.check_clauses import UI_MARKER, clause_ids_in_doc, clause_ids_in_ui_tests, is_scannable


def test_finds_the_stage_dots_clauses():
    doc = pathlib.Path("interfaces/ui/src/components/stage_dots/stage_dots.md")
    assert "STAGE_DOTS-1.2" in clause_ids_in_doc(doc)


def test_finds_a_same_line_citation():
    assert UI_MARKER.findall("  it('x', () => {})  // clause: STAGE_DOTS-2") == ["STAGE_DOTS-2"]


def test_ignores_node_modules_and_build_output():
    assert not is_scannable(pathlib.Path("interfaces/ui/node_modules/pkg/readme.md"))
    assert not is_scannable(pathlib.Path("interfaces/ui/dist-ds/stage_dots/empty.html"))
    assert is_scannable(pathlib.Path("interfaces/ui/src/components/stage_dots/stage_dots.md"))


def test_ui_clauses_are_cited_somewhere():
    declared = clause_ids_in_doc(
        pathlib.Path("interfaces/ui/src/components/stage_dots/stage_dots.md")
    )
    cited = clause_ids_in_ui_tests(pathlib.Path("interfaces"))
    assert declared - cited == set(), f"uncited UI clauses: {sorted(declared - cited)}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_check_clauses_ui.py -v`
Expected: FAIL — `ImportError: cannot import name 'UI_MARKER'`.

- [ ] **Step 3: Extend the scanner**

Add beside the existing `HEADING` and `MARKER` in `scripts/check_clauses.py`:

```python
UI_MARKER = re.compile(r"//\s*clause:\s*([A-Z][A-Z0-9_]*-\d+(?:\.\d+)*)")

# rglob would otherwise walk an installed dependency tree and the generated
# preview bundle, which contain neither clauses nor citations.
_SKIP = {"node_modules", "dist", "dist-ds", ".vite", "coverage"}


def is_scannable(path: pathlib.Path) -> bool:
    return not any(part in _SKIP for part in path.parts)


def clause_ids_in_ui_tests(root: pathlib.Path) -> set[str]:
    ids: set[str] = set()
    for pattern in ("*.spec.ts", "*.pw.ts"):
        for p in root.rglob(pattern):
            if is_scannable(p):
                ids |= set(UI_MARKER.findall(p.read_text(encoding="utf-8")))
    return ids
```

And in `main()`, after the existing `src/sdlc/stages` loop:

```python
    for doc in pathlib.Path("interfaces").rglob("*.md"):
        if doc.name != "AGENTS.md" and is_scannable(doc):
            declared |= clause_ids_in_doc(doc)

    cited = clause_ids_in_tests(pathlib.Path("tests")) | clause_ids_in_ui_tests(
        pathlib.Path("interfaces")
    )
    untested, dangling = orphans(declared, cited)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_check_clauses_ui.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the report and confirm it still exits 0**

Run: `python scripts/check_clauses.py; echo "exit=$?"`
Expected: the report lists the `STAGE_DOTS-*` clauses as covered, and `exit=0` regardless of orphans.

- [ ] **Step 6: Write `docs/templates/component.md`**

Mirror `docs/templates/stage.md`'s shape: a paragraph on what the component does, a paragraph on what the caller owns versus what the component owns, a `## Requirements` section of `<COMPONENT>-N` clauses with anchors, and a `## Failure modes` section. Include an explicit note that identifiers use underscores.

- [ ] **Step 7: Commit**

```bash
git add scripts/check_clauses.py tests/test_check_clauses_ui.py docs/templates/component.md
git commit -m "feat(clauses): extend the advisory report to interfaces/

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe"
```

---

## Phase 4 — Tokens and the remaining components

### Task 7: The mechanical token pass

**Files:**
- Create: `interfaces/ui/src/tokens/tokens.css`, `interfaces/ui/src/tokens/tokens.md`
- Modify: every `<style scoped>` block in `interfaces/dashboard/frontend/src/`, `src/styles/theme.css`
- Test: `interfaces/ui/src/tokens/tokens.pw.ts`

**Interfaces:**
- Produces: `--c-<hex>` variables plus `--font-sans` / `--font-mono`. Names are deliberately non-semantic; Task 16 renames them from the canvas.

- [ ] **Step 1: Write `tokens.css`**

```css
/* interfaces/ui/src/tokens/tokens.css
 *
 * Pass one is mechanical (spec C §5). Names encode values, not meaning:
 * this palette accreted and was never designed, so inventing a semantic
 * taxonomy now means inventing it twice — once here and once when the
 * canvas brings its own. What this pass buys is the wiring, which
 * survives the restyle untouched.
 */
:root {
  --c-0c0f14: #0c0f14;  --c-090b0f: #090b0f;  --c-151a23: #151a23;
  --c-171c25: #171c25;  --c-1e242f: #1e242f;  --c-2a3140: #2a3140;
  --c-d9dfe9: #d9dfe9;  --c-e8edf5: #e8edf5;  --c-c8cfdb: #c8cfdb;
  --c-9db4d8: #9db4d8;  --c-8a93a5: #8a93a5;  --c-7d8697: #7d8697;
  --c-5d6675: #5d6675;

  --status-running: #5b9dd9;   --status-blocked: #e0b050;
  --status-failed: #e06c55;    --status-done: #4fae7f;
  --status-quarantined: #b98fdc;
  --status-pending: #2a3140;   --status-skipped: #1b202b;

  --font-sans: 'IBM Plex Sans', sans-serif;
  --font-mono: 'IBM Plex Mono', monospace;
}
```

- [ ] **Step 2: Write the failing presentation test**

```ts
// interfaces/ui/src/tokens/tokens.pw.ts
import { test, expect } from '@playwright/test'

// Asserts that tokens RESOLVE, never what they resolve to. A suite that
// pinned the old palette would burn down in Task 16 (spec C §5).
test('every declared token resolves to a non-empty value', async ({ page }) => {  // clause: TOKENS-1
  await page.goto('/')
  const unresolved = await page.evaluate(() => {
    const s = getComputedStyle(document.documentElement)
    const names = Array.from(document.styleSheets)
      .flatMap((sh) => Array.from((sh as CSSStyleSheet).cssRules ?? []))
      .filter((r): r is CSSStyleRule => r instanceof CSSStyleRule && r.selectorText === ':root')
      .flatMap((r) => Array.from(r.style).filter((p) => p.startsWith('--')))
    return names.filter((n) => s.getPropertyValue(n).trim() === '')
  })
  expect(unresolved).toEqual([])
})

test('no component ships a bare hex literal', async ({ page }) => {  // clause: TOKENS-2
  await page.goto('/')
  const offenders = await page.evaluate(() =>
    Array.from(document.styleSheets)
      .flatMap((sh) => Array.from((sh as CSSStyleSheet).cssRules ?? []))
      .filter((r): r is CSSStyleRule => r instanceof CSSStyleRule)
      .filter((r) => r.selectorText !== ':root' && /#[0-9a-f]{3,8}\b/i.test(r.style.cssText))
      .map((r) => r.selectorText),
  )
  expect(offenders).toEqual([])
})
```

- [ ] **Step 3: Run it to verify it fails**

Run: `npm run test:pw --workspace @kroker/ui`
Expected: `TOKENS-2` FAILS, listing every selector still holding a literal.

- [ ] **Step 4: Replace the literals**

Work file by file through `interfaces/dashboard/frontend/src/`, replacing each hex with its `var(--c-<hex>)`, and each `'IBM Plex Sans'` / `'IBM Plex Mono'` with `var(--font-sans)` / `var(--font-mono)` — 23 font references and 13 colours. Import `tokens.css` from `src/main.ts` before `theme.css`. Move the two `@keyframes` out of `theme.css` into the components that use them.

- [ ] **Step 5: Re-run until green**

Run: `npm run test:pw --workspace @kroker/ui`
Expected: both tests pass, offender list empty.

- [ ] **Step 6: Confirm nothing moved visually**

Run: `npm run dev --workspace sdlc-dashboard`, and compare against the pre-change console.
Expected: identical. This is the whole point of phases 1–6.

- [ ] **Step 7: Write `tokens.md`** with `TOKENS-1` (every token resolves) and `TOKENS-2` (no literal outside `tokens.css`), anchored to FR-1404, and commit.

---

### Task 8: `STATUS_COLORS` becomes a stable class per kind

**Files:**
- Modify: `interfaces/dashboard/frontend/src/constants.ts:37-45`, `src/composables/status.ts`, `src/components/fleet/FleetRow.vue:21`
- Create: `interfaces/ui/src/components/status_pip/{status_pip.md,status_pip.profiles.ts,status_pip.spec.ts,status_pip.pw.ts}`

- [ ] **Step 1: Write the failing spec** asserting `FleetRow` renders `.cmp-status-pip-blocked` and carries **no** inline `style` attribute on the pip.
- [ ] **Step 2: Run it** — FAILS, since the pip is `:style`-bound today.
- [ ] **Step 3: Add the class rules to `tokens.css`**, one `.cmp-status-pip-<kind>` per status, each `background: var(--status-<kind>)`.
- [ ] **Step 4: Replace the binding** in `FleetRow.vue` with the `StatusPip` component from Task 2, passing `kind`. Reduce `STATUS_COLORS` to a `STATUS_KINDS` list; the colours now live only in `tokens.css`.
- [ ] **Step 5: Run both tiers** — `npm run test --workspace sdlc-dashboard` and `npm run test:pw --workspace @kroker/ui`. Expected: pass, and `constants.test.ts` updated to assert kinds rather than hexes.
- [ ] **Step 6: Write `status_pip.md`** with `STATUS_PIP-1` (one mark per kind, stable class), `STATUS_PIP-2` (only `running` and `blocked` pulse), anchored to FR-1404. Commit.

---

### Task 9: Migrate `FleetRow` and `FleetTable`

Follow Task 5's shape exactly, per component: contract, profiles, Vitest spec, Playwright spec, repoint, delete the old file, commit.

- [ ] **Step 1:** `fleet_row.md` — clauses `FLEET_ROW-1` (renders every supplied field in column order), `FLEET_ROW-1.1` (a null cost renders as an em dash, never `0.00` — the backend distinguishes them, `http.ts:72`), `FLEET_ROW-2` (the whole row is one link to the supplied destination), `FLEET_ROW-3` (a long title truncates while the marks keep their column — the reference project's "Crowded trail" profile).
- [ ] **Step 2:** Profiles: `typical`, `null-cost`, `crowded-trail`, `blocked-at-gate`, `terminal-failed`.
- [ ] **Step 3–6:** Failing spec, run, implement with props `{ id, title, mode, dots, status, blocker, cost, age, href }`, run.
- [ ] **Step 7:** `fleet_table.md` — `FLEET_TABLE-1` (one row per supplied run, in supplied order), `FLEET_TABLE-1.1` (an empty fleet renders the header and an explicit empty state, not a bare header).
- [ ] **Step 8:** Repoint `FleetView.vue`, run both tiers, commit.

---

### Task 10: Migrate `AppHeader`, `Toasts`, `StartRunModal`

These three read Pinia stores directly (`AppHeader.vue:3-5`), which is the domain leak §2 forbids. Each becomes presentational, and the dashboard keeps a thin wrapper that reads the store and passes props.

- [ ] **Step 1:** `app_header.md` — `APP_HEADER-1` (renders brand, tabs, and supplied stats), `APP_HEADER-1.1` (the inbox badge is absent at zero, not rendered as "0"), `APP_HEADER-2` (the active tab carries a stable class).
- [ ] **Step 2:** `toasts.md` — `TOASTS-1` (renders every supplied toast in order), `TOASTS-1.1` (an empty list renders nothing at all).
- [ ] **Step 3:** `start_run_modal.md` — `START_RUN_MODAL-1` (emits `submit` with the supplied shape), `START_RUN_MODAL-1.1` (submit is disabled while any required field is empty), `START_RUN_MODAL-2` (open state is caller-owned; the component never closes itself).
- [ ] **Step 4:** For each: profiles, both tiers, repoint, delete, commit.

---

### Task 11: The dashboard adapter layer

**Files:**
- Create: `interfaces/dashboard/frontend/src/adapters/{fleet.ts,inbox.ts,fleet.test.ts}`

- [ ] **Step 1: Write the failing test** for `toFleetRow(run: Run): FleetRowProps` and `toStageDots(run: Run): StageDot[]`, asserting a null cost survives as `null` and that `stageIdx` becomes the correct per-stage state array.
- [ ] **Step 2: Run it** — FAILS.
- [ ] **Step 3: Implement**, moving the logic out of `composables/stageState.ts` and `composables/status.ts`.
- [ ] **Step 4: Assert the ownership rule holds.** Add a test that greps `interfaces/ui/src` for `from '../../dashboard` and `api/types`, asserting zero matches. This is the mechanical form of spec §2.
- [ ] **Step 5:** Run `python scripts/check_ui.py`, expect green, commit.

---

## Phase 5 — The Claude Design bundle

### Task 12: `build-ds-bundle.ts`

**Files:**
- Create: `interfaces/ui/scripts/build-ds-bundle.ts`
- Modify: `interfaces/ui/package.json` (add `"ds:bundle"`)

**Interfaces:**
- Consumes: the showcase and every registered profile set.
- Produces: `interfaces/ui/dist-ds/<component>/<profile>.html`, each with `<!-- @dsCard ... -->` as its literal first line.

- [ ] **Step 1: Write the builder**

```ts
// interfaces/ui/scripts/build-ds-bundle.ts
import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { REGISTRY } from '../showcase/registry'
import { profileId } from '../src/profile'

const OUT = 'dist-ds'
const BASE = process.env.SHOWCASE_URL ?? 'http://localhost:4173'

const browser = await chromium.launch()
const page = await browser.newPage()
await page.goto(BASE)

// One stylesheet for the whole bundle: every profile shares the showcase's
// CSS, so serializing it once per file keeps each preview standalone.
const css: string = await page.evaluate(() =>
  Array.from(document.styleSheets)
    .flatMap((sh) => {
      try {
        return Array.from((sh as CSSStyleSheet).cssRules).map((r) => r.cssText)
      } catch {
        return []  // cross-origin (the Google Fonts sheet); linked below instead
      }
    })
    .join('\n'),
)

for (const set of REGISTRY) {
  for (const p of set.profiles) {
    const html: string = await page
      .locator(`#${profileId(set.component, p.name)} .showcase-stage`)
      .innerHTML()

    // The marker MUST be the literal first line: the Design System pane
    // reads it there, and bundlers strip leading comments, so it is
    // prepended after serialization rather than authored into a template.
    const doc = [
      `<!-- @dsCard group="${set.group}" -->`,
      '<!doctype html>',
      '<meta charset="utf-8">',
      `<title>${set.component} / ${p.name}</title>`,
      '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">',
      `<style>${css}</style>`,
      `<body>${html}</body>`,
    ].join('\n')

    const out = join(OUT, set.component, `${p.name}.html`)
    await mkdir(dirname(out), { recursive: true })
    await writeFile(out, doc, 'utf8')
    console.log(`wrote ${out}`)
  }
}

await browser.close()
```

- [ ] **Step 2: Write the failing test**

```ts
// interfaces/ui/scripts/build-ds-bundle.spec.ts
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'

const f = 'dist-ds/stage_dots/every-state.html'

describe('the ds bundle', () => {
  it('emits one file per profile', () => {  // clause: DS_BUNDLE-1
    expect(existsSync(f)).toBe(true)
  })

  it('puts the dsCard marker on the literal first line', () => {  // clause: DS_BUNDLE-2
    const first = readFileSync(f, 'utf8').split('\n')[0]
    expect(first).toMatch(/^<!-- @dsCard group="[^"]+" -->$/)
  })

  it('inlines the styles so a preview stands alone', () => {  // clause: DS_BUNDLE-3
    expect(readFileSync(f, 'utf8')).toContain('.cmp-stage-dot')
  })
})
```

- [ ] **Step 3: Run the builder, then the test**

Run: `npm run build --workspace @kroker/ui && npm run preview --workspace @kroker/ui &` then `npm run ds:bundle --workspace @kroker/ui`, then the spec.
Expected: 3 passed.

- [ ] **Step 4: Write `ds_bundle.md`** with `DS_BUNDLE-1/2/3` anchored to FR-1405. Commit.

**Note on scope risk:** spec C names this the largest unknown. If style faithfulness (pseudo-elements, keyframes, webfont metrics) costs more than a day, stop at "structurally faithful" and record the gap in the component's `.md` rather than expanding the task.

---

### Task 13 — ORCHESTRATOR-RUN: push the previews (spec §10, O-1)

> **This task cannot run in a coding pane.** `DesignSync` lives in the orchestrator session. The steps below are written to be executed verbatim there.

- [ ] **Step 1:** `DesignSync` `method: "list_projects"`. Record the `projectId` of the intended target, or `method: "create_project"` with `name: "Kroker Factory Console"` if none exists.
- [ ] **Step 2:** `DesignSync` `method: "get_project"` with that `projectId`. **Confirm `type` is `PROJECT_TYPE_DESIGN_SYSTEM`.** The type is immutable at creation; pushing to a regular project never makes it a design system.
- [ ] **Step 3:** `DesignSync` `method: "finalize_plan"` with:
  - `projectId`: from Step 1
  - `localDir`: `D:\own\Kroker\interfaces\ui\dist-ds`
  - `writes`: `["stage_dots/**/*.html", "status_pip/**/*.html", "fleet_row/**/*.html", "fleet_table/**/*.html", "app_header/**/*.html", "toasts/**/*.html", "start_run_modal/**/*.html"]`
- [ ] **Step 4:** `DesignSync` `method: "write_files"` with the returned `planId` and one entry per generated file, each `{ path: "<component>/<profile>.html", localPath: "<component>/<profile>.html" }`.
- [ ] **Step 5:** Do **not** call `register_assets`. Cards are built from the `@dsCard` markers Task 12 emits.
- [ ] **Step 6:** Confirm with `method: "list_files"` that every expected path landed.

---

## Phase 6 — The live provider

### Task 14: Flip the `VITE_API` default and correct the README

**Files:**
- Modify: `interfaces/dashboard/frontend/src/api/client.ts:9`, `interfaces/dashboard/frontend/README.md`
- Create: `interfaces/ui/app.pw.ts`

- [ ] **Step 1: Write the failing test** asserting `selectApi` defaults to the HTTP provider when `VITE_API` is unset, and still returns the mock when it is `'mock'`.
- [ ] **Step 2: Run it** — FAILS.
- [ ] **Step 3: Flip the default**

```ts
export const api: DashboardApi = selectApi(import.meta.env.VITE_API === 'mock' ? 'mock' : 'http')
```

- [ ] **Step 4: Correct the README.** Delete the "reserved for the future FastAPI provider (`src/api/http.ts`, not yet wired)" paragraph and the "When the FastAPI provider lands" paragraph — `http.ts` has been complete since E-10 and `ROADMAP.md:279` records FR-601 as closed. Replace with: `http` is the default; `VITE_API=mock` selects the in-memory provider, which is what the showcase and the Playwright app tier run on.
- [ ] **Step 5: Add the app tier.** `interfaces/ui/app.pw.ts` runs the real SPA on `VITE_API=mock` and asserts the Fleet view renders rows, the Inbox badge appears, and the header stats render — clauses `CONSOLE-1`, `CONSOLE-2`. A net over the showcase alone misses the pages that ship (spec §6).
- [ ] **Step 6:** Run `python scripts/check_ui.py`, expect green. Commit.

---

## Phase 7 — The restyle

### Task 15 — ORCHESTRATOR-RUN: land the canvas (spec §10, O-2)

> **This task cannot run in a coding pane.**

- [ ] **Step 1:** In Claude Design, author a canvas for the console, using the previews pushed in Task 13 as the current state.
- [ ] **Step 2:** Export it and save **verbatim** to `records/2026-09-05-console-restyle/`: the `<Name>.dc.html` plus the `support.js` it loads. Do not edit either file, ever.
- [ ] **Step 3:** Confirm the directory contains only those files (plus a `.thumbnail` if the export emits one), matching `records/2026-07-12-factory-console/`'s shape.
- [ ] **Step 4:** Commit the record on its own, with no code changes in the same diff.

---

### Task 16: The semantic token rename and the restyle

**Files:**
- Modify: `interfaces/ui/src/tokens/tokens.css`, `tokens.md`, every component `.css`/`<style>` block
- Modify: `ROADMAP.md` (the FR-1400 block entries), `ARCHITECTURE.md` if the tree description changes

- [ ] **Step 1: Extract the taxonomy from the canvas** into `tokens.css`, replacing the `--c-<hex>` names with the canvas's semantic names and values.
- [ ] **Step 2: Rename every reference.** Mechanical, one name at a time; the wiring from Task 7 is what makes this a rename rather than a rewrite.
- [ ] **Step 3: Run both tiers.** `python scripts/check_ui.py`.
  Expected: **green without edits to any spec.** Every assertion from phases 3–6 was written against structure, stable classes and token resolution, never against a hex or a pixel. If a spec fails here, it was written wrong and the spec is the bug — not the restyle.
- [ ] **Step 4: Re-run the bundle and re-push** (Task 12 build, Task 13 steps 3–6) so the design system reflects the landed restyle.
- [ ] **Step 5: Update `ROADMAP.md`** with the FR-1400 block and E-89, now that the code satisfying them is on `main`. Update `docs/documentation-rules.md`'s "what lives where" table with `interfaces/ui/`'s component contracts.
- [ ] **Step 6: Update `tokens.md`** clauses to the semantic names. Commit.

---

## Self-Review

**Spec coverage.** §1 target tree → Tasks 1, 2, 4. §2 ownership → Tasks 2, 11 (step 4 is the mechanical check). §3 profile → Task 4. §4 clause scheme → Tasks 5, 6. §5 tokens, both passes → Tasks 7, 8, 16. §6 two tiers → Tasks 5, 14 (app tier). §7 the loop → Tasks 12, 13, 15. §8 http provider → Task 14. §9 CI and verify → Task 3. §10 orchestrator steps → Tasks 13, 15. §11 clauses → declared across component `.md` files, ROADMAP entries in Task 16 step 5. §12 deliverables 1–11 → all mapped; deliverable 11 is Task 1.

**Known thinness, stated rather than hidden.** Tasks 9 and 10 give clause lists and profile names but not full component source, because they repeat Task 5's shape exactly and reproducing five near-identical 120-line components would obscure what differs. An executor should read Task 5 as the worked example before starting either. Task 8's steps 3–5 and Task 11 are likewise compressed against Task 5's pattern.

**Type consistency.** `StageDot`/`DotState` defined in Task 5 and consumed by name in Task 11. `Profile`/`ProfileSet`/`defineProfiles`/`profileId` defined in Task 4, used in Tasks 5, 12. `STEPS`/`main` defined in Task 3, imported by `tests/test_check_ui.py`. `UI_MARKER`/`is_scannable`/`clause_ids_in_ui_tests` defined in Task 6, imported by its test. `FleetRowProps`/`toFleetRow` introduced in Task 11 and consumed by Task 9's repoint step.
