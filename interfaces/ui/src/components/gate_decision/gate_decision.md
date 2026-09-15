# Gate Decision Component

Renders the approve / revise / reject controls for one pending human gate,
with a comment. The caller owns which gate is pending, the decision key, the
API call, and the busy state while a decision is in flight; the component
owns the controls and the revise-needs-a-comment affordance.

## Requirements

### GATE_DECISION-1
A Gate Decision emits `decide` with `{ outcome, comment }` for the pressed
outcome, the comment trimmed. [FR-1205]

### GATE_DECISION-2
Revise is disabled while the comment is blank; approve and reject are not.
This is a UI affordance, not a server guard (E76-OQ-4). [FR-1205]

### GATE_DECISION-3
While `busy` or `disabled`, every control is disabled and no `decide` is
emitted: a decision in flight cannot be submitted twice. [FR-1205]

## Failure modes

A blank revise emits nothing. Busy state is caller-owned; the component
never clears it.
