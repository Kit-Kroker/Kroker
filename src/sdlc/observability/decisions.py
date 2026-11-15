"""FR-304: the decision-log read surface over the retro exports.

A closing run writes `<root>/<run_id>/summary.json` (RunSummary as data);
this module reads those summaries back as the queryable decision log —
one `DecisionLogRow` per `(gate, round)` decision, with the run context
calibration's `GateDecisionRecord` view deliberately drops.

The discipline is `calibration/store.py::gate_decisions_from_exports`'s,
verbatim: coverage is runs that closed AND exported — not a fleet census;
root defaults to SDLC_EXPORT_ROOT or ./runs/pipeline; a missing root reads
as no decisions (empty state, not an error — a fresh checkout must answer);
a summary that fails to parse or read is skipped, so a truncated export
from a crashed run cannot hide every other run's decisions; sorted glob so
the read never depends on directory order. No second store is built beside
the exports.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from ..core.models import GateOutcome, RunSummary


class DecisionLogRow(BaseModel):
    """One decision as the log reads it: the full FR-304 field set plus the
    run context. Optional fields are None on pre-FR-304 exports."""

    run_id: str
    title: str = ""
    project_key: str | None = None
    gate: str
    round: int
    policy: str
    outcome: GateOutcome | None = None
    decided_by: str
    reviewer: str | None = None
    comments: str | None = None
    decided_at: datetime | None = None
    confidence: float | None = None
    overrides: list[str] = Field(default_factory=list)


def _rows_from_summary(s: RunSummary) -> list[DecisionLogRow]:
    return [
        DecisionLogRow(
            run_id=s.run_id,
            title=s.title,
            project_key=s.project_key,
            gate=g.gate,
            round=g.round,
            policy=g.policy,
            outcome=g.outcome,
            decided_by=g.decided_by,
            reviewer=g.reviewer,
            comments=g.comments,
            decided_at=g.decided_at,
            confidence=g.confidence,
            overrides=list(g.overrides),
        )
        for g in s.gates
    ]


def decisions_from_exports(
    root: str | os.PathLike | None = None,
    *,
    run: str | None = None,
    gate: str | None = None,
    decided_by: str | None = None,
    limit: int | None = None,
) -> list[DecisionLogRow]:
    """Every decision in the readable run exports, oldest run first, then
    summary order within a run. Filters are conjunctive exact matches.
    `limit` keeps the most recent N rows (the tail of that order).
    """
    base = root if root is not None else os.environ.get("SDLC_EXPORT_ROOT", "./runs/pipeline")
    records: list[DecisionLogRow] = []
    for path in sorted(Path(base).glob("*/summary.json")):
        try:
            summary = RunSummary.model_validate_json(path.read_text(encoding="utf-8"))
        # UnicodeDecodeError (a ValueError) is the truncated-write shape a
        # crashed run leaves -- skipped like any malformed summary, never
        # fatal to the sweep.
        except (OSError, ValidationError, UnicodeDecodeError):
            continue
        records.extend(_rows_from_summary(summary))
    if run is not None:
        records = [r for r in records if r.run_id == run]
    if gate is not None:
        records = [r for r in records if r.gate == gate]
    if decided_by is not None:
        records = [r for r in records if r.decided_by == decided_by]
    if limit is not None:
        records = records[-limit:] if limit > 0 else []
    return records


def _cell(text: str | None, width: int = 40) -> str:
    if not text:
        return "-"
    return text if len(text) <= width else text[:width] + "…"


def render_decisions(rows: Sequence[DecisionLogRow]) -> str:
    """The plain-text table, the `render_calibration` style: recomputed
    column widths, `|`-separated. Pure — the verb's only formatting."""
    if not rows:
        return "no decisions recorded (runs that closed and exported under the export root)"

    def stamp(r: DecisionLogRow) -> str:
        return r.decided_at.strftime("%Y-%m-%d %H:%M") if r.decided_at is not None else "-"

    cells = [
        (
            r.run_id,
            r.gate,
            str(r.round),
            r.policy,
            r.decided_by,
            r.reviewer or "-",
            r.outcome.value if r.outcome is not None else "-",
            stamp(r),
            _cell(r.comments),
        )
        for r in rows
    ]
    heads = (
        "run",
        "gate",
        "round",
        "policy",
        "decided_by",
        "reviewer",
        "outcome",
        "decided_at",
        "comments",
    )
    widths = [max(len(h), max(len(c[i]) for c in cells)) for i, h in enumerate(heads)]
    lines = [" | ".join(f"{h:<{w}}" for h, w in zip(heads, widths, strict=True))]
    lines += [" | ".join(f"{c[i]:<{widths[i]}}" for i in range(len(heads))) for c in cells]
    return "\n".join(lines)


def add_decisions_parser(sub) -> None:
    """`sdlc decisions` — the FR-304 read surface. Package-local, like
    calibration/capability/dispositions, because cli.py sits near the
    1000-line ceiling."""
    d = sub.add_parser("decisions")
    d.add_argument("--run", default=None, help="filter: run id (exact match)")
    d.add_argument("--gate", default=None, help="filter: gate name (exact match)")
    d.add_argument(
        "--decided-by", default=None, help="filter: human | policy | timeout (exact match)"
    )
    d.add_argument("--limit", type=int, default=None, help="keep the most recent N decisions")
    d.add_argument(
        "--exports",
        default=None,
        help="run-export root holding <run_id>/summary.json "
        "(default: SDLC_EXPORT_ROOT or runs/pipeline)",
    )


def run_decisions(args: argparse.Namespace) -> str:
    """Returns the text to print. A read surface: exit 0 always, an empty
    log is the friendly line, never a refusal."""
    return render_decisions(
        decisions_from_exports(
            args.exports,
            run=args.run,
            gate=args.gate,
            decided_by=args.decided_by,
            limit=args.limit,
        )
    )
