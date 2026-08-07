# tests/test_board_wiring.py
"""The board call sites exist and are wired to the right stages."""
import inspect

from sdlc.workflows import feature


def test_board_activity_options_have_retries():
    """Board writes are NOT best-effort: agents read tasks from the board,
    so a failed write must retry rather than be swallowed like EXPORT_ACT."""
    assert feature.BOARD_ACT["retry_policy"].maximum_attempts >= 3


def test_workflow_imports_board_activities():
    src = inspect.getsource(feature)
    for name in ("publish_artifact_version", "sync_plan_tasks",
                 "set_task_authoritative", "attach_task_evidence"):
        assert name in src, f"{name} not wired into feature.py"


def test_every_project_artifact_key_is_published():
    src = inspect.getsource(feature)
    for key in ('"requirements"', '"architecture"', '"plan"'):
        assert key in src, f"no board publish for artifact key {key}"


def test_rejected_gate_publishes_rejected_status():
    src = inspect.getsource(feature)
    assert "ArtifactStatus.REJECTED" in src, \
        "a rejected design must still be recorded as history"


def test_board_helpers_exist_on_the_workflow():
    for name in ("_board_publish", "_board_sync_tasks", "_board_task_status",
                 "_board_evidence"):
        assert hasattr(feature.FeatureWorkflow, name), f"missing {name}"
