"""What the research stage writes to the corpus: VERIFIED grounded findings
only. Nothing unverified enters memory, so recall can never launder a false
claim into ground truth. Findings become leads, not grounded claims — recall
must re-fetch to re-ground (spec §6).

The caller supplies the verification: `violations` is the result
`verify_brief_activity` returned for THIS brief, and a grounded finding it
names is dropped. This function reads no file — it decides from the result
it is handed, so a replay needs no page files. An empty list is the caller's
claim that the brief verified clean; nothing here can check that claim.
"""

from __future__ import annotations

from ...grounding import Violation
from ...memory.models import (
    MemoryKind,
    RetainItem,
)
from .models import ResearchBrief


def verified_findings_to_retain(
    brief: ResearchBrief, violations: list[Violation], bank: str = "project:default"
) -> list[RetainItem]:
    bad = {(v.source, v.quote) for v in violations}
    items: list[RetainItem] = []
    for f in brief.grounded_findings:
        if (f.source_url, f.quote) in bad:
            continue
        items.append(
            RetainItem(
                kind=MemoryKind.RESEARCH_FINDING,
                bank=bank,
                text=f"{f.claim} — {f.source_url}",
                metadata={"stage": "research", "source_url": f.source_url},
            )
        )
    return items
