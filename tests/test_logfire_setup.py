"""E-38: Logfire slice is env-gated and a strict no-op without a token."""
import importlib

import sdlc.observability.logfire_setup as lf


def _reload(monkeypatch, token):
    if token is None:
        monkeypatch.delenv("LOGFIRE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("LOGFIRE_TOKEN", token)
    return importlib.reload(lf)


def test_disabled_without_token(monkeypatch):
    mod = _reload(monkeypatch, None)
    assert mod.configure() is False
    with mod.span("x", n=1):        # nullcontext — must not raise, no import
        pass


def test_span_attrs_are_metadata_only_by_convention(monkeypatch):
    # The guard is conventional (spec: counts/durations/ids only); this
    # test pins the API shape so misuse is at least grep-able.
    mod = _reload(monkeypatch, None)
    ctx = mod.span("capture", events=12, bytes=3400, session_id="abc")
    with ctx:
        pass
