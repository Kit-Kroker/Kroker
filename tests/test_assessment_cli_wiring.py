"""E-45's operator surface. Mirrors tests/test_tidyup_cli_wiring.py."""

from datetime import UTC, datetime

import pytest

from sdlc.cli import assess_workflow_id, build_parser


def test_workflow_id_is_per_run_not_per_repository():
    """Same reason triage_workflow_id carries a stamp (E-42 D5): Temporal
    refuses to start a workflow whose id is already RUNNING, so a bare
    assess-<slug> would let one assessment parked on the child's readiness
    gate block the next."""
    now = datetime(2026, 8, 10, 10, 15, 0, tzinfo=UTC)
    assert assess_workflow_id("/x/my-repo", now) == "assess-my-repo-20260810T101500Z"


def test_workflow_id_slugifies_the_basename():
    now = datetime(2026, 8, 10, 10, 15, 0, tzinfo=UTC)
    assert assess_workflow_id("/x/My Repo!", now).startswith("assess-my-repo-")


def test_two_ids_for_one_repo_differ():
    a = assess_workflow_id("/x/r", datetime(2026, 8, 10, 10, 15, 0, tzinfo=UTC))
    b = assess_workflow_id("/x/r", datetime(2026, 8, 10, 10, 16, 0, tzinfo=UTC))
    assert a != b


def test_child_triage_id_does_not_collide_with_a_standalone_triage():
    """AssessmentWorkflow derives its child as <id>-triage."""
    now = datetime(2026, 8, 10, 10, 15, 0, tzinfo=UTC)
    assert not assess_workflow_id("/x/r", now).startswith("triage-")


def test_worker_registers_the_workflow():
    import inspect

    from sdlc import worker

    assert "AssessmentWorkflow" in inspect.getsource(worker)


@pytest.mark.parametrize(
    "argv,expected",
    [
        (
            ["assess", "--repo", "/x/r"],
            {
                "repo": "/x/r",
                "commit": "HEAD",
                "no_build_probe": False,
                "advisory_source": "none",
                "project": None,
            },
        ),
        (
            ["assess", "--repo", "/x/r", "--no-build-probe"],
            {"repo": "/x/r", "no_build_probe": True},
        ),
        (["assess", "--repo", "/x/r", "--commit", "abc123"], {"repo": "/x/r", "commit": "abc123"}),
        (["assess", "--repo", "/x/r", "--advisory-source", "osv"], {"advisory_source": "osv"}),
        (
            ["assess", "--repo", "/x/r", "--project", "payments-service"],
            {"project": "payments-service"},
        ),
    ],
)
def test_parser_accepts_the_assess_flags(argv, expected):
    args = build_parser().parse_args(argv)
    assert args.cmd == "assess"
    for key, value in expected.items():
        assert getattr(args, key) == value


def test_parser_accepts_assess_show():
    args = build_parser().parse_args(["assess", "show", "--id", "assess-r-x"])
    assert args.cmd == "assess"
    assert args.assess_cmd == "show"
    assert args.id == "assess-r-x"


def test_bare_assess_has_no_subcommand():
    args = build_parser().parse_args(["assess", "--repo", "/x/r"])
    assert args.assess_cmd is None


def test_parser_accepts_assess_show_json():
    """The raw dump stays reachable; the summary is the new default."""
    args = build_parser().parse_args(["assess", "show", "--id", "assess-r-x", "--json"])
    assert args.as_json is True
    assert build_parser().parse_args(["assess", "show", "--id", "assess-r-x"]).as_json is False
