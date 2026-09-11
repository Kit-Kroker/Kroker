"""F2 doctor: the operator-facing surface (spec sections 2, 4, 8).

Mirrors src/sdlc/capability/cli.py -- add_<name>_parser / run_<name> -- with
one deliberate divergence: run_doctor is async, because row 8 probes Temporal
and cli.py's main() is already inside an event loop.
"""

from __future__ import annotations

import json
import textwrap

from .checks import run_checks
from .models import CheckResult, Status, exit_code

_LABEL_WIDTH = 20
_INDENT = 8 + _LABEL_WIDTH


def add_doctor_parser(sub) -> None:
    d = sub.add_parser("doctor", help="diagnose this environment's setup")
    d.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit the results as JSON instead of a table",
    )
    d.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero on a warning as well as a failure",
    )


def render_table(results: list[CheckResult]) -> str:
    lines: list[str] = []
    for r in results:
        body = textwrap.fill(
            r.detail,
            width=100,
            initial_indent="",
            subsequent_indent=" " * _INDENT,
        )
        lines.append(f"[{r.status.value}] {r.name:<{_LABEL_WIDTH}} {body}".rstrip())
    counts = {s: sum(1 for r in results if r.status is s) for s in Status}
    lines.append("")
    lines.append(
        f"{counts[Status.PASS]} passed, "
        f"{counts[Status.WARN]} warning{'' if counts[Status.WARN] == 1 else 's'}, "
        f"{counts[Status.FAIL]} failed, "
        f"{counts[Status.SKIP]} skipped"
    )
    return "\n".join(lines)


def render_json(results: list[CheckResult]) -> str:
    return json.dumps(
        [{"name": r.name, "status": r.status.value, "detail": r.detail} for r in results],
        indent=2,
    )


async def run_doctor(args) -> int:
    """Run every check, print the report, return the exit code.

    Never short-circuits: reporting ALL findings at once is the whole
    difference from worker boot, which dies on the first error.
    """
    results = await run_checks()
    print(render_json(results) if args.as_json else render_table(results))
    return exit_code(results, strict=args.strict)
