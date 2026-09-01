"""Route resolution from policy/notifications.yaml.

Mirrors sdlc.harness.containment's loader deliberately: same discovery order
(explicit path -> env var -> walk up for the checkout markers), same
fail-closed stance, same "a structural problem raises at load" rule. A typo in
a notifier name must surface at boot, not for the first time while a gate is
expiring.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from .contract import NotifyReason

ROUTES_PATH_ENV = "SDLC_NOTIFY_ROUTES"
_ROOT_MARKERS = ("pyproject.toml", "agents/registry.yaml")


class NotifyConfigError(Exception):
    """Any structural problem with the routes asset."""


class Route(BaseModel):
    notifier: str
    target: str | None = None


class NotifyRoutes(BaseModel):
    version: int
    base_url: str | None = None
    allow_hosts: list[str] = Field(default_factory=list)
    default: dict[str, Route] = Field(default_factory=dict)
    gates: dict[str, dict[str, Route]] = Field(default_factory=dict)

    def routes_for(self, gate: str, reason: NotifyReason) -> list[Route]:
        """Primary always; fallback additionally on ESCALATE. A tier whose
        route is absent (unset env var, not configured) is skipped."""
        table = self.gates.get(gate) or self.default
        tiers = ["primary", "fallback"] if reason is NotifyReason.ESCALATE else ["primary"]
        return [table[t] for t in tiers if t in table]


def _discover() -> Path | None:
    for d in (Path.cwd(), *Path.cwd().parents):
        if all((d / m).is_file() for m in _ROOT_MARKERS):
            return d / "policy" / "notifications.yaml"
    return None


def _resolve_path(path: str | os.PathLike | None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get(ROUTES_PATH_ENV)
    if env:
        return Path(env)
    found = _discover()
    if found is not None:
        return found
    raise NotifyConfigError(
        f"cannot locate the notification routes asset. Tried: an explicit "
        f"path; ${ROUTES_PATH_ENV}; and walking up from {Path.cwd()} for a "
        f"directory containing {' and '.join(_ROOT_MARKERS)}."
    )


def _parse_route(raw: str, where: str) -> Route | None:
    """'log' -> Route(log); 'webhook:$X' -> Route(webhook, os.environ[X]).
    Returns None when an env-var target is unset: dropping the route beats
    POSTing to the literal string."""
    from .notifiers import NOTIFIERS  # local: avoids an import cycle

    notifier, _, raw_target = raw.partition(":")
    notifier = notifier.strip()
    if notifier not in NOTIFIERS:
        raise NotifyConfigError(
            f"unknown notifier {notifier!r} at {where}; known: {', '.join(sorted(NOTIFIERS))}"
        )
    target: str | None = raw_target.strip() or None
    if target and target.startswith("$"):
        target = os.environ.get(target[1:])
        if not target:
            return None
    return Route(notifier=notifier, target=target)


def _parse_table(raw: dict, where: str) -> dict[str, Route]:
    table: dict[str, Route] = {}
    for tier in ("primary", "fallback"):
        value = (raw or {}).get(tier)
        if value is None:
            continue
        if not isinstance(value, str):
            raise NotifyConfigError(f"{where}.{tier} must be a route string, got {type(value)}")
        route = _parse_route(value, f"{where}.{tier}")
        if route is not None:
            table[tier] = route
    return table


def load_routes(path: str | os.PathLike | None = None) -> NotifyRoutes:
    p = _resolve_path(path)
    if not p.is_file():
        raise NotifyConfigError(f"notification routes asset is not a file: {p}")

    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if raw.get("version") != 1:
        raise NotifyConfigError(
            f"unsupported notifications version {raw.get('version')!r} in {p}; expected 1"
        )

    return NotifyRoutes(
        version=1,
        base_url=raw.get("base_url"),
        allow_hosts=list(raw.get("allow_hosts") or []),
        default=_parse_table(raw.get("default") or {}, "default"),
        gates={g: _parse_table(t or {}, f"gates.{g}") for g, t in (raw.get("gates") or {}).items()},
    )
