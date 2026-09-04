# Intake Stage

The intake stage performs deterministic verification of the project repository environment
before any downstream analysis or planning begins. It checks repository accessibility, base
branch resolution, and verifies whether the observed repository structure matches the declared
`ProjectMode` (`GREENFIELD` vs `BROWNFIELD`).

The caller (`FeatureWorkflow._pipeline`) coordinates subsequent pipeline stages, setup of the
integration branch, and overall run lifecycle. The intake stage owns repository probing via
`classify_repo`, project mode compatibility classification, warning emissions, and fail-closed
rejections when preconditions are violated.

## Requirements

### INTAKE-1.1
The intake step receives a `StageContext` protocol and required collaborators as keyword
arguments, and never receives the workflow instance or calls a gate directly. [FR-101]

### INTAKE-1.2
The intake step probes repository accessibility and branch resolution deterministically via
`classify_repo` and verifies whether the repository tree matches `idea.mode`. [E-84]

### INTAKE-1.3
When repository observation does not satisfy project mode requirements (e.g. brownfield mode
on a non-git repository or missing base branch), intake fails closed with a structured
rejection string (`rejected:intake (<reason>)`). [E-84]

### INTAKE-1.4
When repository classification produces non-fatal warnings (such as source files present in a
greenfield project declaration), the intake step emits a `STAGE_ENDED` event recording the warning. [E-84]

### INTAKE-1.5
The slice exports `step` and `ACTIVITIES = []`, running as a deterministic activity caller without
direct LLM proposer roles. [FR-101]

## Failure modes

- **Non-git directory**: The specified repository path is not inside a git worktree; fails closed with rejection string.
- **Unresolvable base branch**: The specified base branch does not exist or resolve to a commit; fails closed with rejection string.
- **Unreadable tree**: `git ls-tree` fails on the base commit; fails closed with rejection string.
- **Zero source files in brownfield**: Declared as brownfield but tree contains no recognized source files to map; fails closed.
