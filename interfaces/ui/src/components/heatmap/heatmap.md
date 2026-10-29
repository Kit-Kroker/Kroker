# Heatmap Component

Compare's "Rework by canonical_stage" heatmap (S10, FR-052): one column
per canonical stage in wire order, one row per arm, cells by state.
Presentational — the compare read maps into these display shapes; the
intensity rides a token scale, never a literal colour.

## Requirements

### HEATMAP-1
The heatmap renders one column header per column, in wire order; an
empty columns and rows array renders no header, row or cell, without
throwing. [FR-052]

### HEATMAP-2
One row per entry with its name, and one cell per column. [FR-052]

### HEATMAP-3
A value cell shows its value; a blank cell renders empty — no number, no
zero, no placeholder text. [FR-052]

### HEATMAP-4
A low_n cell carries its muted treatment as a stable `low-n` class; a
value cell does not. [FR-052]

### HEATMAP-5
Colour comes from a token scale — a `heat-scale-*` class over the status
tokens via color-mix — never a literal colour (TOKENS-2). [FR-052]

## Failure modes

The heatmap never invents a column, a row or a value; everything visible
comes from the props. Blank is blank.
