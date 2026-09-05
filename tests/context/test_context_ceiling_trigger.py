import pathlib

TASK_HOST_SRC = pathlib.Path("src/sdlc/workflows/task_host.py")
CODE_SRC = pathlib.Path("src/sdlc/stages/code/step.py")


def test_dev_task_consults_near_context_ceiling():
    src = TASK_HOST_SRC.read_text(encoding="utf-8") + "\n" + CODE_SRC.read_text(encoding="utf-8")
    assert "near_context_ceiling" in src, (
        "_dev_task must call run.near_context_ceiling() to force a fresh "
        "session when the harness is at/over its context budget (ADR-13)"
    )
