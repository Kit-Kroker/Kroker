"""Deterministic freeze of a DraftOutput into Requirements (FR-113, plan
Task 2). The model proposes; code validates — offending stories are
dropped, never retried or repaired, and the survivors are frozen with
code-assigned ids. Pure function: no I/O, no model calls; the same draft,
mode, and cap always produce the same FreezeResult, and model noise (empty
narratives, odd whitespace, duplicates) is handled by rules rather than
exceptions.

The rules (spec §3, exact), applied per story in draft order:

- narratives that are empty or whitespace-only drop the whole story.
- FR/SC texts that are empty or whitespace-only drop as noise.
- exact-duplicate texts collapse to the first occurrence **globally across
  the artifact** — FR texts and SC texts each form one artifact-wide
  keyspace (a requirement stated twice is one requirement; case-sensitive
  match on the verbatim text, no normalization). A story verify rejects
  never contributes its texts to the keyspace: text from a rejected story
  must not block the same text in a story verify keeps.
- stories left with zero surviving `functional` entries drop — a story
  with nothing functional isn't a story. Zero surviving criteria is NOT a
  drop: the artifact-level "≥1 SC" pin is a caller warning, not verify's.
- brownfield drafts require a usable `source_ref` (`not (ref or "").strip()`
  drops — None, "", and whitespace all count as missing; strip semantics
  fix constitution's parked whitespace gotcha). Greenfield is exempt — an
  idea-alone draft has nothing to cite.
- ids `US-1…`, `FR-1…`, `SC-1…` are assigned in surviving order, the FR and
  SC counters global across the artifact — the `_PlannerOutput` precedent:
  the model never names the artifact's ids.
- more survivors than `max_stories` cap to the first `max_stories` with
  `capped=True` (bounded artifact, honest record; capped stories are
  recorded by the flag, not re-listed in `dropped`). Ids stay dense — the
  kept prefix of a dense sequence is dense.
- zero survivors degrade the stage: `drafted_by="empty"`, `digest=""`,
  `degraded=True` — the FAIL is noted by the caller; verify itself never
  raises.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import (
    DraftOutput,
    FunctionalRequirement,
    Requirements,
    Story,
    SuccessCriterion,
    requirements_digest,
)

FreezeMode = Literal["greenfield", "brownfield"]


class FreezeResult(BaseModel):
    """The outcome of freezing one draft: the frozen requirements plus an
    audit trail of what verify dropped, whether the artifact capped, and
    whether the stage degraded."""

    frozen: Requirements
    dropped: list[str] = Field(default_factory=list)  # dropped narratives/texts, draft order
    capped: bool = False  # survivors exceeded max_stories; the first max_stories kept
    degraded: bool  # True iff nothing survived — the caller records FAIL


def freeze(draft: DraftOutput, *, mode: FreezeMode, max_stories: int | None = None) -> FreezeResult:
    """Turn the drafter's raw proposals into Requirements, dropping the
    offenders and freezing the rest (partial freeze — see module docstring
    for the rules). `dropped` lists each dropped story's narrative and each
    dropped text in draft order; ids on survivors number densely from
    US-1 / FR-1 / SC-1."""
    frozen: list[Story] = []
    dropped: list[str] = []
    seen_fr: set[str] = set()  # artifact-wide keyspace: FR texts
    seen_sc: set[str] = set()  # artifact-wide keyspace: SC texts
    fr_n = 0  # id counters are artifact-global — they never reset per story
    sc_n = 0
    for item in draft.stories:
        narrative = item.narrative
        if not narrative.strip():
            dropped.append(narrative)
            continue
        if mode == "brownfield" and not (item.source_ref or "").strip():
            dropped.append(narrative)
            continue
        kept_fr: list[str] = []
        for text in item.functional:
            if not text.strip() or text in seen_fr:  # exact, case-sensitive match
                dropped.append(text)
            else:
                kept_fr.append(text)
        kept_sc: list[str] = []
        for text in item.success_criteria:
            if not text.strip() or text in seen_sc:
                dropped.append(text)
            else:
                kept_sc.append(text)
        if not kept_fr:  # nothing functional — not a story
            dropped.append(narrative)
            continue
        seen_fr.update(kept_fr)  # commit only now: rejected stories keyspace nothing
        seen_sc.update(kept_sc)
        frs = [
            FunctionalRequirement(id=f"FR-{fr_n + i}", text=text)
            for i, text in enumerate(kept_fr, 1)
        ]
        scs = [
            SuccessCriterion(id=f"SC-{sc_n + i}", text=text) for i, text in enumerate(kept_sc, 1)
        ]
        fr_n += len(frs)
        sc_n += len(scs)
        frozen.append(
            Story(
                id=f"US-{len(frozen) + 1}",
                narrative=narrative,
                functional=frs,
                success_criteria=scs,
                source_ref=item.source_ref,
            )
        )
    capped = max_stories is not None and len(frozen) > max_stories
    if capped:
        frozen = frozen[:max_stories]
    if frozen:
        requirements = Requirements(
            stories=frozen, digest=requirements_digest(frozen), drafted_by="agent"
        )
        degraded = False
    else:
        requirements = Requirements(stories=[], digest="", drafted_by="empty")
        degraded = True
    return FreezeResult(frozen=requirements, dropped=dropped, capped=capped, degraded=degraded)
