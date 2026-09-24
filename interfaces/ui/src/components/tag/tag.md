# Tag Component

Renders a short, non-interactive label: a decision kind ("Gate · plan"),
an evidence kind ("qa", "rv"), a "Best" marker on a comparison. The caller owns
the words; the component owns the outline, tone and mono treatment.

A tag that means a lifecycle state is a Status Tag, not a Tag. A tag the user
can press is a Filter Chip.

## Requirements

### TAG-1
A Tag renders its default slot and carries its tone as `cmp-tag-<neutral|strong>`. [FR-1400]

### TAG-2
`mono` adds `is-mono` for tags that label identifiers (evidence kinds, port types). [FR-1400]

### TAG-3
A Tag is not interactive: it renders a `span` with no role, tabindex or listener. [FR-1400]

## Failure modes

An empty slot renders an empty outlined box; callers omit the tag instead.
