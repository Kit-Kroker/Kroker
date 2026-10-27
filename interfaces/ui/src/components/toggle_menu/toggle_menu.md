# ToggleMenu Component

The ⋯ display menu: a vertical list of session toggles. The app owns
the toggle state; the menu shows each item's label and description and
a check when the item is on.

## Requirements

### TOGGLE_MENU-1
Each item renders its label and, when set, its description. [US8, FR-053]

### TOGGLE_MENU-2
A check shows on items that are on, and only on those.

### TOGGLE_MENU-3
Clicking an item emits `toggle(id)` with that item's id, once per click,
in click order.

## Failure modes

An empty description renders as nothing, never the string `undefined`.
