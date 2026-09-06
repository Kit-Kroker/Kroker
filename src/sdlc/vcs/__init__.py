"""VCS activities and helpers (spec A §5)."""

from __future__ import annotations

from .git import (
    CommittedBytesInput,
    DiffInput,
    DriftInput,
    DriftReport,
    _chmod_retry,
    _git,
    _rmtree_with_retry,
    check_test_drift,
    get_task_diff,
    read_committed_bytes,
)
from .integration import (
    IntegrationHandle,
    IntegrationInput,
    MergeInput,
    MergeResult,
    VerifyBranchInput,
    VerifyResult,
    build_verification_branch,
    merge_into_integration,
    setup_integration_branch,
)
from .worktree import (
    WorktreeHandle,
    WorktreeInput,
    _clear_worktree_dir,
    _ensure_worktree,
    _find_live_worktree_for_branch,
    _worktrees_root,
    create_worktree,
)

ACTIVITIES = [
    create_worktree,
    setup_integration_branch,
    merge_into_integration,
    build_verification_branch,
    get_task_diff,
    check_test_drift,
    read_committed_bytes,
]

__all__ = [
    "ACTIVITIES",
    "CommittedBytesInput",
    "DiffInput",
    "DriftInput",
    "DriftReport",
    "IntegrationHandle",
    "IntegrationInput",
    "MergeInput",
    "MergeResult",
    "VerifyBranchInput",
    "VerifyResult",
    "WorktreeHandle",
    "WorktreeInput",
    "_chmod_retry",
    "_clear_worktree_dir",
    "_ensure_worktree",
    "_find_live_worktree_for_branch",
    "_git",
    "_rmtree_with_retry",
    "_worktrees_root",
    "build_verification_branch",
    "check_test_drift",
    "create_worktree",
    "get_task_diff",
    "merge_into_integration",
    "read_committed_bytes",
    "setup_integration_branch",
]
