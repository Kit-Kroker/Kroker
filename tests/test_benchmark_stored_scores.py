"""013 T003 (RED): contract §12 run-level figures on the stored records.

Stored test: reads `runs/benchmarks` IN PLACE, read-only, and is skipped
when the records root has no ``*.jsonl``. The root is resolved exactly as
``tests/test_benchmark_legacy_records.py`` resolves it (the recorder's
``_root``; ``SDLC_BENCHMARKS_ROOT`` override, default ``runs/benchmarks``),
and the same removed-``herdr``-harness ValidationError shape is tolerated
and never re-counted.

Names: sdlc.benchmarks.runs (data-model.md §1). Figures:
contracts/scoring-output.md §12 — a mismatch there is stop SG-2, never an
edited assertion. Symbols are imported function-local (the repo's RED
convention).
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from sdlc.benchmarks.models import BenchmarkRecord

# The recorder is not edited by this round; import its real root resolver.
from sdlc.benchmarks.recorder import _root as _resolve_records_root

CAT_CAFE = "cat-cafe-monitoring"
TODO_API = "todo-api-greenfield"

_RECORDS_ROOT = Path(_resolve_records_root())
_RECORD_FILES = sorted(_RECORDS_ROOT.rglob("*.jsonl")) if _RECORDS_ROOT.is_dir() else []

if not _RECORD_FILES:
    pytest.skip(
        "no stored benchmark records under "
        f"{_RECORDS_ROOT} (SDLC_BENCHMARKS_ROOT or default runs/benchmarks); "
        "nothing stored here to pin the §12 figures against",
        allow_module_level=True,
    )


def _is_removed_herdr_harness(exc: ValidationError) -> bool:
    """The one known never-loaded failure shape, as in the legacy PIN."""
    errors = exc.errors()
    input_value = errors[0].get("input_value")
    return (
        len(errors) == 1
        and errors[0].get("loc") == ("harness",)
        and errors[0].get("type") == "enum"
        and (input_value is None or input_value == "herdr")
    )


def _stored_records() -> list[BenchmarkRecord]:
    """Every stored line that validates, in file order; lines that never
    loaded at base (the removed ``herdr`` harness value) are tolerated."""
    records: list[BenchmarkRecord] = []
    for path in _RECORD_FILES:
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                try:
                    records.append(BenchmarkRecord.model_validate_json(raw))
                except ValidationError as exc:
                    if _is_removed_herdr_harness(exc):
                        continue
                    raise
    return records


def _runs_for(records, case_id):
    from sdlc.benchmarks.runs import build_runs

    return [r for r in build_runs(records) if r.case_id == case_id]


def test_stored_cat_cafe_started_graded_lost():
    from sdlc.benchmarks.runs import totals

    runs = _runs_for(_stored_records(), CAT_CAFE)
    t = totals(runs)
    assert (t.started, t.graded, t.lost) == (18, 10, 8)


def test_stored_cat_cafe_lost_by_stage():
    from sdlc.benchmarks.runs import totals

    runs = _runs_for(_stored_records(), CAT_CAFE)
    t = totals(runs)
    assert t.lost_by_stage == {"research": 4, "clarify": 4}


def test_stored_cat_cafe_statuses_all_derived():
    runs = _runs_for(_stored_records(), CAT_CAFE)
    assert len(runs) == 18
    assert all(r.status_derived for r in runs)


def test_stored_cat_cafe_discarded_oracle_records():
    runs = _runs_for(_stored_records(), CAT_CAFE)
    assert sum(r.discarded_oracle_records for r in runs) == 8


def test_stored_cat_cafe_single_pre012_group():
    """§12: one group — pre-012, commit not recorded, harness opencode,
    arm `zai-coding-plan-glm-5.2` (R-3: the arm, not the coding model),
    every run's arm recovered from the run id."""
    from sdlc.benchmarks.runs import group_runs

    runs = _runs_for(_stored_records(), CAT_CAFE)
    groups = group_runs(runs)
    assert len(groups) == 1
    g = groups[0]
    assert g.generation == "pre012"
    assert g.commit is None
    assert g.harness == "opencode"
    assert g.arm == "zai-coding-plan-glm-5.2"
    assert all(r.arm_recovered for r in g.runs)


def test_stored_cat_cafe_mean_partial_credit_and_all_pass():
    from sdlc.benchmarks.runs import group_runs

    runs = _runs_for(_stored_records(), CAT_CAFE)
    (g,) = group_runs(runs)
    assert abs(g.mean - 85 / 120) < 1e-9
    assert g.all_pass == (1, 10)


def test_stored_cat_cafe_first_attempt_and_after_repair():
    """§12: first attempt / after repair 84/113 and 111/113, summed over
    the case's runs."""
    runs = _runs_for(_stored_records(), CAT_CAFE)
    first = [sum(r.first_attempt[i] for r in runs) for i in (0, 1)]
    repair = [sum(r.after_repair[i] for r in runs) for i in (0, 1)]
    assert first == [84, 113]
    assert repair == [111, 113]


def test_stored_todo_api_three_groups():
    """§12: pre-012 group (5 started, 4 graded, 1 lost); 012 commit
    `unknown` (1 graded); 012 commit `b3344416` (1 graded, 1 lost)."""
    from sdlc.benchmarks.runs import group_runs

    runs = _runs_for(_stored_records(), TODO_API)
    groups = {(g.generation, g.commit): g for g in group_runs(runs)}
    assert len(groups) == 3

    pre = groups[("pre012", None)]
    assert (pre.started, pre.graded, pre.lost) == (5, 4, 1)

    unknown = groups[("012", "unknown")]
    assert (unknown.started, unknown.graded, unknown.lost) == (1, 1, 0)

    commit = groups[("012", "b3344416")]
    assert (commit.started, commit.graded, commit.lost) == (2, 1, 1)


