# Field Component

Renders one labelled text input: a gate comment, a clarify answer, a merge
override justification, escalation guidance. The caller owns the value, the
validation rule and the error text; the component owns the label, the control,
the note line, and the accessible wiring between them.

## Requirements

### FIELD-1
The label is bound to the control (`for`/`id`), so clicking the label focuses
the control and assistive tech announces it. [FR-1400]

### FIELD-2
With an `error`, the field carries `is-invalid`, the control carries
`aria-invalid="true"`, and the error renders with `role="alert"` and is
referenced by `aria-describedby`. [FR-1400]

### FIELD-3
With no error, a `hint` renders in the same place; an error replaces the hint,
never stacks under it. [FR-1400]

### FIELD-4
Typing emits `update:modelValue` with the raw value; the component never trims
or validates. [FR-1400]

## Failure modes

Validation is caller-owned: a required field that is blank shows no error until
the caller passes one (the inbox passes it on submit, not on blur).
