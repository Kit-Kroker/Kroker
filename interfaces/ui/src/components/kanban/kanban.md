# Kanban Component

The v5 run board (S7, V7): one column per wire status present, each
card showing its task id, optional title, tag and meta. Presentational
— `features/board/kanban.adapter.ts` (dashboard) maps board tasks to
these display columns; the optional footer link opens the full Agent
Board.

## Requirements

### KANBAN-1
The board renders one column per entry with its title and count; an
empty columns array renders no column and no card, without throwing.
[FR-023]

### KANBAN-2
Each card of its column renders its id, its tag (carrying `tagKind` as
a stable class from the wire status vocabulary), and its meta; a card
with a title renders it, and a card without one never renders the
string `undefined`. [FR-023]

### KANBAN-3
The footer link renders only when one is given — its label as the link
text, its `to` as the destination. [FR-023]

## Failure modes

The board never invents a column, a count or a card; everything visible
comes from the props. The link never renders a default destination.
