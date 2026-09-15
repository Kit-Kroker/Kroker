# Node Palette Component

Lists the node types a draft graph may add, grouped by kind. The caller owns
the type catalog (served by the backend) and what adding a node means; the
component owns the list, its grouping, and the drag payload.

## Requirements

### NODE_PALETTE-1
A Node Palette renders one item per supplied type, grouped stages first then
gates, supplied order kept within a group; an empty list renders an empty
state, not an error. [FR-1205]

### NODE_PALETTE-2
Clicking an item emits `pick` with its type; dragging it carries the type as
`application/x-kroker-node-type`, the payload `graph_canvas` accepts on drop.
While `disabled`, neither happens. [FR-1205]

## Failure modes

A type with no canonical stage shows `unknown`, never a guessed stage.
