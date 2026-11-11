"""The one definition of a recall snapshot's identity.

FakeMemory, HindsightMemory and the degraded path in activities.py all use
this, so a snapshot taken against the fake and one taken against Hindsight
are comparable -- which is what makes a memory-on/memory-off delta meaningful.

021 FR-402 adds the sibling `recall_snapshot_*` pair: the identity of the
question stays `recall_query_hash`; the content of the *answer* gets its own
canonical, version-tagged serialization and sha256 (`snapshot_hash`), so
every backend path derives it from one definition. `recall_query_hash` is
byte-for-byte unchanged (FR-003).
"""

from __future__ import annotations

import hashlib
import json

SNAPSHOT_TAG = "recall_snapshot/v1"


def recall_query_hash(bank: str, query: str, filters: dict[str, str], watermark: str | None) -> str:
    # json.dumps rather than str(): it escapes separators, so a bank
    # containing the delimiter cannot forge another bank's hash.
    payload = json.dumps(
        [bank, query, sorted(filters.items()), watermark], separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def recall_snapshot_canonical(
    bank: str, watermark: str, query_hash: str, items: list[str], degraded: bool
) -> bytes:
    """The exact bytes a snapshot artifact holds (021 data model): the
    version-tagged compact JSON array. Item order is significant (recall
    ranking feeds the prompt); `degraded` is part of the answer."""
    return json.dumps(
        [SNAPSHOT_TAG, bank, watermark, query_hash, items, degraded],
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def recall_snapshot_hash(
    bank: str, watermark: str, query_hash: str, items: list[str], degraded: bool
) -> str:
    return hashlib.sha256(
        recall_snapshot_canonical(bank, watermark, query_hash, items, degraded)
    ).hexdigest()
