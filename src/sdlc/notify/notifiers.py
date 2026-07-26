"""The two reference delivery transports, in a registry resolved by config.

TASK-4 STUB: replaced wholesale in Task 5 by LogNotifier / WebhookNotifier.
Exists only so routes._parse_route can resolve notifier NAMES at load time.
"""
from __future__ import annotations

NOTIFIERS: dict[str, object] = {"log": None, "webhook": None}
