"""026 T005 (RED): rollup no-summary accounting and the roots line.

Split out of tests/test_benchmark_sc_rollup.py at the reviewer's request
(the parent crossed the 1000-line ceiling; T009 and T023 add more rollup
tests, so the 026 block gets its own seam here). Shared fixture helpers
are imported from the parent module; the contract is the one pinned in
tasks.md T005 and data-model.md:

  build_sc_rollup(summaries, records, *, selection_runs=, no_summary=,
                  roots=, excluded_smoke=)

- SC-1 n = summaries that records vouch for plus every no-summary run;
  a no-summary run is always a miss. A summary with no records stays
  under the commit flag and is NOT in n.
- SC-2 / SC-2-all notes name each no-summary run as not measured:
  "no summary, not measured: <run_id>: <class>, <run_id>: <class>"
- every renderer carries the roots line (see _roots_line).
"""

from __future__ import annotations

from test_benchmark_sc_rollup import (
    MIN_RUNS,
    _commit_rec,
    _n_summaries,
    _ot_runs,
    _rate,
    _summary,
    build_sc_rollup,
    render_sc_rollup_html,
    render_sc_rollup_json,
    render_sc_rollup_markdown,
)


def _no_summary(run_id, terminal_class, case_id="c1"):
    from sdlc.benchmarks.evidence import NoSummaryRun

    return NoSummaryRun(run_id=run_id, case_id=case_id, terminal_class=terminal_class)


def _roots(records="/fleet/runs/benchmarks", export="/fleet/runs/pipeline", how=("runs_root",) * 2):
    from sdlc.runs_paths import RootsReport

    return RootsReport(records=records, export=export, records_how=how[0], export_how=how[1])


def _scored(summaries):
    """One record per summary, so each summary is a scored run (records-derived n)."""
    return [_commit_rec(s.run_id, "aaa") for s in summaries]


def _roots_line(roots, k, n, no_summary, smoke):
    ns = ", ".join(f"{x.run_id}: {x.terminal_class}" for x in no_summary) or "none"
    sm = ", ".join(smoke) or "none"
    return (
        f"records: {roots.records} ({roots.records_how}); "
        f"summaries: {roots.export} ({roots.export_how}); "
        f"{k} of {n} scored runs summarized; "
        f"no-summary: {ns}; smoke excluded: {sm}"
    )


def _fleet_rollup():
    """5 summarized runs that reached merge unattended, 2 no-summary runs,
    1 smoke run excluded upstream."""
    summaries = _n_summaries(MIN_RUNS)
    ns = [_no_summary("run-crash", "crashed"), _no_summary("run-term", "terminated")]
    roots = _roots()
    rollup = build_sc_rollup(
        summaries,
        _scored(summaries),
        selection_runs=MIN_RUNS + 2,
        no_summary=ns,
        roots=roots,
        excluded_smoke=["run-smoke"],
    )
    return rollup, summaries, ns, roots


def test_no_summary_runs_join_sc1_n_as_misses():
    rollup, summaries, ns, _ = _fleet_rollup()
    sc1 = _rate(rollup, "SC-1")
    assert sc1.n == len(summaries) + len(ns) == 7
    # the 5 summarized runs all hit; the 2 no-summary runs are misses
    assert sc1.rate == 5 / 7


def test_no_summary_does_not_change_sc1_hits():
    summaries = _n_summaries(MIN_RUNS)
    base = _rate(build_sc_rollup(summaries, _scored(summaries), no_summary=[]), "SC-1")
    more = _rate(
        build_sc_rollup(
            summaries,
            _scored(summaries),
            no_summary=[_no_summary(f"ns-{i}", "crashed") for i in range(5)],
        ),
        "SC-1",
    )
    assert (base.n, base.rate) == (5, 1.0)
    assert (more.n, more.rate) == (10, 0.5)  # hits stay 5


