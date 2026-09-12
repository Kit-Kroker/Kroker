"""`sdlc gates-list` -- read-only render of the merge-gate check manifest.

gate.py owns the manifest; the CLI renders it and never edits it. These
tests pin what the frozen contract cares about: declaration order, verbatim
CheckClass values, the membership-computed required column, and a name
column that restretches with the longest check name -- not a golden string.
"""

import asyncio
import inspect

from sdlc import cli
from sdlc.cli import _render_gates_list, build_parser
from sdlc.gate import MERGE_REQUIRED_CHECKS


def test_parser_accepts_the_flat_gates_list_subcommand():
    args = build_parser().parse_args(["gates-list"])
    assert args.cmd == "gates-list"


def test_gates_list_needs_no_temporal_client():
    """Without this clause main() connects before dispatch and the command
    dies without a running Temporal server, though it reads nothing but a
    module constant."""
    args = build_parser().parse_args(["gates-list"])
    assert cli._needs_temporal_client(args) is False


def test_render_is_a_header_plus_one_row_per_check_in_declaration_order():
    lines = _render_gates_list().splitlines()
    assert lines[0].split() == ["check", "classification", "required-for-merge"]
    body = lines[1:]
    assert len(body) == len(MERGE_REQUIRED_CHECKS)
    for row, (name, classification) in zip(body, MERGE_REQUIRED_CHECKS.items(), strict=True):
        assert row.split() == [name, classification.value, "yes"]


def test_render_is_byte_identical_across_invocations():
    assert _render_gates_list() == _render_gates_list()


def test_name_column_width_follows_the_longest_check_name():
    rows = _render_gates_list().splitlines()[1:]
    width = max(len(name) for name in MERGE_REQUIRED_CHECKS)
    for row, name in zip(rows, MERGE_REQUIRED_CHECKS, strict=True):
        assert row[:width] == name.ljust(width)
        assert row[width : width + 2] == "  "


def test_render_is_a_zero_argument_module_level_pure_function():
    assert len(inspect.signature(_render_gates_list).parameters) == 0
    assert _render_gates_list.__module__ == "sdlc.cli"


def test_main_dispatch_lazily_imports_the_manifest_and_prints_the_render():
    """main()'s async body has no drive harness (the fleet-capacity wiring
    test pins this branch by source too); the driveable path is covered by
    the in-process invocation below."""
    src = inspect.getsource(cli.main)
    head = src.split('args.cmd == "gates-list"', 1)[1]
    branch = head.split("if args.cmd ==", 1)[0]
    assert "from .gate import" in branch
    assert "MERGE_REQUIRED_CHECKS" in branch
    assert "CheckClass" in branch
    assert "print(_render_gates_list())" in branch


def test_main_invocation_prints_the_table(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["sdlc", "gates-list"])
    asyncio.run(cli.main())
    assert capsys.readouterr().out == _render_gates_list() + "\n"
