# Check Row Component

Renders one merge-readiness check: pass/fail mark, check name, detail, and
whether it is ABSOLUTE (blocks the merge) or ADVISORY. The caller owns the
check result (a `CheckRow` from the dashboard API); the component owns making
the one check that blocked the merge the loudest thing in the list.

## Requirements

### CHECK_ROW-1
A Check Row carries `is-ok` or `is-failing`, and `cmp-check-row-absolute` or
`cmp-check-row-advisory`. [FR-1400]

### CHECK_ROW-2
Only a failing ABSOLUTE check sits on the failed tint; a failing ADVISORY check
sits on the idle tint; a passing check has no ground. [FR-1404]

### CHECK_ROW-3
The mark carries `role="img"` and an `aria-label` of "passed" or "failed", so
the result does not depend on the glyph or its colour. [FR-1400]

## Failure modes

An empty `detail` renders the name alone.
