# tests/test_board_wiring.py
"""The board call sites exist and are wired to the right stages."""

import inspect

from sdlc.workflows import board_host, feature


def test_board_activity_options_have_retries():
    """Board writes are NOT best-effort: agents read tasks from the board,
    so a failed write must retry rather than be swallowed like EXPORT_ACT."""
    assert board_host.BOARD_ACT["retry_policy"].maximum_attempts >= 3


def test_workflow_imports_board_activities():
    # Spec A "stage surgery": the board wiring moved off feature.py onto the
    # BoardHost mixin (composed into FeatureWorkflow via its MRO).
    src = inspect.getsource(board_host)
    for name in (
        "publish_artifact_version",
        "sync_plan_tasks",
        "set_task_authoritative",
        "attach_task_evidence",
    ):
        assert name in src, f"{name} not wired into board_host.py"


def test_every_project_artifact_key_is_published():
    src = inspect.getsource(feature)
    for key in ('"requirements"', '"architecture"', '"plan"'):
        assert key in src, f"no board publish for artifact key {key}"


def test_rejected_gate_publishes_rejected_status():
    # The publish (and its REJECTED status) lives in BoardHost._board_publish.
    src = inspect.getsource(board_host)
    assert "ArtifactStatus.REJECTED" in src, "a rejected design must still be recorded as history"


def test_board_helpers_exist_on_the_workflow():
    for name in ("_board_publish", "_board_sync_tasks", "_board_task_status", "_board_evidence"):
        assert hasattr(feature.FeatureWorkflow, name), f"missing {name}"
