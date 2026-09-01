"""The one definition of a recall snapshot's identity.

FakeMemory, HindsightMemory and the degraded path in activities.py all use
this, so a snapshot taken against the fake and one taken against Hindsight
are comparable -- which is what makes a memory-on/memory-off delta meaningful.
"""

from __future__ import annotations

import hashlib
import json


def recall_query_hash(bank: str, query: str, filters: dict[str, str], watermark: str | None) -> str:
    # json.dumps rather than str(): it escapes separators, so a bank
    # containing the delimiter cannot forge another bank's hash.
    payload = json.dumps(
        [bank, query, sorted(filters.items()), watermark], separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
