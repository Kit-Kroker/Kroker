# tests/test_assessment_activities.py
"""FR-304 (E-50 GD8): re-runs read persisted dispositions through one
activity, never memoized -- a disposition recorded between runs must be
visible on the very next one."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sdlc.assessment.activities import LoadDispositionsInput, load_dispositions
from sdlc.dispositions.models import Disposition, FindingDisposition
from sdlc.dispositions.store import BoardFindingDispositionStore

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def board(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    return tmp_path / "board.sqlite3"


def _fd(**kw) -> FindingDisposition:
    base = dict(
        kind="vulnerability",
        key="SS1:hardcoded-secret:src/a.py:",
        disposition=Disposition.ACCEPTED_RISK,
        approved_by="maks",
        reason="reviewed, tolerated",
        decided_at=datetime.now(UTC),
    )
    base.update(kw)
    return FindingDisposition(**base)


async def test_no_dispositions_yet_returns_empty():
    out = await load_dispositions(LoadDispositionsInput(project="acme"))
    assert out == ()


async def test_a_persisted_disposition_is_read_back():
    store = BoardFindingDispositionStore()
    store.apply("acme", _fd(), expected_version=0, actor="maks")
    store.close()

    out = await load_dispositions(LoadDispositionsInput(project="acme"))
    assert len(out) == 1
    assert out[0].key == "SS1:hardcoded-secret:src/a.py:"


async def test_projects_are_isolated():
    store = BoardFindingDispositionStore()
    store.apply("acme", _fd(), expected_version=0, actor="maks")
    store.close()

    out = await load_dispositions(LoadDispositionsInput(project="other"))
    assert out == ()
