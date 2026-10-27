# CommandPalette Component

The ⌘K command palette. A pure overlay: the app supplies the command
list and runs what the user picks; the palette owns filtering, the
keyboard highlight and closing.

## Requirements

### COMMAND_PALETTE-1
With `open: false` the palette renders nothing at all — no backdrop, no
commands. [US8, FR-053]

### COMMAND_PALETTE-2
With `open: true` every command renders with its label and, when set,
its hint.

### COMMAND_PALETTE-3
Typing filters commands by label, case-insensitively; a filter that
matches nothing renders zero commands, and Enter then runs nothing. A
new filter resets the highlight to the first match.

### COMMAND_PALETTE-4
ArrowDown and ArrowUp move the highlight and clamp at the ends (no
wrap); Enter emits `run(id)` with the highlighted command's id.

### COMMAND_PALETTE-5
Escape and a backdrop click each emit `close`.

## Failure modes

An empty hint or description renders as nothing, never the string
`undefined`.
