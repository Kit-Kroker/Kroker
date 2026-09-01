"""Spec D11: the default collects nothing, and every failure path is
not_collected rather than an empty advisory list."""

import json
from unittest.mock import patch

import pytest

from sdlc.measurement import CollectionState
from sdlc.triage.advisories import (
    NoneAdvisorySource,
    OsvAdvisorySource,
    resolve_advisory_source,
)


def test_the_default_source_collects_nothing():
    r = NoneAdvisorySource().lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.advisories == []
    assert "no advisory source configured" in r.collected.reason


def test_an_unknown_name_resolves_to_none_and_says_which_name():
    src = resolve_advisory_source("nosuchsource")
    r = src.lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert "nosuchsource" in r.collected.reason


def test_the_registry_resolves_both_shipped_sources():
    assert isinstance(resolve_advisory_source("none"), NoneAdvisorySource)
    assert isinstance(resolve_advisory_source("osv"), OsvAdvisorySource)


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._body = json.dumps(payload).encode()
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _osv_payload():
    return {
        "vulns": [
            {
                "id": "GHSA-1234",
                "summary": "Request smuggling in requests",
                "database_specific": {"severity": "HIGH"},
            }
        ]
    }


def test_osv_maps_a_hit_to_a_typed_advisory():
    with patch(
        "sdlc.triage.advisories.urllib.request.urlopen", return_value=_FakeResponse(_osv_payload())
    ):
        r = OsvAdvisorySource().lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.MEASURED
    assert r.collected.value == 1.0
    assert r.advisories[0].advisory_id == "GHSA-1234"
    assert r.advisories[0].severity == "high"
    assert r.advisories[0].package == "requests"


def test_osv_no_hits_is_a_measured_zero_not_not_collected():
    with patch(
        "sdlc.triage.advisories.urllib.request.urlopen", return_value=_FakeResponse({"vulns": []})
    ):
        r = OsvAdvisorySource().lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.MEASURED
    assert r.collected.value == 0.0


@pytest.mark.parametrize(
    "boom",
    [
        TimeoutError("timed out"),
        OSError("connection refused"),
        ValueError("not json"),
    ],
)
def test_every_osv_failure_path_is_not_collected(boom):
    with patch("sdlc.triage.advisories.urllib.request.urlopen", side_effect=boom):
        r = OsvAdvisorySource().lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.advisories == []


def test_a_non_200_is_not_collected():
    with patch(
        "sdlc.triage.advisories.urllib.request.urlopen", return_value=_FakeResponse({}, status=503)
    ):
        r = OsvAdvisorySource().lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert "503" in r.collected.reason


def test_no_ecosystem_is_not_collected():
    r = OsvAdvisorySource().lookup(None, ["requests"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert "ecosystem" in r.collected.reason


def test_exceeding_the_package_cap_is_not_collected_not_a_partial_answer():
    src = OsvAdvisorySource(max_packages=2)
    r = src.lookup("PyPI", ["a", "b", "c"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.advisories == []


def test_an_empty_package_list_is_a_measured_zero():
    r = OsvAdvisorySource().lookup("PyPI", [])
    assert r.collected.state is CollectionState.MEASURED
    assert r.collected.value == 0.0
