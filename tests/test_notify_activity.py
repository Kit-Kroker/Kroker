"""E-9 Task 6: the activity. Every route is attempted; a raising transport
becomes a reported failure, never an exception that reaches the workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sdlc.notify import activities as act
from sdlc.notify.contract import NotifyInput, NotifyReason
from sdlc.pending import ClarifyPending

T0 = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)

ASSET = """
version: 1
base_url: null
allow_hosts: [hooks.slack.com]
default:
  primary: log
  fallback: log
gates: {}
"""


@pytest.fixture
def routes(tmp_path, monkeypatch):
    p = tmp_path / "notifications.yaml"
    p.write_text(ASSET, encoding="utf-8")
    monkeypatch.setenv("SDLC_NOTIFY_ROUTES", str(p))
    return p


def _input(reason=NotifyReason.OPENED) -> NotifyInput:
    return NotifyInput(
        run_id="abc123",
        pending=ClarifyPending(
            key="q1", question="Which datastore?", why_it_matters="Drives the schema."
        ),
        reason=reason,
        opened_at=T0,
        now=T0,
        deadline=T0 + timedelta(hours=48),
    )


@pytest.mark.asyncio
async def test_primary_only_for_opened(routes):
    out = await act.notify(_input())
    assert [r.notifier for r in out.results] == ["log"]
    assert all(r.delivered for r in out.results)


@pytest.mark.asyncio
async def test_escalate_delivers_to_primary_and_fallback(routes):
    out = await act.notify(_input(NotifyReason.ESCALATE))
    assert [r.notifier for r in out.results] == ["log", "log"]


@pytest.mark.asyncio
async def test_a_raising_transport_is_reported_not_propagated(routes, monkeypatch):
    class Boom:
        async def deliver(self, text, target):
            raise RuntimeError("slack is down")

    monkeypatch.setitem(act.NOTIFIERS, "log", Boom())
    out = await act.notify(_input())
    assert out.results[0].delivered is False
    assert "slack is down" in out.results[0].error


@pytest.mark.asyncio
async def test_a_broken_routes_asset_is_reported_not_propagated(monkeypatch, tmp_path):
    bad = tmp_path / "notifications.yaml"
    bad.write_text("version: 99\n", encoding="utf-8")
    monkeypatch.setenv("SDLC_NOTIFY_ROUTES", str(bad))
    out = await act.notify(_input())
    assert out.results == [] or all(not r.delivered for r in out.results)


@pytest.mark.asyncio
async def test_no_configured_route_yields_no_results(routes, monkeypatch):
    monkeypatch.setattr(act, "load_routes", lambda: _routes_with_no_primary())
    out = await act.notify(_input())
    assert out.results == []


def _routes_with_no_primary():
    from sdlc.notify.routes import NotifyRoutes

    return NotifyRoutes(version=1, default={}, gates={})


@pytest.mark.asyncio
async def test_webhook_gets_the_allowlist_injected(routes, monkeypatch):
    """allow_hosts lives in the asset, so the transport must be built per
    call rather than used from the module-level registry."""
    seen = {}

    class Recorder:
        def __init__(self, allow_hosts=None):
            seen["allow_hosts"] = allow_hosts

        async def deliver(self, text, target):
            pass

    monkeypatch.setattr(act, "WebhookNotifier", Recorder)
    monkeypatch.setattr(act, "load_routes", lambda: _webhook_routes())
    await act.notify(_input())
    assert seen["allow_hosts"] == ["hooks.slack.com"]


def _webhook_routes():
    from sdlc.notify.routes import NotifyRoutes, Route

    return NotifyRoutes(
        version=1,
        allow_hosts=["hooks.slack.com"],
        default={"primary": Route(notifier="webhook", target="https://hooks.slack.com/x")},
        gates={},
    )
