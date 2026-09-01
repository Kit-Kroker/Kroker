"""The chat mount is opt-in and can never take the dashboard down."""

from fastapi import FastAPI

from interfaces.dashboard.api import main


class FakePoller:
    async def snapshot(self):
        raise AssertionError("mounting must not query Temporal")


def test_unset_flag_means_no_mount(monkeypatch):
    monkeypatch.delenv("SDLC_CHAT_ENABLED", raising=False)
    app = FastAPI()
    assert main.mount_chat(app, FakePoller()) is False
    assert not any(getattr(r, "path", "") == "/chat" for r in app.routes)


def test_flag_set_to_anything_else_means_no_mount(monkeypatch):
    monkeypatch.setenv("SDLC_CHAT_ENABLED", "yes")
    assert main.mount_chat(FastAPI(), FakePoller()) is False


def test_flag_on_mounts_the_app(monkeypatch):
    monkeypatch.setenv("SDLC_CHAT_ENABLED", "1")
    app = FastAPI()
    assert main.mount_chat(app, FakePoller()) is True
    assert any(getattr(r, "path", "") == "/chat" for r in app.routes)


def test_a_broken_chat_config_skips_the_mount_instead_of_raising(monkeypatch, caplog):
    monkeypatch.setenv("SDLC_CHAT_ENABLED", "1")

    def boom(*a, **kw):
        from sdlc.operator.agent import ChatConfigError

        raise ChatConfigError("missing agent.yaml")

    monkeypatch.setattr(main, "build_chat_app", boom)
    app = FastAPI()
    assert main.mount_chat(app, FakePoller()) is False
    assert not any(getattr(r, "path", "") == "/chat" for r in app.routes)


def test_any_unexpected_error_also_skips_the_mount(monkeypatch):
    monkeypatch.setenv("SDLC_CHAT_ENABLED", "1")

    def boom(*a, **kw):
        raise RuntimeError("no api key")

    monkeypatch.setattr(main, "build_chat_app", boom)
    assert main.mount_chat(FastAPI(), FakePoller()) is False


def test_mounting_configures_logfire(monkeypatch):
    """Spec 12: the chat surface's traces come from instrument_pydantic_ai(),
    which lives inside configure(). A no-op without LOGFIRE_TOKEN."""
    monkeypatch.setenv("SDLC_CHAT_ENABLED", "1")
    called = []
    monkeypatch.setattr(main, "configure_logfire", lambda: called.append(True) or False)
    main.mount_chat(FastAPI(), FakePoller())
    assert called == [True]
