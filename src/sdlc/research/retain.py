"""What the research stage writes to the corpus: VERIFIED grounded findings
only. Nothing unverified enters memory, so recall can never launder a false
claim into ground truth. Findings become leads, not grounded claims — recall
must re-fetch to re-ground (spec §6)."""
from __future__ import annotations

from ..models import MemoryKind, ResearchBrief, RetainItem
from .verify import verify_brief


def verified_findings_to_retain(brief: ResearchBrief, run_id: str,
                                bank: str = "project:default"
                                ) -> list[RetainItem]:
    bad = {(v.source, v.quote) for v in verify_brief(brief, run_id)}
    items: list[RetainItem] = []
    for f in brief.grounded_findings:
        if (f.source_url, f.quote) in bad:
            continue
        items.append(RetainItem(
            kind=MemoryKind.RESEARCH_FINDING, bank=bank,
            text=f"{f.claim} — {f.source_url}",
            metadata={"stage": "research", "source_url": f.source_url}))
    return items
