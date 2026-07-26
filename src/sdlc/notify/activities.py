"""The notify activity -- everything the workflow sandbox cannot do.

Route resolution reads a YAML file and delivery opens a socket, so both live
here. The same split as harness containment: "flags travel; the YAML is
loaded activity-side."

This activity NEVER raises. A gate must remain decidable no matter what the
notification path does, so every failure becomes a DeliveryResult the
workflow can trace (spec 6) rather than an exception it must swallow blind.
"""
from __future__ import annotations

from temporalio import activity

from .contract import DeliveryResult, NotifyInput, Results
from .notifiers import NOTIFIERS, WebhookNotifier
from .render import render_notification
from .routes import load_routes


def _build(notifier_name: str, allow_hosts: list[str]):
    """Resolve a transport. `webhook` is constructed per call because its
    allowlist comes from the asset, not from module state."""
    if notifier_name == "webhook":
        return WebhookNotifier(allow_hosts=allow_hosts)
    return NOTIFIERS[notifier_name]


@activity.defn
async def notify(inp: NotifyInput) -> Results:
    try:
        routes = load_routes()
    except Exception as e:                # noqa: BLE001 - reported, not raised
        activity.logger.warning("notification routes unavailable: %s", e)
        return Results(results=[
            DeliveryResult(notifier="unresolved", delivered=False,
                           error=str(e)[:500])])

    gate = getattr(inp.pending, "gate", None) or ""
    text = render_notification(
        pending=inp.pending, reason=inp.reason, run_id=inp.run_id,
        opened_at=inp.opened_at, now=inp.now,
        deadline=inp.deadline, base_url=routes.base_url)

    out: list[DeliveryResult] = []
    for route in routes.routes_for(gate, inp.reason):
        try:
            transport = _build(route.notifier, routes.allow_hosts)
            await transport.deliver(text, route.target)
            out.append(DeliveryResult(notifier=route.notifier,
                                      delivered=True))
        except Exception as e:            # noqa: BLE001 - reported, not raised
            out.append(DeliveryResult(notifier=route.notifier,
                                      delivered=False, error=str(e)[:500]))
    return Results(results=out)
