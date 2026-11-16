import pathlib

WORKER_SRC = pathlib.Path("src/sdlc/worker.py")


def test_worker_validates_registry_at_boot():
    src = WORKER_SRC.read_text(encoding="utf-8")
    assert "validate_registry" in src, (
        "worker.main() must validate the agent registry at boot so a "
        "same-family developer/reviewer config fails closed (FR-204)"
    )
    assert "load_registry(" in src


def test_worker_validation_runs_before_worker_run():
    """The validation call must precede the worker run loop so a bad config
    never reaches it. 024 T009: the single `await worker.run()` became
    `await asyncio.gather(*(w.run() ...))` (pool modes), so the anchor is
    the gather."""
    src = WORKER_SRC.read_text(encoding="utf-8")
    assert src.index("validate_registry(") < src.index("asyncio.gather(")
