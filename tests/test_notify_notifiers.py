"""E-9 Task 5: the two reference transports. The webhook is the pipeline's
second outbound egress after research (FR-703), so it fails closed on any
host not explicitly allowlisted."""
from __future__ import annotations

import logging

import pytest

from sdlc.notify.notifiers import (
    NOTIFIERS, EgressDenied, LogNotifier, WebhookNotifier,
)


def test_registry_ships_exactly_log_and_webhook():
    assert set(NOTIFIERS) == {"log", "webhook"}


@pytest.mark.asyncio
async def test_log_notifier_writes_the_text_and_never_raises(caplog):
    with caplog.at_level(logging.INFO):
        await LogNotifier().deliver("gate merge awaiting you", None)
    assert "gate merge awaiting you" in caplog.text


@pytest.mark.asyncio
async def test_webhook_posts_json_to_an_allowlisted_host(monkeypatch):
    sent = {}

    async def fake_post(url, payload):
        sent["url"], sent["payload"] = url, payload

    n = WebhookNotifier(allow_hosts=["hooks.slack.com"])
    monkeypatch.setattr(n, "_post", fake_post)
    await n.deliver("hello", "https://hooks.slack.com/services/T/B/X")
    assert sent["url"] == "https://hooks.slack.com/services/T/B/X"
    assert sent["payload"] == {"text": "hello"}


@pytest.mark.asyncio
async def test_webhook_accepts_a_subdomain_of_an_allowlisted_host(monkeypatch):
    n = WebhookNotifier(allow_hosts=["slack.com"])
    monkeypatch.setattr(n, "_post", lambda url, payload: _noop())
    await n.deliver("hello", "https://hooks.slack.com/x")


async def _noop():
    return None


@pytest.mark.asyncio
async def test_webhook_denies_a_non_allowlisted_host(monkeypatch):
    n = WebhookNotifier(allow_hosts=["hooks.slack.com"])
    monkeypatch.setattr(n, "_post", lambda url, payload: _noop())
    with pytest.raises(EgressDenied, match="evil.example.com"):
        await n.deliver("hello", "https://evil.example.com/x")


@pytest.mark.asyncio
async def test_webhook_denies_when_the_allowlist_is_empty():
    """Fail closed: no allowlist means no egress, not unrestricted egress."""
    with pytest.raises(EgressDenied):
        await WebhookNotifier(allow_hosts=[]).deliver(
            "hello", "https://hooks.slack.com/x")


@pytest.mark.asyncio
async def test_webhook_without_a_target_is_a_config_error():
    with pytest.raises(EgressDenied):
        await WebhookNotifier(allow_hosts=["hooks.slack.com"]).deliver(
            "hello", None)


def test_containment_host_matching_is_reused_not_reimplemented():
    """One implementation of the subdomain rule, shared with the pre_tool
    hook -- two would drift and a host would be allowed in one and denied
    in the other."""
    from sdlc.harness.containment import host_allowed
    assert host_allowed("hooks.slack.com", ["slack.com"])
    assert not host_allowed("notslack.com", ["slack.com"])
