"""FR-301: `sdlc calibration` -- the C7 ledger's operator read surface.

The ledger records every SOFT-gate auto-approve and its realized outcome,
but nothing showed it. These tests pin the two halves of the verb:
store.summary() must report the same windowed verdict the gate's decision
path computes (never a second statistic), and the render must answer the
operator's actual question -- why is nothing auto-approving -- with one
row per bucket and the effectively-HARD flag on anything not calibrated.
Exit code is pinned by construction: run_calibration returns a string and
main() returns without SystemExit, so the verb can never gate anyone.
"""

import argparse
import asyncio
import inspect
import re
from pathlib import Path

import pytest

from sdlc import cli
from sdlc.calibration.cli import add_calibration_parser, render_calibration, run_calibration
from sdlc.calibration.models import CalibrationSample, LabelSource
from sdlc.calibration.store import CalibrationLedger
from sdlc.calibration.verdict import MIN_SAMPLES, WINDOW, bucket_key

BK = bucket_key("some/model", LabelSource.PRODUCTION_PROXY)
OTHER = bucket_key("other/model", LabelSource.PRODUCTION_PROXY)
JUDGE = bucket_key("some/model", LabelSource.BENCHMARK)


@pytest.fixture
def ledger(tmp_path):
    led = CalibrationLedger(db=tmp_path / "board.sqlite3")
    yield led
    led.close()


def _sample(conf: float, label: float, bk: str = BK, gate: str = "architecture"):
    return CalibrationSample(
        gate=gate, bucket_key=bk, confidence=conf, outcome_label=label, run_id="r1"
    )


def _seed(tmp_path, batches) -> Path:
    """Seed a ledger on disk and close it, so the verb opens its own
    connection the way an operator invocation would."""
    db = tmp_path / "board.sqlite3"
    led = CalibrationLedger(db=db)
    for batch in batches:
        led.append(batch)
    led.close()
    return db


def _ns(db) -> argparse.Namespace:
    return argparse.Namespace(db=str(db))


def _bucket_cell(bucket_key: str) -> str:
    """Rebuild the render's bucket cell from the constants: the key is
    `model|source`, and the display splits it so the pipe stays a column
    separator. Duplicated here on purpose -- if the render rule drifts,
    this pin fails rather than silently tracking it."""
    return bucket_key.replace("|", " / ")


# --- store.summary: the same verdict the gate reads, one row per bucket ----


def test_summary_on_an_empty_ledger_is_empty(ledger):
    assert ledger.summary() == []


def test_summary_enumerates_each_distinct_bucket_once(ledger):
    ledger.append([_sample(0.9, 0.9) for _ in range(2)])  # architecture | BK
    ledger.append([_sample(0.9, 0.9, gate="plan") for _ in range(2)])  # plan | BK
    ledger.append([_sample(0.9, 0.9, bk=JUDGE)])  # architecture | JUDGE
    rows = ledger.summary()
    got = [(r.gate, r.bucket_key) for r in rows]
    assert sorted(got) == sorted([("architecture", BK), ("plan", BK), ("architecture", JUDGE)])
    assert len(got) == len(set(got))


def test_summary_rows_are_ordered_by_gate_then_bucket(ledger):
    ledger.append([_sample(0.9, 0.9), _sample(0.9, 0.9, bk=OTHER), _sample(0.9, 0.9, bk=JUDGE)])
    got = [(r.gate, r.bucket_key) for r in ledger.summary()]
    assert got == sorted(got)


def test_a_calibrated_bucket_reads_calibrated_with_its_counts(ledger):
    ledger.append([_sample(0.9, 0.9) for _ in range(MIN_SAMPLES)])
    (row,) = ledger.summary()
    assert (row.gate, row.bucket_key) == ("architecture", BK)
    assert row.verdict.verdict == "calibrated"
    assert row.verdict.n == MIN_SAMPLES
    assert row.verdict.agreement_rate == 1.0
    assert row.last_sample_at is not None


def test_a_three_sample_bucket_is_insufficient_data(ledger):
    ledger.append([_sample(0.9, 0.9) for _ in range(3)])
    (row,) = ledger.summary()
    assert row.verdict.verdict == "insufficient_data"
    assert row.verdict.n == 3


def test_a_disagreeing_bucket_reads_uncalibrated(ledger):
    ledger.append([_sample(0.9, 0.1) for _ in range(MIN_SAMPLES)])
    (row,) = ledger.summary()
    assert row.verdict.verdict == "uncalibrated"
    assert row.verdict.agreement_rate == 0.0


def test_summary_n_is_the_window_not_the_table(ledger):
    """Ruling OQ5: the table keeps superseded samples but the verdict READS
    the window -- so the operator surface must show the window's n, the
    same number the gate's decision used, not the table's."""
    ledger.append([_sample(0.9, 0.9) for _ in range(WINDOW + 5)])
    (row,) = ledger.summary()
    assert row.verdict.n == WINDOW


def test_last_sample_at_tracks_the_buckets_latest_sample(ledger):
    ledger.append([_sample(0.9, 0.9) for _ in range(2)])
    ledger.append([_sample(0.9, 0.9, gate="plan") for _ in range(2)])
    rows = {r.gate: r for r in ledger.summary()}
    assert rows["architecture"].last_sample_at is not None
    assert rows["plan"].last_sample_at is not None
    assert rows["architecture"].last_sample_at <= rows["plan"].last_sample_at


