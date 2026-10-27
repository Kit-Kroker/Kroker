# App Header Component

Renders v5's application header: the wordmark, primary and secondary
navigation, the run switch, Search ⌘K and the ⋯ display menu trigger.
The caller owns route state, the nav manifest and the menus; the
component owns layout, typography and badge rendering. There is no
stats block and no Start-run button (018 S4).

## Requirements

### APP_HEADER-1
The header renders the wordmark (mark `K` + `Kroker`), the primary and
secondary navigation in order, and only items whose `available` flag is
true. It renders no stats element and no Start button. [FR-1400]
(rewritten 018: the old clause asserted `SDLC·FACTORY`, uppercase tabs
and supplied stats — S4 retires them.)

### APP_HEADER-1.1
The badge is absent when `badge` is zero, never rendered as "0". [FR-1400]

### APP_HEADER-2
The active navigation tab carries a stable class, `tab-active`. [FR-1404]

### APP_HEADER-3
The run switch renders only when supplied, and its Observe/Design
segment only when `mode` is set. Search and ⋯ emit `search` and `menu`. [FR-1400]

## Failure modes

An item marked `available: false` is not rendered at all. A run switch
without an active tab highlights nothing. Omitting `runSwitch` hides the
switch; omitting `badge` hides the badge (APP_HEADER-1.1).
