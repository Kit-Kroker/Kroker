# Quickstart: validating the Decision Inbox (010)

How to prove the feature works once it is built. Names and selectors are in [data-model.md](data-model.md) and [contracts/inbox-screen.md](contracts/inbox-screen.md); they are not repeated here.

## Prerequisites

- Run in the environment the orchestrator names for this run. Node must be present: `scripts/check_ui.py` exits 0 with a loud "skipped" when Node is missing, and **a skip is not a pass**.
- On Windows, `PLAYWRIGHT_BROWSERS_PATH` should point at `D:/own/.pw-browsers` (the wrapper sets it when unset).
- Never chain two test runs in one shell call.

## 1. Automated gates

Run each from the repository root, one per call.

| Command | Expected |
|---|---|
| `python scripts/check_ui.py` | every step green: install, both typechecks, both builds, vitest-dashboard, ds-bundle, vitest-ui, playwright |
| `python scripts/check_clauses.py` | always exits 0, so read it: no `clause with no test: CONSOLE-17` … `CONSOLE-23` line, and no dangling citation |
| `python scripts/check_file_size.py` | no file over 1000 lines |

The Python gates (`pytest` fast tier, `ruff check .`, `ruff format --check .`, `mypy`) are the orchestrator's integration check. This feature changes no Python file, so they are expected to be unchanged.

## 2. Manual walk on the mock provider

```text
cd interfaces/dashboard/frontend
VITE_API=mock npm run dev
```

Open the address Vite prints and go to the Inbox tab.

| Step | Expect | Proves |
|---|---|---|
| Open the inbox | six entries; the header badge reads 6; the count line reads "6 waiting" | SC-002, US1 |
| Read any entry | kind, run id as a link, age, title, body | US1 |
| On Q1, press accept | the entry leaves; badge 5 | SC-003, US2 |
| On Q2, press edit, change the text, send | the entry leaves; badge 4 | US2 |
| On the usage-metering gate, press revise with no comment | nothing happens (revise is unavailable) | US3 |
| Type a comment, wait for at least 12 seconds, look again | the comment is still there | SC-005 |
| Press revise | the entry leaves; badge 3 | US3 |
| On the merge override entry | six check rows and the verdict are shown; override is unavailable | US4 |
| Type a justification, press override | the entry leaves; badge 2 | US4 |
| Narrow the window and look at the escalation entry | its analysis wraps inside the entry; the retry and quarantine actions stay visible; the page does not scroll sideways | EC8 |
| On the escalation entry, press quarantine | the entry leaves; badge 1 | US4 |
| On the graph-demo gate, press approve | the entry leaves; "Nothing is waiting." is shown; the header shows no badge | SC-001, US1 |
| Open the graph-demo run | its canvas offers no gate decision | US3 |
| Reload the page, open the inbox, follow any run link | that run's page opens | US1, SC-006 |

## 3. What cannot be shown on the mock

The mock cannot fail a read, report an unreadable run, or hold two runs on one key. It refuses a write only when the item was decided elsewhere in the few seconds before the next poll, which cannot be reproduced reliably. Those behaviours are proved by the unit tests named in the contract §6: `inbox.store.test.ts`, `InboxView.test.ts`, `entryKey.test.ts`, and the `mapInboxState` cases in `http.test.ts`.

## 4. Optional check against a live backend

With the dashboard backend running and a run waiting at a gate, open the inbox on the default (`http`) provider and decide the item. The same item must disappear from `python -m sdlc.cli inbox`. The decision is recorded as `human:unknown` (GATE 1, Q3 = A).
