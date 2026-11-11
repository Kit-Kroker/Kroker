# Skeptic brief 1 — 021 RecallSnapshot persisted input (spec: .specify/specs/021-recall-snapshot-artifact/spec.md)

Pressure-test the LOCKED decisions below. For each: the strongest concrete failure scenario (inputs/state -> wrong outcome), how likely, and what the plan must add to close it. Cite file:line. Write your answer to .specify/specs/021-recall-snapshot-artifact/skeptic-answer-1.md; edit nothing else.

L1 Q1: snapshot_hash joins the memo key ALONGSIDE the watermark (FR-010). Memory-off key byte-identical to today (FR-007).
L2 Q2: snapshot content lives in the artifact store only (src/sdlc/artifacts/store.py); stage record carries hash + ref, no items (FR-011).
L3 Q3: a persistence failure continues as degraded, logged and marked (FR-008); degraded never shares a key with healthy (FR-006).
L4 D1 content hash covers [bank, watermark, query_hash, ordered items, degraded]; query_hash (src/sdlc/memory/query_hash.py) unchanged (FR-003).
L5 FR-009 replay: recall output already in Temporal history, persistence idempotent, so no nondeterminism.

Specifically look for: (1) whether Hindsight recall nondeterminism under a fixed watermark makes the new key miss on EVERY re-run (memoization effectively dead with memory on — is that acceptable under NFR-6/ADR-5, ARCHITECTURE.md:210?); (2) replay of tests/replay/histories/research_retain_grounded.json and any memory-enabled golden if the RecallSnapshot payload or cache_get input changes; (3) the artifact store being local-disk per worker (LocalFileStore) — a ref written by worker A unreadable from worker B / the dashboard; (4) whether anything consumes RecallSnapshot fields positionally or by equality (tests/test_hindsight_recall.py:143, stage stubs) such that a new field breaks them; (5) multiple recalls in one stage or recall outside the three stages (grep ctx.recall / _recall callers); (6) PII: recalled items persisted to disk in plaintext — they were scrubbed at retain (src/sdlc/memory/scrub.py), is that enough per NFR-5/NFR-8 tenant isolation?
