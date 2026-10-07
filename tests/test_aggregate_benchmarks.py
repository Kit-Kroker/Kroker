"""012 T011 (RED): the documentation script's records (contract §7.9).

Tests run on a tmp_path runs directory the test writes itself: raw JSON
lines in ``<runs>/bench-<case>-<ts>/*.jsonl`` with only the fields the
script reads. Import pattern follows tests/docs_site/
test_aggregate_empty_state.py (scripts is importable via pythonpath).
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.aggregate_benchmarks import aggregate, build_html

_TS = 1791000001


def _rec(
    case="c1",
    scope="stage",
    stage="research",
    outcome="pass",
    wall=10.0,
    model="m1",
    **extra,
):
    rec = {
        "run_id": "r",
        "bench_run_id": "b",
        "case_id": case,
        "scope": scope,
        "stage": stage,
        "role": "dev" if scope == "task_attempt" else stage,
        "model": model,
        "prompt_sha": "",
        "quality": {"score": 1.0, "judge": "contract"},
        "speed": {
            "wall_clock_s": wall,
            "started_at": "2026-10-08T10:00:00+00:00",
            "ended_at": "2026-10-08T10:00:10+00:00",
        },
        "outcome": outcome,
    }
    rec.update(extra)
    return rec


def _cell_rec(case="c1"):
    return _rec(
        case=case,
        scope="cell",
        stage="cell",
        wall=5.0,
        model="deterministic",
        role="cell",
        arm="a1",
        cell_id="c1#opencode#a1",
        kroker_commit="abc123",
    )


def _write_run(runs_dir: Path, run_id: str, records: list[dict]) -> Path:
    rd = runs_dir / run_id
    rd.mkdir(parents=True)
    with open(rd / "records.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return runs_dir


def _run(data: dict) -> dict:
    return next(r for r in data["runs"])


# --- contract §7.9 bullet 1: a cell record is status, not data ---------------


def test_cell_scope_record_adds_nothing_to_a_run(tmp_path):
    base = [
        _rec(stage="research", wall=10.0),
        _rec(scope="task_attempt", stage="code", outcome="pass", wall=20.0, model="m2"),
    ]
    without = aggregate(_write_run(tmp_path / "without", f"bench-c1-{_TS}", base))
    with_cell = aggregate(_write_run(tmp_path / "with", f"bench-c1-{_TS}", base + [_cell_rec()]))
    r_without, r_with = _run(without), _run(with_cell)
    for key in ("total_wall_s", "record_count", "stage_count", "task_count", "errors"):
        assert r_with[key] == r_without[key], key
    assert with_cell["totals"]["total_records"] == without["totals"]["total_records"]
    assert with_cell["totals"]["total_wall_s"] == without["totals"]["total_wall_s"]
    assert with_cell["records"] == without["records"]


# --- contract §7.9 bullet 2: not_evaluated merge is not the overall ----------


def test_not_evaluated_merge_takes_overall_from_the_remaining_stages(tmp_path):
    all_pass = aggregate(
        _write_run(
            tmp_path,
            f"bench-c1-{_TS}",
            [
                _rec(stage="research", outcome="pass"),
                _rec(stage="clarify", outcome="pass"),
                _rec(stage="merge", outcome="not_evaluated"),
            ],
        )
    )
    assert _run(all_pass)["overall"] == "pass"

    # a second scenario needs its own runs root: _run picks the first run
    # and both fixtures share a timestamp suffix
    one_fail = aggregate(
        _write_run(
            tmp_path / "one-fail",
            f"bench-c2-{_TS}",
            [
                _rec(stage="research", outcome="fail"),
                _rec(stage="merge", outcome="not_evaluated"),
            ],
        )
    )
    assert _run(one_fail)["overall"] == "fail"


# --- contract §7.9 bullet 3: not_evaluated without a merge record ------------


def test_not_evaluated_stage_without_merge_does_not_fail_the_all_passed_test(tmp_path):
    passing = aggregate(
        _write_run(
            tmp_path,
            f"bench-c1-{_TS}",
            [
                _rec(stage="research", outcome="pass"),
                _rec(stage="qa", outcome="not_evaluated"),
            ],
        )
    )
    assert _run(passing)["overall"] == "pass"

    # separate runs root, same reason as above
    failing = aggregate(
        _write_run(
            tmp_path / "failing",
            f"bench-c2-{_TS}",
            [
                _rec(stage="research", outcome="fail"),
                _rec(stage="qa", outcome="not_evaluated"),
            ],
        )
    )
    assert _run(failing)["overall"] == "fail"


# --- contract §7.9 bullet 4: detail rows label by arm else model -------------


def test_detail_rows_label_by_arm_else_model(tmp_path):
    data = aggregate(
        _write_run(
            tmp_path,
            f"bench-c1-{_TS}",
            [
                _rec(stage="research", model="anthropic:glm-5.2", arm="a1"),
                _rec(stage="clarify", model="m2"),
            ],
        )
    )
    by_stage = {r["stage"]: r for r in data["records"]}
    assert by_stage["research"]["model"] == "a1"
    assert by_stage["clarify"]["model"] == "m2"


# --- contract §7.9 bullet 5: the pre-012 line --------------------------------


def test_build_html_states_the_pre012_count_for_records_without_commit(tmp_path):
    records = [
        _rec(stage="research"),
        _rec(stage="clarify"),
        _rec(scope="task_attempt", stage="code", wall=20.0),
        _rec(stage="qa", kroker_commit="abc123"),  # a 012 record
        # drift records are never pre-012, whatever their commit
        _rec(case="_production", stage="qa", outcome="fail"),
    ]
    data = aggregate(_write_run(tmp_path, f"bench-c1-{_TS}", records))
    html = build_html(data)
    assert "includes 3 pre-012 records (untrusted)" in html


def test_build_html_drops_the_pre012_line_when_every_record_has_a_commit(tmp_path):
    records = [
        _rec(stage="research", kroker_commit="abc123"),
        _rec(stage="clarify", kroker_commit="abc123"),
    ]
    data = aggregate(_write_run(tmp_path, f"bench-c1-{_TS}", records))
    assert "pre-012" not in build_html(data)


# --- contract §7.9 last line: the stored-records PIN --------------------------

# T001 base values: extracted from the aggregate output the executor kept
# at T001 (base 7f5191d0, primary checkout's runs/benchmarks). The 7.9
# changes must not move a stored number; they only add the pre-012 line.
_T001_BASE = {
    "bench-cat-cafe-monitoring-1791062646": {
        "overall": "fail",
        "record_count": 71,
        "stage_count": 6,
        "task_count": 14,
        "tasks_passed": 14,
        "total_wall_s": 23464.1,
    },
    "bench-todo-api-greenfield-1791051721": {
        "overall": "fail",
        "record_count": 55,
        "stage_count": 6,
        "task_count": 7,
        "tasks_passed": 7,
        "total_wall_s": 14517.3,
    },
}


def test_stored_pre012_runs_match_the_t001_base_values(tmp_path):
    """PIN: on a COPY of two stored run directories (every record pre-012 —
    no kroker_commit), each run's aggregate equals its T001 base values
    field-for-field, and build_html carries the one permitted difference:
    the pre-012 line for all 126 records."""
    import shutil

    import pytest

    records_root = Path("runs/benchmarks")
    if not all((records_root / run).is_dir() for run in _T001_BASE):
        pytest.skip(
            "stored run directories not found under runs/benchmarks "
            "(host-side run without the runs mount)"
        )
    for run in _T001_BASE:
        shutil.copytree(records_root / run, tmp_path / run)

    data = aggregate(tmp_path)
    for run, expected in _T001_BASE.items():
        got = next(r for r in data["runs"] if r["run_id"] == run)
        for key, want in expected.items():
            assert got[key] == want, f"{run}.{key}: got {got[key]!r}, T001 base {want!r}"

    assert data["totals"]["runs"] == 2
    assert data["totals"]["total_records"] == 71 + 55


def test_stored_pre012_runs_carry_only_the_pre012_line_difference(tmp_path):
    """The ONE permitted difference from base: the pre-012 line for all 126
    stored records. Green only once the 7.9 change lands; until then it
    fails on exactly that missing line."""
    import shutil

    import pytest

    records_root = Path("runs/benchmarks")
    if not all((records_root / run).is_dir() for run in _T001_BASE):
        pytest.skip(
            "stored run directories not found under runs/benchmarks "
            "(host-side run without the runs mount)"
        )
    for run in _T001_BASE:
        shutil.copytree(records_root / run, tmp_path / run)

    data = aggregate(tmp_path)
    assert "includes 126 pre-012 records (untrusted)" in build_html(data)
