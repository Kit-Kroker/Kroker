# Graph Canvas Component

Renders a pipeline graph as nodes with typed ports and directed edges, in one
of two modes: editable (a draft) or read-only with run decorations (a run).
The caller owns the graph, its keys, legality, layout persistence and every
consequence of an edit; the component owns rendering, auto-layout of
unpositioned nodes, and turning gestures into events. It decides no legality
(FR-1202): the single connection rule it runs is the caller's `connectable`.

## Requirements

### GRAPH_CANVAS-1
A Graph Canvas renders exactly one node per supplied node, keyed by its
`key`, with its issue count when non-zero; duplicate domain ids are the
caller's to disambiguate into distinct keys. [FR-1205]

### GRAPH_CANVAS-2
An edge with `backward: true` renders on a curved path below its endpoints
and carries `cmp-graph-edge-backward`. [FR-1205]

### GRAPH_CANVAS-3
An edge with a `counter` renders `used/max` as its label text. [FR-1205]

### GRAPH_CANVAS-4
A node with a `status` carries `cmp-graph-node-<status>`; an unknown status
fails rendering rather than falling back (STAGE_DOTS-1.2 precedent). The
status set is the run-state set: `idle`, `running`, `blocked`, `done`,
`failed`, `stale`, plus the run-end states `skipped` (never routed to) and
`cancelled` (cut down by a closed execution) -- E-75 design §7.4.
[FR-1205]

### GRAPH_CANVAS-5
With `editable: false` no node is draggable, no handle is connectable, and
no `connect`, `move`, `remove` or `drop-type` is emitted. [FR-1205]

### GRAPH_CANVAS-6
A connection attempt is accepted iff `editable` and the caller's
`connectable(from, to)` returns true; the component evaluates no other rule
(no multiplicity, duplicate, self-loop or cycle check). [FR-1202, FR-1205]

### GRAPH_CANVAS-7
The canvas's colours resolve through design tokens: vue-flow's stylesheet
(`@vue-flow/core/dist/style.css`, which carries colour literals) is not
imported; the structural rules the canvas needs are re-declared with `--*`
tokens under `.cmp-graph-canvas`. [FR-1404]

### GRAPH_CANVAS-8
`move` never emits a non-finite coordinate or an unknown key, and auto-layout
never adds an edge whose endpoint is not a supplied node key. [FR-1205]

### GRAPH_CANVAS-9
Decoration changes -- status, metrics, counters, issue counts -- never
replace the renderer's element lists; only a structural change (keys,
positions, ports, endpoints, backward) does, so edges persist across
run-state updates. [FR-1205]

## Failure modes

Layout throws: existing positions are kept, unpositioned nodes go on a grid,
and `layout-failed` is emitted. An edge naming a missing node is not drawn.
