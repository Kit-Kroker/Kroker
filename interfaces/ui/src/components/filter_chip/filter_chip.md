# Filter Chip Component

Renders one filter a list can be narrowed by: All, In progress, Gates,
Escalations. The caller owns which chips exist, which is selected, and whether
selection is single or multiple; the component owns the pressed treatment and
the optional count.

## Requirements

### FILTER_CHIP-1
A selected chip carries `is-selected` and `aria-pressed="true"`; an
unselected chip carries `aria-pressed="false"`. [FR-1400]

### FILTER_CHIP-2
Pressing an enabled chip emits `select` whether or not it is selected, so the
caller decides between single-select and toggle; a disabled chip emits nothing. [FR-1400]

### FILTER_CHIP-3
The count renders when defined, including `0`, and is absent when undefined. [FR-1400]

## Failure modes

Selection is caller-owned; pressing a chip never changes its own state.
