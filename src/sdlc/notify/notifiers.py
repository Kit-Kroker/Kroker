"""The two reference delivery transports, in a registry resolved by config --
the same shape as HARNESSES (ADR-2) and TOOLCHAINS (ADR-15).

`log` is the default: zero configuration, no egress, deterministic in CI.
`webhook` is a generic JSON POST that Slack and Discord accept as-is; anything
else is a receiving shim, not our substrate (NG7).
"""

from __future__ import annotations

import json
import logging
import urllib.request
from urllib.parse import urlparse

from ..harness.containment import host_allowed

log = logging.getLogger("sdlc.notify")

POST_TIMEOUT_S = 10


class EgressDenied(Exception):
    """A webhook route was refused before any bytes left the process."""


class LogNotifier:
    """Default transport. Never raises, needs no configuration, and makes the
    test suite deterministic without stubbing a URL."""

    async def deliver(self, text: str, target: str | None) -> None:
        log.info("notification:\n%s", text)


class WebhookNotifier:
    """Generic JSON POST. The host is checked against the notification
    allowlist BEFORE the request is built: a notify webhook is the pipeline's
    second outbound egress after research, and FR-703 is not yet closed at
    the network level, so this tier fails closed."""

    def __init__(self, allow_hosts: list[str] | None = None) -> None:
        self.allow_hosts = list(allow_hosts or [])

    async def deliver(self, text: str, target: str | None) -> None:
        if not target:
            raise EgressDenied("webhook route has no target URL")
        host = urlparse(target).hostname or ""
        if not host_allowed(host, self.allow_hosts):
            raise EgressDenied(
                f"host {host!r} is not in the notification allow_hosts (policy/notifications.yaml)"
            )
        await self._post(target, {"text": text})

    async def _post(self, url: str, payload: dict) -> None:
        import asyncio

        def _send() -> None:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=POST_TIMEOUT_S):
                pass

        await asyncio.to_thread(_send)


NOTIFIERS: dict[str, object] = {
    "log": LogNotifier(),
    "webhook": WebhookNotifier(),  # allow_hosts injected per-run (Task 6)
}
