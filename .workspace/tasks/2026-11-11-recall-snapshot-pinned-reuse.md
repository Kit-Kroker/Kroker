# Reuse a persisted RecallSnapshot when the watermark is pinned (021 GATE 2 item 1)

| | |
|---|---|
| From | 021 round (GATE 2 ruling 1; skeptic probe 1) |
| Size | M |
| Status | open |

**What.** ARCHITECTURE.md ADR-5 (`ARCHITECTURE.md:210-224`) said recall is a cached activity, so a pinned watermark reuses the frozen snapshot. That has never been true: `recall_snapshot` (`src/sdlc/memory/activities.py:61`) re-queries the backend on every run. Hindsight has an LLM leg (~30s/call, `activities.py:24`), and nightly consolidation (`hindsight_client.py` reflect) can change the items under a fixed watermark.

**Why it matters.** Since 021 the stage memo key includes `snapshot_hash` (021 FR-010). A live-Hindsight re-run therefore usually *misses* the stage cache: the miss is explicit, but memoization is effectively off with Hindsight on, and every run still pays about 42s per recall. The 021 ruling accepted this and corrected the ADR-5 text (021 T061).

**Shape of a fix.** When `RecallInput.watermark` is pinned, look up a healthy persisted snapshot for the same `query_hash` and return it instead of querying the backend. That needs a cross-run index (`query_hash` → artifact ref), because 021 stores snapshots per run (`<root>/<run_id>/recall/<hash>.json`). Restore ADR-5's original wording when this lands.

**Evidence.** `.specify/specs/021-recall-snapshot-artifact/skeptic-answer-1.md` probe 1; plan.md GATE 2 item 1.
