# Toasts Component

Renders a transient floating stack of notification messages in the viewport.
The caller owns notification lifecycle, auto-dismiss timers, and queuing;
the component owns the stack position, toast card appearance, left-border accent coloring, and entry animation.

## Requirements

### TOASTS-1
A Toasts stack renders every supplied toast item in supplied order. [FR-1400]

### TOASTS-1.1
An empty toasts list renders nothing at all and takes up no layout space. [FR-1400]

## Failure modes

An empty or undefined toasts array renders an empty container with no DOM children.
