# tests/core/test_workflows_models_placement.py
def test_task_result_lives_with_the_orchestrator():
    from sdlc.workflows.models import SeededWork, TaskResult

    assert TaskResult.__module__ == "sdlc.workflows.models"
    assert SeededWork.__module__ == "sdlc.workflows.models"


def test_core_does_not_import_the_orchestrator_envelopes():
    import pathlib

    src = pathlib.Path("src/sdlc/core/models.py").read_text(encoding="utf-8")
    assert "TaskResult" not in src
    assert "SeededWork" not in src
