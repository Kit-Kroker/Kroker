# tests/test_containment_write_root.py
"""E-88 step 2 §A: a non-lead crew role must be able to READ the repository
it is criticising while WRITING only under the protocol tree.

The hook already decides `path_outside_worktree` as _abs_under(target,
worktree) and takes `worktree` as an explicit argument, so the confinement
root is a PARAMETER, not a predicate. Adding a fifth Predicate member was
the alternative, and Predicate's own docstring says a fifth member is
'deliberately not an expression language'.
"""

from __future__ import annotations

from sdlc.harness.base import HarnessRequest
from sdlc.harness.claude_code import ClaudeCodeHarness


def test_hook_confines_to_cwd_when_no_write_root_is_given():
    """The default must be byte-identical to today's behaviour: every
    existing caller passes no write_root and must not move."""
    cmd = ClaudeCodeHarness._hook_command(HarnessRequest(prompt="p", cwd="/srv/wt"))
    assert '--worktree "/srv/wt"' in cmd


def test_hook_confines_to_write_root_when_one_is_given():
    cmd = ClaudeCodeHarness._hook_command(
        HarnessRequest(
            prompt="p", cwd="/srv/wt", write_root="/srv/wt/.workspace/orchestration/code"
        )
    )
    assert '--worktree "/srv/wt/.workspace/orchestration/code"' in cmd
    # cwd is NOT the confinement root any more, but it is still where the
    # process runs -- the role must be able to read the repo.
    assert '--worktree "/srv/wt"' not in cmd
