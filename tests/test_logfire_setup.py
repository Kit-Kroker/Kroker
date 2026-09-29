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
    with mod.span("x", n=1):  # nullcontext — must not raise, no import
        pass


def test_span_attrs_are_metadata_only_by_convention(monkeypatch):
    # The guard is conventional (spec: counts/durations/ids only); this
    # test pins the API shape so misuse is at least grep-able.
    mod = _reload(monkeypatch, None)
    ctx = mod.span("capture", events=12, bytes=3400, session_id="abc")
    with ctx:
        pass


def test_configure_instruments_without_transcript_content(monkeypatch):
    """When Logfire is live, instrumentation must not carry payloads.

    The module docstring's "NEVER transcript payloads" holds for spans on the
    wire too: instrument_pydantic_ai() defaults to include_content=True, which
    records prompts, completions and tool arguments. configure() must opt out
    explicitly (fully honoured from pydantic-ai 2.44, which the lock pins).
    """
    import sys

    calls = {}

    class _FakeLogfire:
        def configure(self, **kw):
            calls["configure"] = kw

        def instrument_pydantic_ai(self, **kw):
            calls["instrument"] = kw

        def span(self, *a, **kw):  # pragma: no cover - not reached here
            raise AssertionError("span() not used by configure()")

    monkeypatch.setitem(sys.modules, "logfire", _FakeLogfire())
    mod = _reload(monkeypatch, "token")
    assert mod.configure() is True
    assert calls["configure"] == {"send_to_logfire": "if-token-present", "console": False}
    assert calls["instrument"] == {"include_content": False}
