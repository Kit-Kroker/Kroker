# Design System Preview Bundle

Builds standalone preview cards for each component profile in `@kroker/ui`
for Claude Design System import.

The build script serializes rendered showcase component profiles into standalone HTML
files with inlined CSS styles and leading `@dsCard` marker comments.

## Requirements

### DS_BUNDLE-1
The bundle emits one standalone HTML file per registered component profile. [FR-1405]

### DS_BUNDLE-2
Each emitted preview file places the `@dsCard` group marker on the literal first line. [FR-1405]

### DS_BUNDLE-3
Styles from the design system are inlined into each emitted file so previews render standalone without external stylesheet dependencies. [FR-1405]

## Failure modes

If the showcase server is not reachable or fails to start, the build fails.
If a component profile cannot be found or serialized, the bundle build aborts.
