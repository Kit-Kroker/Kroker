import os

# roles.py constructs pydantic_ai Agents (wrapped in TemporalAgent) at
# import time, which eagerly resolves the model and requires
# ANTHROPIC_API_KEY to be present (pre-existing design smell, tracked
# separately). Set a placeholder before importing so collection-time
# agent construction succeeds — matches the pattern used elsewhere in
# this codebase for the same reason.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy")


def test_merge_verdict_model():
    from sdlc.stages.merge.models import MergeVerdict

    v = MergeVerdict(approve=True, confidence=0.9, rationale="clean build")
    assert v.approve is True
    assert v.confidence == 0.9
    assert v.concerns == []


def test_roles_and_workflow_import_cleanly():
    import importlib

    roles = importlib.import_module("sdlc.agents.roles")
    assert hasattr(roles, "t_merge_verdict")
    assert not hasattr(roles, "t_gate")  # renamed away
    importlib.import_module("sdlc.workflows.feature")
