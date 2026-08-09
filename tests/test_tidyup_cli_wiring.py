"""E-44's operator surface. Mirrors tests/test_triage_cli_wiring.py."""
from datetime import datetime, timezone

import pytest

from sdlc.cli import tidyup_workflow_id


def test_workflow_id_is_per_run_not_per_repository():
    """Same reason triage_workflow_id carries a stamp (E-42 D5): Temporal
    refuses to start a workflow whose id is already RUNNING, so a bare
    tidyup-<slug> would let one tidy-up parked on the gate block the next."""
    now = datetime(2026, 8, 9, 10, 15, 0, tzinfo=timezone.utc)
    assert tidyup_workflow_id("/x/my-repo", now) == \
        "tidyup-my-repo-20260809T101500Z"


def test_workflow_id_slugifies_the_basename():
    now = datetime(2026, 8, 9, 10, 15, 0, tzinfo=timezone.utc)
    assert tidyup_workflow_id("/x/My Repo!", now).startswith("tidyup-my-repo-")


def test_two_ids_for_one_repo_differ():
    a = tidyup_workflow_id("/x/r", datetime(2026, 8, 9, 10, 15, 0,
                                            tzinfo=timezone.utc))
    b = tidyup_workflow_id("/x/r", datetime(2026, 8, 9, 10, 16, 0,
                                            tzinfo=timezone.utc))
    assert a != b


def test_child_triage_ids_do_not_collide_with_a_standalone_triage():
    """TidyUpWorkflow derives its children as <id>-triage-before/-after."""
    now = datetime(2026, 8, 9, 10, 15, 0, tzinfo=timezone.utc)
    assert not tidyup_workflow_id("/x/r", now).startswith("triage-")


def test_worker_registers_the_workflow_and_the_activity():
    import inspect

    from sdlc import worker
    src = inspect.getsource(worker)
    assert "TidyUpWorkflow" in src
    assert "build_verification_branch" in src


def test_approve_reaches_a_tidyup_workflow_unchanged():
    """channels/transport.py resolves and submits BY NAME and imports nothing
    from FeatureWorkflow -- so the existing approve verb already works against
    TidyUpWorkflow. This test exists so a future refactor cannot quietly
    break that."""
    import inspect

    from sdlc.channels import transport
    src = inspect.getsource(transport)
    assert "FeatureWorkflow" not in src


@pytest.mark.parametrize("argv,expected", [
    (["tidyup", "--repo", "/x/r"], {"repo": "/x/r", "max_fix_runs": 10}),
    (["tidyup", "--repo", "/x/r", "--max-fix-runs", "3"],
     {"repo": "/x/r", "max_fix_runs": 3}),
])
def test_parser_accepts_the_tidyup_flags(argv, expected):
    """Built by calling the same parser main() builds -- extract it into a
    module-level build_parser() if it is still inline in main()."""
    from sdlc.cli import build_parser
    args = build_parser().parse_args(argv)
    assert args.cmd == "tidyup"
    assert args.repo == expected["repo"]
    assert args.max_fix_runs == expected["max_fix_runs"]


def test_parser_accepts_select_and_show():
    from sdlc.cli import build_parser
    a = build_parser().parse_args(
        ["tidyup", "select", "--id", "w", "--identities", "a,b"])
    assert a.tidyup_cmd == "select" and a.identities == "a,b"
    b = build_parser().parse_args(["tidyup", "show", "--id", "w"])
    assert b.tidyup_cmd == "show"
