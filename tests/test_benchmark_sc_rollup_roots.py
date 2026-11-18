"""026 T005 chaos/edge cases: rollup accounting and the roots line.

Companion to the 026 T005 block in tests/test_benchmark_sc_rollup.py. That
file is already past the 1000-line ceiling (scripts/check_file_size.py), so
these cases live beside it rather than in it. Same contract:

    build_sc_rollup(summaries, records, *, selection_runs=, no_summary=,
                    roots=, excluded_smoke=)

Pinned here (decisions this file makes, so T006 has one answer):

- Defaults are inert. Called without the new kwargs, or with them empty
  (no_summary=[], roots=None, excluded_smoke=[]), every renderer's output is
  byte-identical, and no roots line or "no-summary" text appears at all.
  The roots line is rendered only when `roots` is given.
- Empty no_summary, when the line IS rendered, reads "no-summary: none"
  (the choice the T005 block's own clean-run test already makes), never an
  empty tail like "no-summary: ;".
- SC-1 n counts distinct run_ids, and no-summary runs count as misses
  that can lift n across the MIN_RUNS floor.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.sc_rollup import (
    MIN_RUNS,
    build_sc_rollup,
    render_sc_rollup_html,
    render_sc_rollup_json,
    render_sc_rollup_markdown,
)
from sdlc.core.models import HarnessKind, RunSummary

T = datetime(2026, 11, 18, 10, tzinfo=UTC)
RENDERERS = (render_sc_rollup_markdown, render_sc_rollup_html, render_sc_rollup_json)


def _summary(run_id, offset=0):
    """Reached merge with no gate: an SC-1 hit."""
    return RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome="deployed:pr",
        terminal_stage="deploy",
        started_at=T + timedelta(hours=offset),
        ended_at=T + timedelta(hours=offset),
        duration_s=0.0,
    )


def _rec(run_id):
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.TASK_ATTEMPT,
        stage="code",
        task_id="t01",
        attempt=0,
        role="dev",
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T, ended_at=T + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.PASS,
        kroker_commit="aaa",
    )


def _scored(n):
    summaries = [_summary(f"run-{i}", offset=i) for i in range(n)]
    return summaries, [_rec(s.run_id) for s in summaries]


def _no_summary(run_id, terminal_class, case_id="c1"):
    from sdlc.benchmarks.evidence import NoSummaryRun

    return NoSummaryRun(run_id=run_id, case_id=case_id, terminal_class=terminal_class)


def _roots(records, export, how=("runs_root", "runs_root")):
    from sdlc.runs_paths import RootsReport

    return RootsReport(records=records, export=export, records_how=how[0], export_how=how[1])


def _sc1(rollup):
    return next(r for r in rollup.rates if r.criterion == "SC-1")


# --- (1) defaults are inert ----------------------------------------------


@pytest.mark.parametrize("render", RENDERERS, ids=lambda f: f.__name__)
def test_roots_and_no_summary_defaults_render_byte_identical(render):
    summaries, records = _scored(MIN_RUNS)
    bare = build_sc_rollup(summaries, records, selection_runs=MIN_RUNS)
    empty = build_sc_rollup(
        summaries,
        records,
        selection_runs=MIN_RUNS,
        no_summary=[],
        roots=None,
        excluded_smoke=[],
    )
    assert render(bare) == render(empty)


@pytest.mark.parametrize(
    "render", (render_sc_rollup_markdown, render_sc_rollup_html), ids=lambda f: f.__name__
)
def test_roots_line_absent_when_roots_is_none_even_with_no_summary_runs(render):
    """No roots, no roots line, and no stray "no-summary:" segment. The
    no-summary runs still reach SC-1 n and the SC-2 notes."""
    summaries, records = _scored(MIN_RUNS)
    rollup = build_sc_rollup(
        summaries, records, no_summary=[_no_summary("ns-1", "crashed")], roots=None
    )
    out = render(rollup)
    assert "records: " not in out
    assert "no-summary:" not in out
    assert _sc1(rollup).n == MIN_RUNS + 1


@pytest.mark.parametrize(
    "render", (render_sc_rollup_markdown, render_sc_rollup_html), ids=lambda f: f.__name__
)
def test_roots_line_with_empty_no_summary_says_none_not_an_empty_tail(render):
    summaries, records = _scored(MIN_RUNS)
    rollup = build_sc_rollup(
        summaries, records, no_summary=[], roots=_roots("/r/b", "/r/p"), excluded_smoke=[]
    )
    out = render(rollup)
    assert "no-summary: none; smoke excluded: none" in out
    assert "no-summary: ;" not in out
    assert "smoke excluded: \n" not in out and not out.rstrip().endswith("smoke excluded:")


# --- (2) MIN_RUNS boundary -----------------------------------------------


def test_no_summary_runs_lift_sc1_n_across_the_floor_as_misses():
    assert MIN_RUNS == 5  # the boundary below is written for the 5-run floor
    summaries, records = _scored(3)
    ns = [_no_summary("ns-1", "crashed"), _no_summary("ns-2", "terminated")]
    sc1 = _sc1(build_sc_rollup(summaries, records, no_summary=ns))
    assert sc1.n == 5
    assert sc1.rate == 3 / 5  # a rate, not None; hits come only from summaries


def test_no_summary_one_short_of_the_floor_stays_na():
    summaries, records = _scored(3)
    sc1 = _sc1(build_sc_rollup(summaries, records, no_summary=[_no_summary("ns-1", "crashed")]))
    assert sc1.n == 4
    assert sc1.rate is None


# --- (3) distinct run_ids ------------------------------------------------


def test_no_summary_duplicate_run_id_counts_once_in_sc1_n():
    summaries, records = _scored(MIN_RUNS)
    ns = [_no_summary("ns-1", "crashed"), _no_summary("ns-1", "crashed")]
    sc1 = _sc1(build_sc_rollup(summaries, records, no_summary=ns))
    assert sc1.n == MIN_RUNS + 1
    assert sc1.rate == MIN_RUNS / (MIN_RUNS + 1)


# --- (4) roots line with awkward paths -------------------------------------


def test_roots_line_keeps_a_spaced_path_raw_on_one_markdown_line():
    summaries, records = _scored(MIN_RUNS)
    roots = _roots("/fleet root/runs benchmarks", "/fleet root/runs pipeline")
    md = render_sc_rollup_markdown(
        build_sc_rollup(
            summaries,
            records,
            no_summary=[_no_summary("ns-1", "timed_out")],
            roots=roots,
            excluded_smoke=["run-smoke"],
        )
    )
    lines = [ln for ln in md.splitlines() if "records: /fleet root/runs benchmarks" in ln]
    assert len(lines) == 1, md
    line = lines[0]
    assert "summaries: /fleet root/runs pipeline (runs_root)" in line
    assert "no-summary: ns-1: timed_out" in line
    assert "smoke excluded: run-smoke" in line  # the whole line, no wrap inside it


# --- (5) JSON round-trip ---------------------------------------------------


def test_no_summary_round_trips_through_json_for_every_class():
    summaries, records = _scored(MIN_RUNS)
    ns = [
        _no_summary("ns-crash", "crashed", "case-a"),
        _no_summary("ns-time", "timed_out", "case-b"),
        _no_summary("ns-term", "terminated", "case-c"),
        _no_summary("ns-miss", "summary_missing", "case-d"),
    ]
    parsed = json.loads(
        render_sc_rollup_json(
            build_sc_rollup(summaries, records, no_summary=ns, roots=_roots("/r/b", "/r/p"))
        )
    )
    assert [(x["run_id"], x["case_id"], x["terminal_class"]) for x in parsed["no_summary"]] == [
        ("ns-crash", "case-a", "crashed"),
        ("ns-time", "case-b", "timed_out"),
        ("ns-term", "case-c", "terminated"),
        ("ns-miss", "case-d", "summary_missing"),
    ]


def test_roots_and_no_summary_json_defaults_are_null_and_empty():
    summaries, records = _scored(MIN_RUNS)
    parsed = json.loads(render_sc_rollup_json(build_sc_rollup(summaries, records)))
    assert parsed["roots"] is None
    assert parsed["no_summary"] == []
    assert parsed["excluded_smoke"] == []
