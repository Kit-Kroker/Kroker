"""B4: every client-side FeatureWorkflow start path consults the fleet cap.

The CLI's start branch lives inside cli.main()'s async body, which this repo
has no harness for driving (tests/test_tidyup_cli_wiring.py tests
build_parser() and asserts on source instead). The behaviour of the guard
itself is covered for real in tests/test_dashboard_fleet.py; what needs
pinning here is that the CLI actually calls it -- otherwise the check exists
and never runs, which is exactly the shape C8 named for review lenses.
"""

import inspect

from sdlc import cli


def test_the_start_command_guards_fleet_capacity():
    src = inspect.getsource(cli.main)
    assert "await guard_fleet_capacity(client)" in src, (
        "cli.py's start branch must call guard_fleet_capacity before "
        "start_workflow, or the cap exists without ever being consulted"
    )


def test_the_start_command_reports_a_refusal_instead_of_a_traceback():
    src = inspect.getsource(cli.main)
    assert "except FleetCapacityExceeded" in src, (
        "a refused start must print an operator-readable message and exit "
        "nonzero, not surface a RuntimeError traceback"
    )


def test_the_guard_runs_before_the_workflow_is_started():
    """Ordering, not just presence: guarding after start_workflow would
    admit the run and then complain about it."""
    src = inspect.getsource(cli.main)
    assert src.index("guard_fleet_capacity(client)") < src.index("FeatureWorkflow.run"), (
        "the capacity guard must precede the FeatureWorkflow start"
    )
