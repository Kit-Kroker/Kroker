# tests/test_assessment_activities.py
"""E-50: tests for assessment activities."""

from __future__ import annotations

import pytest

from sdlc.assessment.activities import load_dispositions
from sdlc.dispositions.models import Disposition, FindingDisposition
from sdlc.dispositions.store import BoardFindingDispositionStore


@pytest.mark.asyncio
async def test_load_dispositions_reads_every_finding_for_the_project(tmp_path):
    from datetime import UTC, datetime

    db = tmp_path / "board.sqlite3"
    store = BoardFindingDispositionStore(db=db)
    store.apply(
        "p",
        FindingDisposition(
            kind="vulnerability",
            key="SS1:hardcoded-secret:src/a.py:",
            disposition=Disposition.ACCEPTED_RISK,
            approved_by="maks",
            reason="reviewed",
            decided_at=datetime.now(UTC),
        ),
        expected_version=0,
        actor="maks",
    )
    store.close()
    rows = await load_dispositions("p", db=str(db))
    assert len(rows) == 1
    assert rows[0].key == "SS1:hardcoded-secret:src/a.py:"


@pytest.mark.asyncio
async def test_load_dispositions_returns_empty_tuple_for_a_fresh_project(tmp_path):
    db = tmp_path / "board.sqlite3"
    rows = await load_dispositions("brand-new-project", db=str(db))
    assert rows == ()
