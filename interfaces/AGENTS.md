# interfaces/ — AGENTS.md

Router only. Deep context lives in each sub-package.

## Tree layout

Two packages:

- **`ui/`** — the `@kroker/ui` design-system package. Presentation components
  that accept display primitives and know nothing of Kroker's domain. Source
  exports only; no `dist/`, no compiled declarations.
- **`dashboard/frontend/`** — the `sdlc-dashboard` npm package. Consumes
  `@kroker/ui`. Contains domain adapters (`src/adapters/`) that map `Run` and
  `InboxItem` to display primitives, and every Pinia store.

## The cardinal rule

**`ui/` must never import from `dashboard/`.** If a component's props cannot
be constructed as a literal (with no import from `dashboard/`), a domain type
has leaked into the component and must be removed. The adapter layer in
`dashboard/frontend/src/adapters/` is where the boundary is maintained.

## Node toolchain

The single entry point for every JavaScript check is:

```
python scripts/check_ui.py
```

Do not invoke `npm`, `npx`, `vitest`, or `playwright` directly in CI or in
`scripts/verify.py`. The wrapper handles install, typecheck, both Vitest
workspaces, and both Playwright tiers — including the Windows detail that
`npm` is `npm.cmd`.

## File-size ceiling

The 1000-line ceiling already covers `interfaces/` via `scripts/check_file_size.py`.
No change to that script is needed; no file in this tree may exceed 1000 lines.

## Component contracts

Each component carries its own clause document at
`ui/src/components/<name>/<name>.md`. Those documents are **not** inlined
here. Read the component directory for its contract.
