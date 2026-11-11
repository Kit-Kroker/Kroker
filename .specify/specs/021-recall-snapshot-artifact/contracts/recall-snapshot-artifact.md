# Contract — recall_snapshot artifact and memory_recalled event

Internal contract (no HTTP surface in this feature).

1. **File**: `<artifact_root>/<run_id>/recall/<snapshot_hash>.json`. Content is the canonical JSON array `["recall_snapshot/v1", bank, watermark, query_hash, items, degraded]` (UTF-8, compact separators). `sha256(file) == snapshot_hash == ArtifactRef.sha256`. `ArtifactRef.kind == "recall_snapshot"`.
2. **Reader**: `sdlc.artifacts.read.read_recall_snapshot(ref: ArtifactRef) -> RecallSnapshot`. It raises `ValueError` on the wrong kind or a hash mismatch, and never returns unverified content.
3. **Event**: `events.jsonl` line with `kind="memory_recalled"`, `stage` = the recalling stage, and `data` keys `snapshot_hash`, `snapshot_uri`, `degraded`, `persist_failed`. Additive: consumers that ignore unknown kinds are unaffected (`observability/summary.py` filters by kind).
4. **Version tag**: `recall_snapshot/v1`. Any change to the canonical form bumps the tag.
