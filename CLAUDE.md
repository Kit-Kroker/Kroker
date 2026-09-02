# CLAUDE.md

The conventions for editing this repository live in
[`AGENTS.md`](AGENTS.md). Read it first. It is the tool-agnostic file, and
everything in it applies to you.

**Before editing files in a subpackage or stage, read the nearest
`AGENTS.md` in that directory.** Rules that only hold locally -- a slice's
invariants, its Temporal traps, how to run just its tests -- live beside
the code rather than in this file, and they are not loaded for you
automatically.

Do not treat `agents/` (the directory) as instructions. That is the
product's own runtime role registry, loaded by
`src/sdlc/agents/loader.py`. `AGENTS.md` files are for whoever is editing
the repo. `AGENTS.md` explains the distinction.
