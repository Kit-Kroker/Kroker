"""E-84 D3: intake verifies the declared mode; the asymmetry is the point."""

from __future__ import annotations

from sdlc.context.classify import classify
from sdlc.context.models import RepoObservation
from sdlc.models import ProjectMode


def _repo(**over) -> RepoObservation:
    base = dict(
        is_git_repo=True, base_branch_resolves=True, commit_sha="a" * 40, source_file_count=12
    )
    return RepoObservation(**{**base, **over})


def test_a_healthy_brownfield_repo_is_admitted():
    v = classify(_repo(), ProjectMode.BROWNFIELD)
    assert v.ok is True
    assert v.mode is ProjectMode.BROWNFIELD
    assert v.warning == ""


def test_brownfield_against_a_non_repository_fails_closed():
    v = classify(_repo(is_git_repo=False), ProjectMode.BROWNFIELD)
    assert v.ok is False
    assert "not a git repository" in v.reason


def test_brownfield_against_an_empty_tree_fails_closed():
    v = classify(_repo(source_file_count=0), ProjectMode.BROWNFIELD)
    assert v.ok is False
    assert "no source files" in v.reason


def test_brownfield_needs_its_base_branch_to_resolve():
    v = classify(_repo(base_branch_resolves=False), ProjectMode.BROWNFIELD)
    assert v.ok is False
    assert "base branch" in v.reason


def test_greenfield_against_a_populated_tree_warns_but_continues():
    """D3's asymmetry: the greenfield claim carries no invariant, and failing
    it would break existing runs and benchmark cases for nothing."""
    v = classify(_repo(source_file_count=40), ProjectMode.GREENFIELD)
    assert v.ok is True
    assert "40 source file(s)" in v.warning


def test_greenfield_against_an_empty_tree_is_silent():
    v = classify(_repo(source_file_count=0), ProjectMode.GREENFIELD)
    assert v.ok is True
    assert v.warning == ""


def test_a_failing_verdict_keeps_the_declared_mode():
    """The verdict reports what was declared; it never silently reclassifies."""
    v = classify(_repo(is_git_repo=False), ProjectMode.BROWNFIELD)
    assert v.mode is ProjectMode.BROWNFIELD
