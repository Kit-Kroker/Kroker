# Button Component

Renders one action. The caller owns what the action does and when it is busy;
the component owns the four variants, two sizes, and the disabled/busy lock.

Use one `primary` per surface for the action the surface exists for
("Run this version", "Send answer"); `secondary` for the rest; `ghost` for
low-weight actions in dense rows; `danger` for actions that end or discard
work ("Reject", "Abort task").

## Requirements

### BUTTON-1
A Button carries its variant and size as stable classes, `cmp-button-<variant>`
and `cmp-button-<size>`. [FR-1400]

### BUTTON-2
While `disabled` or `busy`, the native button is disabled and no `click` is
emitted; `busy` also sets `aria-busy`. [FR-1400]

### BUTTON-3
A Button renders `type="button"` unless told otherwise, so it never submits an
enclosing form by accident. [FR-1400]

## Failure modes

Busy state is caller-owned; the component never clears it.
