# Toasts Component

Renders a transient floating stack of notification messages in the viewport.
The caller owns notification lifecycle, auto-dismiss timers, and queuing;
the component owns the stack position, toast card appearance, left-border accent coloring, and entry animation.

## Requirements

### TOASTS-1
A Toasts stack renders every supplied toast item in supplied order. [FR-1400]

### TOASTS-1.1
An empty toasts list renders nothing at all and takes up no layout space. [FR-1400]

### TOASTS-2
The stack renders bottom-centre of the viewport — the root carries
`cmp-toasts--bottom-centre` (018 v5; retired: bottom-right).

### TOASTS-3
A toast's accent colour comes from its `kind` (`done`, `running`,
`waiting`, `failed`, `idle` → `cmp-toast-<kind>`); a toast without a kind
uses the default. The v5 `ToastItem` carries no colour pass-through — a
legacy `color` value contributes no inline style (018 R-10).

## Failure modes

An empty or undefined toasts array renders an empty container with no DOM children.
