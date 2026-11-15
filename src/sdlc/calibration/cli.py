"""FR-301: `sdlc calibration` -- the C7 ledger's operator surface.

The ledger records every SOFT-gate auto-approve and its realized outcome,
but nothing showed it: an operator watching nothing auto-approve had no
way to ask why. One row per bucket -- gate, bucket, verdict, n, agreement,
and the effectively-HARD flag -- answers it directly: a bucket that is not
`calibrated` can never auto-approve, whatever the gate's SOFT class says.

SC-6 extends the surface with one line: the soft-gate override rate over
the run exports the retro stage already retains -- are humans deciding
because they must, or is the policy earning trust?

Exit code 0 always: this is a read surface, not a gate. An ugly verdict is
information for the operator, never a refusal.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .metrics import OverrideRate, soft_gate_override_rate
from .models import BucketSummary
from .store import CalibrationLedger, gate_decisions_from_exports


def add_calibration_parser(sub: argparse._SubParsersAction) -> None:
    """The read-only verb. --db points at a non-default board file and
    --exports at a non-default run-export root (tests, scratch boards);
    the defaults are env-resolved, like every other store construction."""
    cal = sub.add_parser("calibration")
    cal.add_argument(
        "--db",
        default=None,
        help="board SQLite file (default: SDLC_BOARD_DB or runs/board.sqlite3)",
    )
    cal.add_argument(
        "--exports",
        default=None,
        help="run-export root holding <run_id>/summary.json "
        "(default: SDLC_EXPORT_ROOT or runs/pipeline)",
    )


def _agreement_cell(row: BucketSummary) -> str:
    """A bucket below MIN_SAMPLES never ran compute_agreement, so a 0.000
    would state an agreement the data cannot support -- the same lie
    insufficient_data exists to prevent."""
    if row.verdict.verdict == "insufficient_data":
        return "--"
    return f"{row.verdict.agreement_rate:.3f}"


def _bucket_cell(bucket_key: str) -> str:
    """The key is `model|source` (verdict.py); rendered raw it would plant a
    pipe inside a pipe-delimited row, so the display splits it."""
    return bucket_key.replace("|", " / ")


def render_calibration(rows: Sequence[BucketSummary]) -> str:
    """The plain-text table. Pure -- the verb's only formatting lives here.

    The flag column is the operator-facing answer to 'why is nothing
    auto-approving': yes == not calibrated == this bucket can never
    auto-approve a SOFT gate until it earns calibration."""
    gate_w = max(len("gate"), max(len(r.gate) for r in rows))
    bucket_w = max(len("bucket"), max(len(_bucket_cell(r.bucket_key)) for r in rows))
    verdict_w = max(len("verdict"), max(len(r.verdict.verdict) for r in rows))
    n_w = max(len("n"), max(len(str(r.verdict.n)) for r in rows))
    agreement_w = max(len("agreement"), max(len(_agreement_cell(r)) for r in rows))
    hard_w = len("effectively-HARD?")
    lines = [
        f"{'gate':<{gate_w}} | {'bucket':<{bucket_w}} | {'verdict':<{verdict_w}} | "
        f"{'n':<{n_w}} | {'agreement':<{agreement_w}} | effectively-HARD?"
    ]
    for r in rows:
        hard = "no" if r.verdict.verdict == "calibrated" else "yes"
        bucket = _bucket_cell(r.bucket_key)
        lines.append(
            f"{r.gate:<{gate_w}} | {bucket:<{bucket_w}} | "
            f"{r.verdict.verdict:<{verdict_w}} | {r.verdict.n:<{n_w}} | "
            f"{_agreement_cell(r):<{agreement_w}} | {hard:<{hard_w}}"
        )
    return "\n".join(lines)


def render_override_line(rate: OverrideRate) -> str:
    """SC-6 in one line: the rate, its numerator/denominator, and the <5%
    target. Zero decisions is the friendly empty state -- the metric is
    undefined, not 0%, which would claim a perfection no data supports.

    "Human decisions" follows the SC-6 definition decided_by != "policy":
    a timed-out SOFT gate is counted too, since the policy then failed to
    decide -- the exact failure SC-6 exists to surface."""
    if rate.rate is None:
        return "SC-6 soft-gate override rate: no SOFT gate decisions recorded (target <5%)"
    return (
        f"SC-6 soft-gate override rate: {rate.rate * 100:.1f}% "
        f"({rate.human}/{rate.total} human decisions on SOFT gates; target <5%)"
    )


def run_calibration(args: argparse.Namespace) -> str:
    """Returns the text to print (never raises a gate, never exits non-zero).

    The bucket table and the SC-6 line read different retained sources --
    the board's ledger and the run exports respectively -- so one can be
    full while the other is empty; each keeps its own friendly empty
    state rather than the verb going quiet."""
    ledger = CalibrationLedger(args.db)
    try:
        rows = ledger.summary()
    finally:
        ledger.close()
    line = render_override_line(soft_gate_override_rate(gate_decisions_from_exports(args.exports)))
    if not rows:
        return f"no samples recorded\n\n{line}"
    return f"{render_calibration(rows)}\n\n{line}"
