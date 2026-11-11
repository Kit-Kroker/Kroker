# Data model — 021

## RecallSnapshot (`src/sdlc/memory/models.py`)
| Field | Type | Default | Notes |
|---|---|---|---|
| query_hash | str | required | unchanged; `""` only on the memory-disabled path |
| bank | str | required | |
| watermark | str | required | |
| items | list[str] | `[]` | scrubbed (R-8); emptied on persist failure (R-5) |
| degraded | bool | False | |
| snapshot_hash | str | `""` | **new**; filled by validator when empty and (`query_hash` or `degraded`) |
| ref | ArtifactRef \| None | None | **new**; set when persisted |
| persist_failed | bool | False | **new**; True implies `degraded=True`, `items=[]`, `ref=None` |

States:
- disabled: `query_hash=""`, `snapshot_hash=""`, `ref=None`
- healthy: `degraded=False`, `ref` set
- backend-degraded: `degraded=True`, `items=[]`, `ref` set
- persist-failed: `degraded=True`, `persist_failed=True`, `items=[]`, `ref=None`
- no-run-id (direct call): healthy or degraded, `ref=None`, `persist_failed=False`

## Canonical content / artifact bytes
`json.dumps(["recall_snapshot/v1", bank, watermark, query_hash, items, degraded], separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.
`snapshot_hash = sha256(bytes)`. The file holds exactly these bytes, so `ArtifactRef.sha256 == snapshot_hash`.

## Artifact location
`LocalFileStore.put("recall_snapshot", run_id, f"{snapshot_hash}.json", bytes)` → `<root>/<run_id>/recall/<snapshot_hash>.json`. Idempotent (same name, same bytes).

## RecallInput (`src/sdlc/memory/activities.py:51`)
Adds `run_id: str = ""`.

## RunEvent `memory_recalled`
`kind=MEMORY_RECALLED`, `stage=filters.get("stage")`, `data={snapshot_hash, snapshot_uri, degraded: "true"|"false", persist_failed: "true"|"false"}`. Never carries items (FR-011). Emitted only when memory is enabled.

## Memo key (`content_key` slot 5)
- `recall_ref == ""` → `wm` (unchanged)
- otherwise → `f"{wm}|{recall_ref}"`, where `wm = _memory_watermark or "none"`
