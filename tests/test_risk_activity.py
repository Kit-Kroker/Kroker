# tests/test_risk_activity.py
"""The one activity seam. Never raises: a failure is a not_collected map."""
from __future__ import annotations

import pytest

from sdlc.assessment.activities import AssessRiskInput, assess_risk
from sdlc.assessment.discover.map import CapabilityMap, DiscoverAction
from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ, C_DB_SECURITY, C_INPUT_VALIDATION, C_TLS,
)
from sdlc.measurement import CollectionState, Measurement

from tests.helpers_risk import capability

ALL = [C_AUTHN_AUTHZ, C_INPUT_VALIDATION, C_TLS, C_DB_SECURITY]


@pytest.fixture(autouse=True)
def _cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))


def _cmap(*caps) -> CapabilityMap:
    actions = {}
    for c in caps:
        actions[c.disposition.action] = actions.get(c.disposition.action, 0) + 1
    return CapabilityMap(capabilities=tuple(caps),
                         by_action=actions,
                         collected=Measurement.measured(1.0))


def _inp(cmap: CapabilityMap) -> AssessRiskInput:
    return AssessRiskInput(capability_map=cmap, collected_categories=ALL)


@pytest.mark.asyncio
async def test_it_scores_a_capability_map():
    out = await assess_risk(_inp(_cmap(capability())))
    assert out.collected.state is CollectionState.MEASURED
    assert len(out.capabilities) == 1


@pytest.mark.asyncio
async def test_an_uncollected_map_yields_not_collected():
    out = await assess_risk(_inp(
        CapabilityMap(collected=Measurement.not_collected("no discover"))))
    assert out.collected.state is CollectionState.NOT_COLLECTED


@pytest.mark.asyncio
async def test_the_baseline_is_deterministic_across_calls():
    """The memo moved to risk_memo_load/store with plan 2; what this seam
    still owes is a byte-identical result for identical input (NFR-10)."""
    inp = _inp(_cmap(capability()))
    first = await assess_risk(inp)
    second = await assess_risk(inp)
    assert first.model_dump_json() == second.model_dump_json()


@pytest.mark.asyncio
async def test_the_baseline_reports_no_judgment():
    """RD7: plan 2's activity still runs no model, so the judgment layer is
    not_collected until the workflow applies a proposal."""
    out = await assess_risk(_inp(_cmap(capability())))
    assert out.judgment.state is CollectionState.NOT_COLLECTED


@pytest.mark.asyncio
async def test_it_never_raises(monkeypatch):
    """E-41 spec D3: a signal that crashes yields not_collected for itself."""
    import sdlc.assessment.activities as acts

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(acts, "build_risk", boom)
    out = await assess_risk(_inp(_cmap(capability())))
    assert out.collected.state is CollectionState.NOT_COLLECTED
    assert "kaboom" in out.collected.reason
