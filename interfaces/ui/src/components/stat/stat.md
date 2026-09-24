# Stat Component

Renders one counter: a small label over a mono number, optionally led by a
status pip ("In progress 2", "Fix attempts 6", "Events 412"). The caller owns
the number and its formatting; the component owns the hierarchy.

Stats show what the source owns. The board strip shows board counters only;
cost and quality belong to `benchmarks/` and are not restated here.

## Requirements

### STAT-1
A Stat renders its label and its value, the value in the mono family. [FR-1400]

### STAT-2
A pip renders before the label only when `pip` is given, as a Status Pip of that kind. [FR-1400]

### STAT-3
A `null`, `undefined` or empty value renders an em dash; `0` renders "0". [FR-1400]

## Failure modes

Formatting (currency, durations, thousands) is caller-owned; the component
renders the string it is given.
