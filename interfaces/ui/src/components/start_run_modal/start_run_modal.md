# Start Run Modal Component

Renders a modal dialogue for configuring and launching a new feature pipeline run.
The caller owns modal visibility state, form persistence, API dispatch, and toast triggering;
the component owns the modal card presentation, backdrop overlay, input bindings, mode toggle buttons, and disabled submission state.

## Requirements

### START_RUN_MODAL-1
A Start Run Modal emits `submit` with `{ title, repo, mode }` upon submission. [FR-1400]

### START_RUN_MODAL-1.1
The submit button is disabled and submission is blocked while any required field is empty. [FR-1400]

### START_RUN_MODAL-2
The open state is caller-owned; the component never alters its own open state and emits `close` on backdrop or cancel click. [FR-1400]

## Failure modes

When `open` is false, nothing is rendered. When required inputs are whitespace only, submission is disabled.
