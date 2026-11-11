# `recall_leads` bypasses RecallSnapshot persistence and the degrade path (021 GATE 2 item 2)

| | |
|---|---|
| From | 021 round (GATE 2 ruling 2; skeptic probe 5) |
| Size | S |
| Status | open |

**What.** The research agent's tool `agents/research/tools/recall_leads.py:14-17` calls `_backend(...).recall(...)` directly, not through the `recall_snapshot` activity. Consequences:
1. It is not persisted as a 021 snapshot artifact and not recorded by a `memory_recalled` event.
2. It has **no degrade path**: an unreachable Hindsight raises out of the tool instead of returning an empty snapshot. Research tool-call retries are uncapped, so see also E-28 in `docs/roadmap/filesystem-first.md`.
3. Its recalled text is not passed through `scrub()`. 021 adds recall-side scrubbing only in the activity.

It runs in the research stage and, through the architect's `research` tool, in the architecture stage (`src/sdlc/stages/research/toolset.py:92-102`).

**Why it is not 021.** 021 FR-001/SC-001 were narrowed at GATE 2 to stage-level `ctx.recall`. Leads are never grounded inputs by design (`recall_leads` docstring; `src/sdlc/stages/research/retain.py:2-3`).

**Shape of a fix.** Route the tool through the same persist-scrub-degrade helper as the activity (pass `run_id` via `ResearchDeps`), or at least catch backend errors and return `[]`.