def test_no_summary_runs_lift_sc1_across_the_floor_as_misses():
    """FR-003's blind spot: 3 summaries is below MIN_RUNS (n/a), but 3
    summaries + 2 no-summary runs is a measured fleet of 5 — a RATE at
    3/5, never n/a, because crashed runs count in the denominator."""
    summaries = _n_summaries(3)
    below = build_sc_rollup(summaries, _scored(summaries), no_summary=[])
    assert _rate(below, "SC-1").rate is None
    rollup = build_sc_rollup(
        summaries,
        _scored(summaries),
        no_summary=[_no_summary("run-crash", "crashed"), _no_summary("run-term", "terminated")],
    )
    sc1 = _rate(rollup, "SC-1")
    assert sc1.n == 5
    assert sc1.rate == 3 / 5


def test_no_summary_runs_are_not_measured_in_sc2_and_sc2_all_with_their_class():
    rollup, _, _, _ = _fleet_rollup()
    want = "no summary, not measured: run-crash: crashed, run-term: terminated"
    md = render_sc_rollup_markdown(rollup)
    for name in ("SC-2", "SC-2-all"):
        r = _rate(rollup, name)
        assert want in r.note, name
        assert f"- **{name}**: " in md
    assert md.count(want) == 2


def test_no_summary_runs_add_nothing_to_sc2_n():
    summaries = _ot_runs(5)
    rollup = build_sc_rollup(
        summaries, _scored(summaries), no_summary=[_no_summary("ns-1", "timed_out")]
    )
    assert _rate(rollup, "SC-2").n == 5
    assert _rate(rollup, "SC-2-all").n == 5
    assert "ns-1: timed_out" in _rate(rollup, "SC-2-all").note


def test_no_summary_sc1_n_excludes_a_summary_with_no_records():
    """R2: the denominator is the distinct run_ids of (non-smoke) records. A
    summary no record vouches for stays under the commit flag only."""
    summaries = _n_summaries(MIN_RUNS)
    orphan = _summary("orphan", offset=99)
    rollup = build_sc_rollup(
        [*summaries, orphan],
        _scored(summaries),
        no_summary=[_no_summary("run-crash", "crashed")],
    )
    sc1 = _rate(rollup, "SC-1")
    assert sc1.n == 6  # 5 scored summaries + 1 no-summary run, not the orphan
    assert sc1.rate == 5 / 6  # the orphan reached merge but is no hit either
    assert "1 run(s) commit unknown" in rollup.commit_flag


def test_roots_line_renders_in_markdown():
    rollup, summaries, ns, roots = _fleet_rollup()
    line = _roots_line(roots, len(summaries), 7, ns, ["run-smoke"])
    assert line == (
        "records: /fleet/runs/benchmarks (runs_root); "
        "summaries: /fleet/runs/pipeline (runs_root); "
        "5 of 7 scored runs summarized; "
        "no-summary: run-crash: crashed, run-term: terminated; "
        "smoke excluded: run-smoke"
    )
    assert line in render_sc_rollup_markdown(rollup)


def test_roots_line_renders_in_html():
    rollup, summaries, ns, roots = _fleet_rollup()
    assert _roots_line(roots, len(summaries), 7, ns, ["run-smoke"]) in render_sc_rollup_html(rollup)


def test_roots_line_and_fields_render_in_json():
    import json

    rollup, summaries, ns, roots = _fleet_rollup()
    text = render_sc_rollup_json(rollup)
    parsed = json.loads(text)
    assert parsed["roots"] == {
        "records": "/fleet/runs/benchmarks",
        "export": "/fleet/runs/pipeline",
        "records_how": "runs_root",
        "export_how": "runs_root",
    }
    assert [(x["run_id"], x["terminal_class"]) for x in parsed["no_summary"]] == [
        ("run-crash", "crashed"),
        ("run-term", "terminated"),
    ]
    assert parsed["excluded_smoke"] == ["run-smoke"]
    assert _roots_line(roots, len(summaries), 7, ns, ["run-smoke"]) in text


def test_roots_line_names_each_how_and_says_none_when_clean():
    summaries = _n_summaries(MIN_RUNS)
    roots = _roots("/x/benchmarks", "/y", how=("explicit", "default"))
    rollup = build_sc_rollup(summaries, _scored(summaries), no_summary=[], roots=roots)
    line = (
        "records: /x/benchmarks (explicit); summaries: /y (default); "
        "5 of 5 scored runs summarized; no-summary: none; smoke excluded: none"
    )
    for out in (render_sc_rollup_markdown(rollup), render_sc_rollup_html(rollup)):
        assert line in out
