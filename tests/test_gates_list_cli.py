"""`sdlc gates-list` -- read-only render of the merge-gate check manifest.

gate.py owns the manifest; the CLI renders it and never edits it. These
tests pin what the frozen contract cares about: full stdout equality with
a table rebuilt from the imported MERGE_REQUIRED_CHECKS/CheckClass
constants, declaration order, the membership-computed required column,
the four ABSOLUTE rows, the row count, and a name column that
restretches with the longest check name -- not a golden string.
"""

import asyncio
import inspect

from sdlc import cli
from sdlc.cli import _render_gates_list, build_parser
from sdlc.gate import MERGE_REQUIRED_CHECKS, CheckClass

# The four checks the manifest holds at ABSOLUTE. Two are also in
# ABSOLUTE_FLOOR; all four must render as absolute and required.
ABSOLUTE_CHECKS = (
    "build_integration_green",
    "lint_clean",
    "security_scan_collected",
    "security_no_critical",
)


def _expected_table() -> str:
    """Rebuild the expected table from the imported constants alone: header,
    then one row per MERGE_REQUIRED_CHECKS entry in declaration order, each
    classification rendered as its CheckClass value, 'yes' required."""
    name_width = max(len(name) for name in MERGE_REQUIRED_CHECKS)
    cls_width = max(
        len("classification"),
        max(len(c.value) for c in MERGE_REQUIRED_CHECKS.values()),
    )
    lines = [f"{'check':<{name_width}}  {'classification':<{cls_width}}  required-for-merge"]
    for name, classification in MERGE_REQUIRED_CHECKS.items():
        required = "yes" if name in MERGE_REQUIRED_CHECKS else "no"
        lines.append(f"{name:<{name_width}}  {classification.value:<{cls_width}}  {required}")
    return "\n".join(lines)


def _run_gates_list_main(capsys, monkeypatch) -> str:
    """Drive main() the way the console entry point does; return its stdout."""
    monkeypatch.setattr("sys.argv", ["sdlc", "gates-list"])
    asyncio.run(cli.main())
    return capsys.readouterr().out


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


def test_main_stdout_exactly_equals_table_built_from_imported_constants(capsys, monkeypatch):
    out = _run_gates_list_main(capsys, monkeypatch)
    assert out == _expected_table() + "\n"


def test_all_four_absolute_checks_appear_marked_absolute(capsys, monkeypatch):
    rows = {
        parts[0]: parts[1:]
        for parts in (
            line.split() for line in _run_gates_list_main(capsys, monkeypatch).splitlines()[1:]
        )
    }
    for name in ABSOLUTE_CHECKS:
        assert name in rows, f"{name} missing from gates-list output"
        classification, required = rows[name]
        assert classification == CheckClass.ABSOLUTE.value
        assert required == "yes"
        # The render and the manifest cannot disagree on a floor-grade row.
        assert MERGE_REQUIRED_CHECKS[name] is CheckClass.ABSOLUTE


def test_main_row_count_excluding_header_equals_manifest_len(capsys, monkeypatch):
    lines = _run_gates_list_main(capsys, monkeypatch).splitlines()
    assert len(lines) - 1 == len(MERGE_REQUIRED_CHECKS)


def test_repeated_main_invocation_prints_identical_output(capsys, monkeypatch):
    first = _run_gates_list_main(capsys, monkeypatch)
    second = _run_gates_list_main(capsys, monkeypatch)
    assert first
    assert first == second
