# Context Stage

The context stage performs brownfield codebase mapping (Stage 2 / E-84) to ground downstream
architecture and planning proposals in the real repository structure. It runs thirteen static
scan signals over the repository tree at the pinned integration head commit, projects them into
a `CodebaseMap` (modules, contracts, and hot spots), and verifies that collection was measured
(fail-closed per FR-915).

The orchestrator (`FeatureWorkflow._pipeline`) coordinates setup of the integration branch and
passes the pinned commit SHA to `context.step`. Greenfield runs bypass context mapping completely.
Downstream architecture proposals use the resulting `CodebaseMap` and verify architecture deltas
against the repository tree via `check_brownfield_delta`.

## Requirements

### CONTEXT-1.1
The context step receives a `StageContext` protocol and required collaborators as keyword
arguments, and never receives the workflow instance or calls a gate directly. The slice exports
`step`, `build_map`, `prompt_digest`, and `ACTIVITIES = [classify_repo, check_brownfield_delta]`. [FR-101, E-84]

### CONTEXT-1.2
When `idea.mode` is not `ProjectMode.BROWNFIELD` (e.g. `GREENFIELD`), the context step immediately
short-circuits and returns `None` without invoking scan signals or mapping activities. [E-84 D13]

### CONTEXT-1.3
In brownfield mode, the context step records stage progress (`mapping`, `context`), runs the thirteen
static scan signals over the repository tree at the pinned commit, and projects the results into
a `CodebaseMap`. [E-84 D1/D4/D5]

### CONTEXT-1.4
If signal collection fails to produce a measured state (`codebase_map.collected.state is not CollectionState.MEASURED`),
the context step fails closed and returns a structured rejection string (`rejected:context (<reason>)`),
preventing ungrounded proposals when measurements are missing or corrupt. [FR-915, E-84 D6]

### CONTEXT-1.5
The context slice owns and exports repository probe and delta grounding activities (`classify_repo`
and `check_brownfield_delta`), ensuring downstream stages verify proposed filesystem deltas against
the pinned repository tree. [E-84 D3/D8]

## Failure modes

- **Unmeasured scan signals**: A scan activity times out or errors, leaving `collected.state` unmeasured; fails closed with rejection string.
- **Malformed SARIF or tool output**: Signal output cannot be parsed into measured data; rejected fail-closed to avoid false-clean passes.
- **Delta mismatch**: Architecture proposals referencing non-existent files to modify or already-existing files to add fail the `check_brownfield_delta` activity check.
