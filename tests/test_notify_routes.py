"""E-9 Task 4: routes as a versioned asset, mirroring policy/containment.yaml.
Unknown notifier names fail at LOAD, not at send -- a typo must not surface
for the first time during an expiring gate."""
from __future__ import annotations

import pytest

from sdlc.notify.contract import NotifyReason
from sdlc.notify.routes import NotifyConfigError, load_routes

ASSET = """
version: 1
base_url: null
allow_hosts: [hooks.slack.com]
default:
  primary: log
  fallback: log
gates:
  merge:
    primary: webhook:$MERGE_HOOK
    fallback: webhook:$ONCALL_HOOK
"""


def _write(tmp_path, text=ASSET):
    p = tmp_path / "notifications.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_non_escalate_reasons_go_to_primary_only(tmp_path, monkeypatch):
    monkeypatch.setenv("MERGE_HOOK", "https://hooks.slack.com/a")
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    routes = load_routes(_write(tmp_path))
    for reason in (NotifyReason.OPENED, NotifyReason.REMIND,
                   NotifyReason.EXPIRE):
        got = routes.routes_for("merge", reason)
        assert [r.target for r in got] == ["https://hooks.slack.com/a"]


def test_escalate_adds_the_fallback_route(tmp_path, monkeypatch):
    monkeypatch.setenv("MERGE_HOOK", "https://hooks.slack.com/a")
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    routes = load_routes(_write(tmp_path))
    got = routes.routes_for("merge", NotifyReason.ESCALATE)
    assert [r.target for r in got] == ["https://hooks.slack.com/a",
                                       "https://hooks.slack.com/b"]


def test_unlisted_gate_falls_back_to_default(tmp_path):
    routes = load_routes(_write(tmp_path))
    got = routes.routes_for("architecture", NotifyReason.OPENED)
    assert [(r.notifier, r.target) for r in got] == [("log", None)]


def test_unset_env_var_drops_the_route_rather_than_sending_a_literal(
        tmp_path, monkeypatch):
    """A literal '$MERGE_HOOK' POSTed to nowhere is worse than no route."""
    monkeypatch.delenv("MERGE_HOOK", raising=False)
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    routes = load_routes(_write(tmp_path))
    got = routes.routes_for("merge", NotifyReason.OPENED)
    assert got == []


def test_unknown_notifier_name_fails_at_load(tmp_path):
    bad = ASSET.replace("primary: log", "primary: carrier_pigeon")
    with pytest.raises(NotifyConfigError, match="carrier_pigeon"):
        load_routes(_write(tmp_path, bad))


def test_unsupported_version_fails_at_load(tmp_path):
    with pytest.raises(NotifyConfigError, match="version"):
        load_routes(_write(tmp_path, ASSET.replace("version: 1", "version: 9")))


def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(NotifyConfigError):
        load_routes(tmp_path / "nope.yaml")


def test_env_var_overrides_discovery(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_NOTIFY_ROUTES", str(_write(tmp_path)))
    assert load_routes().allow_hosts == ["hooks.slack.com"]


def test_shipped_asset_parses():
    """policy/notifications.yaml must always load -- it is the default."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert load_routes(root / "policy" / "notifications.yaml").version == 1
