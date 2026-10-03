"""E-9 Task 4: routes as a versioned asset, mirroring policy/containment.yaml.
Unknown notifier names fail at LOAD, not at send -- a typo must not surface
for the first time during an expiring gate."""

from __future__ import annotations

import logging

import pytest

from sdlc.notify.contract import NotifyReason
from sdlc.notify.routes import NotifyConfigError, load_routes, unset_env_targets

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

# Two gates plus a default table: exercises the loader's walk order
# (default first, then gates in asset order, primary before fallback) and
# the set / set-to-empty / unset split of the unset-or-empty contract.
MULTIGATE_ASSET = """
version: 1
default:
  primary: webhook:$DEFAULT_HOOK
  fallback: webhook:$DEFAULT_FALLBACK
gates:
  merge:
    primary: webhook:$MERGE_HOOK
    fallback: log
  deploy:
    primary: log
    fallback: webhook:$DEPLOY_FALLBACK
"""

# A yaml list where a route string belongs: the loader raises on this
# (structural error); unset_env_targets must skip the tier instead.
BAD_TIER_ASSET = """
version: 1
default:
  primary: log
  fallback: [webhook, $DEFAULT_FALLBACK]
gates:
  merge:
    primary: webhook:$MERGE_HOOK
    fallback: log
"""


def _write(tmp_path, text=ASSET):
    p = tmp_path / "notifications.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def _route_warnings(caplog):
    return [r for r in caplog.records if r.name == "sdlc.notify.routes"]


def test_non_escalate_reasons_go_to_primary_only(tmp_path, monkeypatch):
    monkeypatch.setenv("MERGE_HOOK", "https://hooks.slack.com/a")
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    routes = load_routes(_write(tmp_path))
    for reason in (NotifyReason.OPENED, NotifyReason.REMIND, NotifyReason.EXPIRE):
        got = routes.routes_for("merge", reason)
        assert [r.target for r in got] == ["https://hooks.slack.com/a"]


def test_escalate_adds_the_fallback_route(tmp_path, monkeypatch):
    monkeypatch.setenv("MERGE_HOOK", "https://hooks.slack.com/a")
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    routes = load_routes(_write(tmp_path))
    got = routes.routes_for("merge", NotifyReason.ESCALATE)
    assert [r.target for r in got] == ["https://hooks.slack.com/a", "https://hooks.slack.com/b"]


def test_unlisted_gate_falls_back_to_default(tmp_path):
    routes = load_routes(_write(tmp_path))
    got = routes.routes_for("architecture", NotifyReason.OPENED)
    assert [(r.notifier, r.target) for r in got] == [("log", None)]


def test_unset_env_var_drops_the_route_rather_than_sending_a_literal(tmp_path, monkeypatch):
    """A literal '$MERGE_HOOK' POSTed to nowhere is worse than no route."""
    monkeypatch.delenv("MERGE_HOOK", raising=False)
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    routes = load_routes(_write(tmp_path))
    got = routes.routes_for("merge", NotifyReason.OPENED)
    assert got == []


def test_unset_env_var_drop_logs_a_warning_naming_location_and_variable(
    tmp_path, caplog, monkeypatch
):
    """US2: the drop must not be silent. The merge gate just lost its primary
    tier mid-run; the warning names the location and the variable, never the
    value."""
    monkeypatch.delenv("MERGE_HOOK", raising=False)
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    with caplog.at_level(logging.WARNING, logger="sdlc.notify"):
        routes = load_routes(_write(tmp_path))
    recs = _route_warnings(caplog)
    assert len(recs) == 1
    text = recs[0].getMessage()
    assert "gates.merge.primary" in text
    assert "MERGE_HOOK" in text
    assert "https://hooks.slack.com/b" not in text
    assert routes.routes_for("merge", NotifyReason.OPENED) == []


def test_empty_env_var_drop_logs_the_same_warning_and_still_drops(tmp_path, caplog, monkeypatch):
    """An empty value is as good as unset: one warning naming location and
    variable, route dropped, load still succeeds."""
    monkeypatch.setenv("MERGE_HOOK", "")
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    with caplog.at_level(logging.WARNING, logger="sdlc.notify"):
        routes = load_routes(_write(tmp_path))
    recs = _route_warnings(caplog)
    assert len(recs) == 1
    text = recs[0].getMessage()
    assert "gates.merge.primary" in text
    assert "MERGE_HOOK" in text
    assert all("https://hooks.slack.com/b" not in r.getMessage() for r in recs)
    assert routes.routes_for("merge", NotifyReason.OPENED) == []


