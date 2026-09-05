# App Header Component

Renders the global application navigation header with branding, top-level tabs,
aggregate fleet statistics, and the action to start a new run.
The caller owns route state, store subscription, and triggering modals;
the component owns the visual layout, typography, tab styling, and badge rendering.

## Requirements

### APP_HEADER-1
An App Header renders the brand name, top-level navigation tabs, and supplied stats. [FR-1400]

### APP_HEADER-1.1
The inbox count badge is absent when the inbox count is zero, never rendered as "0". [FR-1400]

### APP_HEADER-2
The active navigation tab carries a stable class, `tab-active`. [FR-1404]

## Failure modes

Omitting stats renders fallback placeholders. Negative or zero inbox count suppresses the badge.
