# Segmented Control Component

Renders two to five mutually exclusive options as one control: Observe / Design,
Path / Events, Tasks / Artifacts / Events. The caller owns the selected value
and what switching means; the component owns the selected treatment and the
radio semantics.

Use it for switching the view of one thing. For filtering a list use Filter
Chip; for navigating between pages use Tab Bar.

## Requirements

### SEGMENTED_CONTROL-1
Exactly the option whose value equals `modelValue` carries `is-selected`
and `aria-checked="true"`; every other option carries `aria-checked="false"`. [FR-1400]

### SEGMENTED_CONTROL-2
Pressing an unselected option emits `update:modelValue` with its value;
pressing the selected option emits nothing. [FR-1400]

### SEGMENTED_CONTROL-3
An option's count renders when it is defined, including `0`, and is absent
when undefined. [FR-1400]

## Failure modes

A `modelValue` matching no option renders every option unselected.
