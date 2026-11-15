"""Contract tests for the two incident memory kinds (023b T006, RED).

Subject: ``sdlc.memory.models.MemoryKind`` gains ``INCIDENT_LESSON`` and
``INCIDENT_EXPERIENCE`` (023b R13, data-model.md "MemoryKind (additions)").
Until T007 lands these members are absent, so every test here fails.
"""

from __future__ import annotations

import pytest

from sdlc.memory.fake import FakeMemory
from sdlc.memory.hindsight_client import _filter_tags
from sdlc.memory.models import MemoryKind, RetainItem


def test_incident_kind_values_are_pinned():
    assert MemoryKind.INCIDENT_LESSON == "incident_lesson"
    assert MemoryKind.INCIDENT_EXPERIENCE == "incident_experience"


@pytest.mark.asyncio
async def test_fake_memory_retains_and_recalls_both_incident_kinds_by_kind_filter():
    mem = FakeMemory()
    await mem.retain(
        RetainItem(
            kind=MemoryKind.INCIDENT_LESSON,
            bank="project:x",
            text="lesson: stale .env fixed by rotating the key",
            metadata={"kind": MemoryKind.INCIDENT_LESSON.value},
        )
    )
    await mem.retain(
        RetainItem(
            kind=MemoryKind.INCIDENT_EXPERIENCE,
            bank="project:x",
            text="experience: fix did not hold, escalated",
            metadata={"kind": MemoryKind.INCIDENT_EXPERIENCE.value},
        )
    )

    lessons = await mem.recall(
        "project:x", "incident", {"kind": MemoryKind.INCIDENT_LESSON.value}, None
    )
    experiences = await mem.recall(
        "project:x", "incident", {"kind": MemoryKind.INCIDENT_EXPERIENCE.value}, None
    )

    assert lessons.items == ["lesson: stale .env fixed by rotating the key"]
    assert experiences.items == ["experience: fix did not hold, escalated"]


def test_hindsight_filter_accepts_kind_for_both_incident_kinds():
    # _filter_tags raises ValueError for any key it cannot honour; "kind" is
    # always filterable because the kind tag is always written (hindsight_client.py).
    assert _filter_tags({"kind": "incident_lesson"}) == ["kind:incident_lesson"]
    assert _filter_tags({"kind": "incident_experience"}) == ["kind:incident_experience"]
