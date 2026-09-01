import pathlib

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def test_dev_task_consults_near_context_ceiling():
    src = SRC.read_text(encoding="utf-8")
    assert "near_context_ceiling" in src, (
        "_dev_task must call run.near_context_ceiling() to force a fresh "
        "session when the harness is at/over its context budget (ADR-13)"
    )