def test_the_store_never_imports_cli_code():
    """Layering: store.py is pure SQLite, the verb formats. A store that
    reaches for CLI rendering inverts the dependency."""
    src = Path("src/sdlc/calibration/store.py").read_text(encoding="utf-8")
    offenders = [ln for ln in src.splitlines() if "import" in ln and re.search(r"\bcli\b", ln)]
    assert offenders == []


# --- the verb: parser wiring, empty-ledger line, the table -----------------


def test_parser_accepts_the_calibration_verb_and_its_db_flag():
    args = cli.build_parser().parse_args(["calibration"])
    assert args.cmd == "calibration"
    assert args.db is None  # default: the env-resolved board DB
    args = cli.build_parser().parse_args(["calibration", "--db", "/tmp/x.sqlite3"])
    assert args.db == "/tmp/x.sqlite3"


def test_the_calibration_subparser_is_registered_by_the_package_hook():
    """The registration lives in calibration/cli.py behind the same hook
    pattern as maintain/capability -- cli.py sits near the line ceiling."""
    sub = argparse.ArgumentParser().add_subparsers(dest="cmd")
    add_calibration_parser(sub)
    assert sub.choices["calibration"] is not None


def test_calibration_needs_no_temporal_client():
    """A read over local SQLite; without this clause main() connects before
    dispatch and the verb dies without a Temporal server."""
    assert cli._needs_temporal_client(cli.build_parser().parse_args(["calibration"])) is False


def test_main_dispatches_calibration_before_the_worker_import():
    """main() builds the agent registry (which fails closed without provider
    keys) after the doctor dispatch; the calibration verb is local read-only
    work and must answer on a keyless machine too. Exit 0 ALWAYS is the
    contract -- the operator asking why nothing auto-approves may be on
    precisely the box that has no keys."""
    src = inspect.getsource(cli.main)
    assert src.index('args.cmd == "calibration"') < src.index("from .worker import")


def test_run_calibration_on_an_empty_ledger_is_the_friendly_line(tmp_path):
    assert run_calibration(_ns(tmp_path / "empty.sqlite3")) == "no samples recorded"


def test_main_invocation_prints_the_friendly_line_and_exits_clean(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        "sys.argv", ["sdlc", "calibration", "--db", str(tmp_path / "board.sqlite3")]
    )
    asyncio.run(cli.main())  # returning normally == exit code 0
    assert capsys.readouterr().out == "no samples recorded\n"


def test_the_seeded_table_answers_the_operators_question(tmp_path):
    """The three verdicts an operator actually meets: a bucket that earns
    auto-approval, a cold-start bucket, and a bucket whose confidence lied
    -- the last two flagged effectively-HARD, i.e. never auto-approving
    however SOFT the gate class is."""
    db = _seed(
        tmp_path,
        [
            [_sample(0.9, 0.9) for _ in range(MIN_SAMPLES)],  # calibrated
            [_sample(0.9, 0.9, bk=JUDGE) for _ in range(3)],  # insufficient_data
            [_sample(0.9, 0.1, bk=OTHER) for _ in range(MIN_SAMPLES)],  # uncalibrated
        ],
    )
    lines = run_calibration(_ns(db)).splitlines()
    header = [cell.strip() for cell in lines[0].split("|")]
    assert header == ["gate", "bucket", "verdict", "n", "agreement", "effectively-HARD?"]

    rows = {}
    for line in lines[1:]:
        cells = [cell.strip() for cell in line.split("|")]
        rows[(cells[0], cells[1])] = cells[2:]
    assert len(rows) == 3
    assert rows[("architecture", _bucket_cell(BK))] == [
        "calibrated",
        str(MIN_SAMPLES),
        "1.000",
        "no",
    ]
    assert rows[("architecture", _bucket_cell(JUDGE))] == [
        "insufficient_data",
        "3",
        "--",
        "yes",
    ]
    assert rows[("architecture", _bucket_cell(OTHER))] == [
        "uncalibrated",
        str(MIN_SAMPLES),
        "0.000",
        "yes",
    ]


def test_the_agreement_cell_of_an_uncomputed_verdict_is_not_a_zero(tmp_path):
    """A bucket below MIN_SAMPLES never ran compute_agreement, so rendering
    0.000 would state an agreement the data cannot support -- the same lie
    insufficient_data exists to prevent. It renders as '--' instead."""
    db = _seed(tmp_path, [[_sample(0.9, 0.9) for _ in range(3)]])
    assert "--" in run_calibration(_ns(db))


def test_render_is_byte_identical_across_invocations(ledger):
    ledger.append([_sample(0.9, 0.9) for _ in range(MIN_SAMPLES)])
    ledger.append([_sample(0.9, 0.1, bk=OTHER) for _ in range(3)])
    rows = ledger.summary()
    assert render_calibration(rows) == render_calibration(rows)


def test_the_rendered_table_has_one_row_per_bucket(tmp_path):
    db = _seed(
        tmp_path,
        [
            [_sample(0.9, 0.9) for _ in range(2)],
            [_sample(0.9, 0.9, gate="plan") for _ in range(2)],
        ],
    )
    lines = run_calibration(_ns(db)).splitlines()
    assert len(lines) == 3  # header + two buckets