def test_both_merge_tiers_unset_log_exactly_one_warning_per_tier(tmp_path, caplog, monkeypatch):
    """Two tiers dropped, two warnings -- each tier names its own location
    and its own variable, and no record can carry a value (none is set)."""
    monkeypatch.delenv("MERGE_HOOK", raising=False)
    monkeypatch.delenv("ONCALL_HOOK", raising=False)
    with caplog.at_level(logging.WARNING, logger="sdlc.notify"):
        routes = load_routes(_write(tmp_path))
    recs = _route_warnings(caplog)
    assert len(recs) == 2
    texts = [r.getMessage() for r in recs]
    assert any("gates.merge.primary" in t and "MERGE_HOOK" in t for t in texts)
    assert any("gates.merge.fallback" in t and "ONCALL_HOOK" in t for t in texts)
    assert all("https://" not in t for t in texts)
    # both tiers dropped: the gate's own table is empty (routes_for falls
    # through to the default table, which is not this contract's business)
    assert routes.gates["merge"] == {}


def test_resolved_https_targets_log_no_warning(tmp_path, caplog, monkeypatch):
    """The warning belongs to the drop branch alone: a fully resolvable
    table loads without a word and both routes carry their values."""
    monkeypatch.setenv("MERGE_HOOK", "https://hooks.slack.com/a")
    monkeypatch.setenv("ONCALL_HOOK", "https://hooks.slack.com/b")
    with caplog.at_level(logging.WARNING, logger="sdlc.notify"):
        routes = load_routes(_write(tmp_path))
    assert _route_warnings(caplog) == []
    got = routes.routes_for("merge", NotifyReason.ESCALATE)
    assert [r.target for r in got] == ["https://hooks.slack.com/a", "https://hooks.slack.com/b"]


def test_plain_log_target_logs_no_warning(tmp_path, caplog):
    """Only a '$' target can drop. A plain 'log' tier is a complete route --
    no env var involved, so nothing is logged."""
    plain = ASSET.replace("primary: webhook:$MERGE_HOOK", "primary: log").replace(
        "fallback: webhook:$ONCALL_HOOK", "fallback: log"
    )
    with caplog.at_level(logging.WARNING, logger="sdlc.notify"):
        routes = load_routes(_write(tmp_path, plain))
    assert _route_warnings(caplog) == []
    got = routes.routes_for("merge", NotifyReason.OPENED)
    assert [(r.notifier, r.target) for r in got] == [("log", None)]


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


# --- unset_env_targets (006-B2): the doctor's pre-run listing of every
# --- $VAR target whose variable will drop its route at load time.


def test_unset_env_targets_lists_unset_targets_in_loader_order(tmp_path, monkeypatch):
    """default before gates.*, each gate in asset order, primary before
    fallback -- the same walk load_routes does. A variable set to '' is
    unset-or-empty; a resolvable webhook never appears."""
    monkeypatch.setenv("DEFAULT_HOOK", "")
    monkeypatch.delenv("DEFAULT_FALLBACK", raising=False)
    monkeypatch.setenv("MERGE_HOOK", "https://hooks.slack.com/merge")
    monkeypatch.delenv("DEPLOY_FALLBACK", raising=False)
    assert unset_env_targets(_write(tmp_path, MULTIGATE_ASSET)) == [
        ("default.primary", "DEFAULT_HOOK"),
        ("default.fallback", "DEFAULT_FALLBACK"),
        ("gates.deploy.fallback", "DEPLOY_FALLBACK"),
    ]


def test_unset_env_targets_with_every_variable_set_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("DEFAULT_HOOK", "https://hooks.slack.com/a")
    monkeypatch.setenv("DEFAULT_FALLBACK", "https://hooks.slack.com/b")
    monkeypatch.setenv("MERGE_HOOK", "https://hooks.slack.com/c")
    monkeypatch.setenv("DEPLOY_FALLBACK", "https://hooks.slack.com/d")
    assert unset_env_targets(_write(tmp_path, MULTIGATE_ASSET)) == []


def test_unset_env_targets_on_the_shipped_asset_is_empty():
    """policy/notifications.yaml routes everything to `log` -- a clean
    checkout must report nothing for the doctor to warn about."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert unset_env_targets(root / "policy" / "notifications.yaml") == []


def test_unset_env_targets_skips_a_non_string_tier_instead_of_raising(tmp_path, monkeypatch):
    """A yaml list where a route string belongs is a structural error the
    LOADER raises on; the doctor helper must not -- its WARN should still
    list the tiers it can read, so a malformed tier cannot hide a real
    unset variable elsewhere in the asset."""
    monkeypatch.delenv("MERGE_HOOK", raising=False)
    monkeypatch.delenv("DEFAULT_FALLBACK", raising=False)
    assert unset_env_targets(_write(tmp_path, BAD_TIER_ASSET)) == [
        ("gates.merge.primary", "MERGE_HOOK")
    ]
