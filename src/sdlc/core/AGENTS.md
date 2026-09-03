# core/ — the shared kernel

**Rule 5, the layering invariant:** `core/` imports nothing from `stages/`
and nothing from any horizontal package (`harness/`, `memory/`, `board/`,
`schedules/`, `measurement.py`). Anything a `core/` type references is
itself in `core/`.

Check it:

    grep -rnE "from \.\.(stages|harness|memory|board|schedules)" src/sdlc/core/

Empty output is the pass condition. A non-empty result is a boot-time
circular-import defect waiting to happen, not a style nit — every slice
imports `core`.

Two rules exist only to keep Rule 5 satisfiable:
- **Rule 6** — a bare enum (no model dependencies) that a `core/` type
  references lives here. That is why `HarnessKind` and
  `ClarificationDimension` are here rather than with the harness and the
  clarify slice.
- **Rule 7** — an envelope aggregating *stage artifacts* does NOT live here.
  It goes to `workflows/models.py`, beside the orchestrator that assembles
  it. That is why `TaskResult` and `SeededWork` are not here.
