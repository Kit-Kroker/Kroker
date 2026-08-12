"""E-46 scan activities (FR-912). One activity per computed signal,
deliberately: a signal that crashes or times out yields not_collected for
ITSELF while every other signal still reports (E-41 spec D3).

Every signal reads blob bytes at the pinned commit. NOTHING here executes the
assessed repository's code -- the init phase's build probe remains the only
place that happens (NFR-9, E-46 D12).
"""
from __future__ import annotations

import logging

from pydantic import BaseModel
from temporalio import activity

from ..activities import _git

_log = logging.getLogger(__name__)


class AssessmentTreeInput(BaseModel):
    repo_dir: str
    commit_sha: str


class AssessmentTree(BaseModel):
    tree_hash: str


@activity.defn
async def assessment_resolve_tree(
        inp: AssessmentTreeInput) -> AssessmentTree:
    """The tree object of the pinned commit, which is what the scan memo keys
    on (D10).

    Two commits can share a tree -- amend, rebase, cherry-pick -- and a
    commit-keyed cache would miss on all of them, which E-54's incremental
    re-assessment and E-44's before/after re-triage both lean on.

    Deliberately NOT never-raising, matching triage_resolve_commit: a commit
    that does not resolve is not a not_collected dimension, it is the absence
    of the tree the whole artifact claims to describe.
    """
    proc = _git(["rev-parse", "--verify", f"{inp.commit_sha}^{{tree}}"],
                cwd=inp.repo_dir)
    if proc.returncode != 0:
        raise RuntimeError(
            f"commit {inp.commit_sha!r} does not resolve to a tree in "
            f"{inp.repo_dir}: {proc.stderr.strip()}")
    return AssessmentTree(tree_hash=proc.stdout.strip())
