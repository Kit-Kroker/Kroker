from dataclasses import FrozenInstanceError, fields

import pytest

from sdlc.core.context import StageContext, StageServices

ELEVEN = {
    "emit",
    "stage",
    "run_role",
    "cached_stage",
    "revisable_stage",
    "record",
    "judge",
    "recall",
    "retain",
    "gate",
    "ask_and_wait",
}


def _services(**over):
    base = {name: (lambda *a, **k: None) for name in ELEVEN}
    base.update(over)
    return StageServices(**base)


def test_protocol_has_exactly_eleven_services():
    members = {m for m in StageContext.__protocol_attrs__ if not m.startswith("_")}
    assert members == ELEVEN


def test_services_satisfies_the_protocol():
    assert isinstance(_services(), StageContext)


def test_services_is_frozen():
    svc = _services()
    with pytest.raises(FrozenInstanceError):
        svc.emit = None  # type: ignore[misc]


def test_services_exposes_nothing_beyond_the_protocol():
    # The whole point: a step handed this cannot reach _pending or _status.
    assert not [f.name for f in fields(_services()) if f.name not in ELEVEN]