def test_stored_started_invariant_holds_for_every_case():
    """§1.7: started == graded + lost + grading_failed + no_oracle, for
    every case in the corpus."""
    from sdlc.benchmarks.runs import build_runs, totals

    all_runs = build_runs(_stored_records())
    assert all_runs, "no runs built from the stored records"
    for case_id in sorted({r.case_id for r in all_runs}):
        case_runs = [r for r in all_runs if r.case_id == case_id]
        t = totals(case_runs)
        assert t.started == t.graded + t.lost + t.grading_failed + t.no_oracle, (
            f"§1.7 invariant broken for case {case_id!r}"
        )


def test_stored_cat_cafe_attrition_layer():
    """§12 attrition on the stored cat-cafe row: research 4/18, clarify
    4/14, 8/18 lost before code (one row: pre-012, one arm)."""
    from sdlc.benchmarks.heatmap import build_layers

    hm = build_layers(_runs_for(_stored_records(), CAT_CAFE))
    (row,) = hm.rows
    assert row.started == 18
    assert row.lost_before_code == 8

    cells = {(c.layer, c.stage): c for c in hm.cells if c.row == row.key}
    research = cells[("attrition", "research")]
    assert (research.num, research.den, research.observations) == (4.0, 18.0, 18)
    clarify = cells[("attrition", "clarify")]
    assert (clarify.num, clarify.den, clarify.observations) == (4.0, 14.0, 14)


def test_stored_todo_api_pre012_lost_run_positions_at_code():
    """§12: todo-api's pre-012 lost run (code records, no post-code stage
    record, stored full-pass oracle) is positioned at `code` by the
    task-loop fold — 1 of the row's 5 runs, none lost before code."""
    from sdlc.benchmarks.heatmap import build_layers

    hm = build_layers(_runs_for(_stored_records(), TODO_API))
    pre_rows = [r for r in hm.rows if r.generation == "pre012"]
    assert len(pre_rows) == 1
    row = pre_rows[0]
    assert row.started == 5
    assert row.lost_before_code == 0  # the one lost run sits AT code, not before

    cells = {(c.layer, c.stage): c for c in hm.cells if c.row == row.key}
    code = cells[("attrition", "code")]
    assert (code.num, code.den, code.observations) == (1.0, 5.0, 5)


# --- 013 T009: contract §12 gate-versus-oracle rows (SC-009) --------------------


def _stored_gate_rows(case_id):
    from sdlc.benchmarks.gate_oracle import build_gate_oracle

    go = build_gate_oracle(_runs_for(_stored_records(), case_id))
    return {r.gate: r for r in go.rows}


def test_stored_cat_cafe_analyze_vs_oracle():
    """§12: analyze rejected 10, of which oracle pass 1; passed 0; escape
    n/a (zero denominator)."""
    row = _stored_gate_rows(CAT_CAFE)["analyze"]
    assert (row.pass_pass, row.pass_fail, row.reject_pass, row.reject_fail) == (
        0,
        0,
        1,
        9,
    )
    assert row.n == 10
    assert row.escape_rate is None
    assert row.agree_rate == 9 / 10
    assert row.mean_credit_passed is None
    assert abs(row.mean_credit_rejected - 85 / 120) < 1e-9


def test_stored_cat_cafe_merge_vs_oracle():
    """§12: merge rejected 7, of which oracle pass 1; passed 3, of which
    oracle fail 3; escape 3/3 low n (SC-009: merge revise is a pass)."""
    row = _stored_gate_rows(CAT_CAFE)["merge"]
    assert (row.pass_pass, row.pass_fail, row.reject_pass, row.reject_fail) == (
        0,
        3,
        1,
        6,
    )
    assert row.n == 10
    assert row.escape_rate == 1.0  # 3/3
    assert row.false_reject_rate == 1 / 7
    assert row.low_n["escape_rate"] is True


def test_stored_cat_cafe_qa_is_a_copy_row():
    """§12: the qa gate over cat-cafe's all-copy pre-012 runs reads
    `copy of code` and carries no counts."""
    from sdlc.benchmarks.gate_oracle import build_gate_oracle, render_gate_oracle_markdown

    row = _stored_gate_rows(CAT_CAFE)["qa"]
    assert row.is_copy is True
    assert (row.pass_pass, row.pass_fail, row.reject_pass, row.reject_fail, row.n) == (
        0,
        0,
        0,
        0,
        0,
    )
    md = render_gate_oracle_markdown(build_gate_oracle(_runs_for(_stored_records(), CAT_CAFE)))
    assert "copy of code (pre-012)" in md


# --- 013 T010: contract §9.3 — the summary count on the stored selection ------


def test_stored_cat_cafe_sc_rollup_reads_zero_of_eighteen():
    """§9.3 with the §12 selection: cat-cafe's 18 runs left no run summary
    (baseline item (e): no cat-cafe summary exists under the export root),
    so the rollup opens with `0 of 18 runs left a run summary`."""
    from sdlc.benchmarks.evidence import load_evidence
    from sdlc.benchmarks.sc_rollup import build_sc_rollup, render_sc_rollup_markdown

    ev = load_evidence(case=CAT_CAFE)
    assert ev.selection_runs == 18
    rollup = build_sc_rollup(ev.summaries, ev.records, selection_runs=ev.selection_runs)
    assert rollup.summary_runs == 0
    assert "0 of 18 runs left a run summary" in render_sc_rollup_markdown(rollup)
