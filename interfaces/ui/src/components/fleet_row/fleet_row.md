# Fleet Row Component

Renders a single tabular row representing an active, completed, or blocked run in the fleet.
The caller owns run domain identity, stage computation, status selection, and navigation routing;
the component owns the columnar layout, typography, status pip composition, truncation, and visual styling.

## Requirements

### FLEET_ROW-1
A Fleet Row renders every supplied field in column order: ID, title with mode badge,
stage dots, status with pip and label, blocker, cost, and age. [FR-1400]

### FLEET_ROW-1.1
A null cost renders as an em dash (`—`), never `0.00` or `$0.00`: the system distinguishes
an unresolved or free run from a run that cost zero. [FR-1400]

### FLEET_ROW-2
The whole row is a single link to the supplied destination href. [FR-1400]

### FLEET_ROW-3
A long title truncates with ellipsis while the stage marks and other columns retain
their grid positions. [FR-1400]

## Failure modes

Missing required props will result in missing content or caller errors. Null or undefined
blocker and cost render em dashes.
