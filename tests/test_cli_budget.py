"""The start command's --budget-usd flag (011 T012, FR-006/FR-007), tested
at the parser level: rejection happens in argparse, so no Temporal
connection is ever needed to refuse a bad budget."""

import types

import pytest

from sdlc.cli import _start_config, build_parser
from sdlc.run_budget import budget_notice

# --- 011 T012 (RED): the --budget-usd flag -----------------------------------


@pytest.mark.parametrize(("raw", "expected"), [("5", 5.0), ("5.5", 5.5)])
def test_budget_usd_parses_to_float(raw, expected):
    args = build_parser().parse_args(["start", "--title", "t", "--budget-usd", raw])
    assert args.budget_usd == expected


def test_budget_usd_absent_is_none():
    args = build_parser().parse_args(["start", "--title", "t"])
    assert args.budget_usd is None


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("0", "omit it to run without a budget"),
        ("-1", "budget must be a number greater than 0"),
        ("abc", "budget must be a number greater than 0"),
    ],
)
def test_budget_usd_rejects_with_usage_error(raw, message, capsys):
    # argparse's usage error: exit code 2, the flag named on stderr, and the
    # same two messages the server answers with — nothing is started.
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["start", "--title", "t", "--budget-usd", raw])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "--budget-usd" in err
    assert message in err


# --- 011 T012 (RED): the start config carries the budget ---------------------
# The start branch's config construction is the pure _start_config(args)
# (role-model overrides + run_budget_usd). The notice print itself is
# print-level wiring (untestable without Temporal); its message source is
# pinned through budget_notice instead.


def test_start_config_carries_the_budget():
    cfg = _start_config(types.SimpleNamespace(role_model=[], budget_usd=5.0))
    assert cfg.run_budget_usd == 5.0


def test_start_config_without_a_budget_keeps_the_gate_off():
    # SC-003: absent flag -> 0.0, the sentinel the budget gate reads as off.
    cfg = _start_config(types.SimpleNamespace(role_model=[], budget_usd=None))
    assert cfg.run_budget_usd == 0.0


def test_the_config_builds_the_notice_the_cli_prints():
    # The exact line the start branch prints after the run id.
    cfg = _start_config(types.SimpleNamespace(role_model=[], budget_usd=5.0))
    notice = budget_notice(cfg)
    assert notice is not None
    assert notice.startswith("Budget $5.00 ")
