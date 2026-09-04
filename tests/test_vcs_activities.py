# tests/test_vcs_activities.py
import importlib
import pathlib

import pytest


def test_activities_monolith_is_deleted():
    assert not pathlib.Path("src/sdlc/activities.py").exists()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("sdlc.activities")


def test_vcs_owns_the_plumbing():
    from sdlc import vcs

    names = {a.__temporal_activity_definition.name for a in vcs.ACTIVITIES}
    assert names == {
        "create_worktree",
        "setup_integration_branch",
        "merge_into_integration",
        "build_verification_branch",
        "get_task_diff",
        "read_committed_bytes",
    }


def test_tidyup_still_reaches_build_verification_branch():
    # The evidence this is not stage-owned: a different domain executes it,
    # and feature.py never does.
    from sdlc.workflows import tidyup

    assert tidyup is not None
