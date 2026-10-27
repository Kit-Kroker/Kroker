# Footer Bar Component

v5's application footer: one line, a left text and a right text.
The caller owns what the texts say (the fleet spend total on the left
of non-canvas screens, the command hint on the right); the component
owns the bar.

## Requirements

### FOOTER_BAR-1
The footer renders the `left` and `right` texts. An empty string
renders nothing in that slot. [FR-1400]

## Failure modes

Omitting a prop leaves the slot empty; the bar itself always renders.
