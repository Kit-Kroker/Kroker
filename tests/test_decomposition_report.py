"""Unit tests of scripts/decomposition_report.py (016 T011, D-11) on
SYNTHETIC inputs: invented plan ids, an invented case, in-memory run
stand-ins. The synthetic plan fixture copies the REAL plan-artifact
schema read from
runs/pipeline/bench-cat-cafe-monitoring-1792148180/cat-cafe-monitoring#
opencode#zai-coding-plan-glm-5.3-flash/artifacts/plan-v25.json:

    {"tasks": [{"id": "T-01", ..., "depends_on": ["T-00"], ...}]}

-- the task-id field is ``id`` and the dependency field is ``depends_on``
(str list of upstream task ids). The plan_shape reading of Names
(edges = resolvable depends_on entries; longest_chain in NODES) was
checked against that real artifact and reproduces V6: 10 tasks, 18
edges, chain 7, dangling 0.

tier_credit definition pinned here (D-11, per (arm, tier)):
    mean over that arm's runs whose oracle_id matches the given identity
    of the per-run test-weighted fraction
        sum(score_of_task * n_tests_of_task) / n_tests_in_tier
    where n_requirements = the number of suite tasks in the tier and
    n_tests = the number of oracle tests mapped in the tier. Runs of a
    different oracle identity contribute NOTHING anywhere.
"""

import json
import re
from types import SimpleNamespace

import pytest

from scripts.decomposition_report import latest_plan, plan_shape, tier_credit

# A 4-task diamond in the real artifact shape: seats-and-holds and
# pricing-rules depend on scaffold-venue; end-to-end-flow depends on both.
DIAMOND_PLAN = {
    "tasks": [
        {"id": "scaffold-venue", "depends_on": []},
        {"id": "seats-and-holds", "depends_on": ["scaffold-venue"]},
        {"id": "pricing-rules", "depends_on": ["scaffold-venue"]},
        {"id": "end-to-end-flow", "depends_on": ["seats-and-holds", "pricing-rules"]},
    ]
}


def test_plan_shape_on_a_four_task_diamond():
    shape = plan_shape(DIAMOND_PLAN)
    assert shape.tasks == 4
    assert shape.edges == 4
    assert shape.longest_chain == 3  # NODE count: scaffold -> seats -> flow
    assert shape.dangling == 0


def test_latest_plan_picks_the_highest_version_and_reports_count(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "plan-v9.json").write_text("{}", encoding="utf-8")
    (artifacts / "plan-v10.json").write_text("{}", encoding="utf-8")
    (artifacts / "notes.txt").write_text("not a plan", encoding="utf-8")
    result = latest_plan(artifacts)
    assert result == artifacts / "plan-v10.json"
    # Pinned here: the candidate count rides on the returned path as an
    # attribute (Names annotates -> Path | None, so a tuple return would
    # contradict it; the CLI reports the count beside the path).
    assert result.count == 2


def _tier_case(tmp_path, monkeypatch) -> None:
    """A synthetic case whose mapping carries tier and feature on every
    task: hold-basic-1 (basic, 2 oracle tests), rule-charge-2 (rule, 3),
    cross-flow-3 (cross, 4)."""
    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path))
    case = tmp_path / "synthetic-tier-case"
    case.mkdir()
    (case / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: hold-basic-1\n"
        "    error_class: functional\n"
        "    tier: basic\n"
        "    feature: holds\n"
        "    oracle_tests:\n"
        "      - test_holds.py::test_hold_created\n"
        "      - test_holds.py::test_hold_expires\n"
        "  - id: rule-charge-2\n"
        "    error_class: data_integrity\n"
        "    tier: rule\n"
        "    feature: charges\n"
        "    oracle_tests:\n"
        "      - test_charges.py::test_charge_rounds\n"
        "      - test_charges.py::test_charge_declines_zero\n"
        "      - test_charges.py::test_charge_idempotent\n"
        "  - id: cross-flow-3\n"
        "    error_class: api_contract\n"
        "    tier: cross\n"
        "    feature: flows\n"
        "    oracle_tests:\n"
        "      - test_flow.py::test_refund_releases_hold\n"
        "      - test_flow.py::test_refund_notifies\n"
        "      - test_flow.py::test_refund_audits\n"
        "      - test_flow.py::test_refund_twice_fails\n",
        encoding="utf-8",
    )


def _run(arm: str, oracle_id: str, scores: dict[str, float]) -> SimpleNamespace:
    """An in-memory run stand-in: .arm, .case_id, .oracle_id, .records of
    per-oracle-task records with .scope, .task_id and .quality.score."""
    return SimpleNamespace(
        arm=arm,
        case_id="synthetic-tier-case",
        oracle_id=oracle_id,
        records=[
            SimpleNamespace(scope="oracle_task", task_id=tid, quality=SimpleNamespace(score=s))
            for tid, s in scores.items()
        ],
    )


def test_tier_credit_per_arm_and_tier_with_exact_numbers(tmp_path, monkeypatch):
    _tier_case(tmp_path, monkeypatch)
    match = "sha256:match"
    runs = [
        # arm A, run 1: basic 1.0, rule 0.5, cross 1.0
        _run(
            "arm-a",
            match,
            {
                "hold-basic-1": 1.0,
                "rule-charge-2": 0.5,
                "cross-flow-3": 1.0,
            },
        ),
        # arm A, run 2: basic 0.5, rule 1.0, cross 0.0
        _run(
            "arm-a",
            match,
            {
                "hold-basic-1": 0.5,
                "rule-charge-2": 1.0,
                "cross-flow-3": 0.0,
            },
        ),
        # arm B, matching identity: all 1.0
        _run(
            "arm-b",
            match,
            {
                "hold-basic-1": 1.0,
                "rule-charge-2": 1.0,
                "cross-flow-3": 1.0,
            },
        ),
        # arm A under a DIFFERENT oracle identity: contributes NOTHING
        _run(
            "arm-a",
            "sha256:other-identity",
            {
                "hold-basic-1": 0.0,
                "rule-charge-2": 0.0,
                "cross-flow-3": 0.0,
            },
        ),
    ]

    credit = tier_credit("synthetic-tier-case", runs, match)

    # mean = average of per-run sum(score * n_tests)/n_tests_in_tier;
    # n_requirements = tasks in the tier, n_tests = oracle tests in tier.
    assert set(credit) == {
        ("arm-a", "basic"),
        ("arm-a", "rule"),
        ("arm-a", "cross"),
        ("arm-b", "basic"),
        ("arm-b", "rule"),
        ("arm-b", "cross"),
    }
    assert credit[("arm-a", "basic")] == (0.75, 1, 2)  # (1.0 + 0.5) / 2
    assert credit[("arm-a", "rule")] == (0.75, 1, 3)  # (0.5 + 1.0) / 2
    assert credit[("arm-a", "cross")] == (0.5, 1, 4)  # (1.0 + 0.0) / 2
    assert credit[("arm-b", "basic")] == (1.0, 1, 2)
    assert credit[("arm-b", "rule")] == (1.0, 1, 3)
    assert credit[("arm-b", "cross")] == (1.0, 1, 4)


def test_cli_prints_no_synthetic_ids(tmp_path, capsys):
    """D-11: the CLI output is aggregates only -- never a task id, test
    name or requirement id of the synthetic material."""
    from scripts.decomposition_report import main

    plan = tmp_path / "plan-v1.json"
    plan.write_text(json.dumps(DIAMOND_PLAN), encoding="utf-8")
    rc = main(["--baseline-plan", str(plan)])
    out = capsys.readouterr().out
    assert rc == 0
    for task_id in (
        "scaffold-venue",
        "seats-and-holds",
        "pricing-rules",
        "end-to-end-flow",
    ):
        assert task_id not in out, f"CLI printed the task id {task_id!r}"
    # none of the tier-fixture's test names or requirement ids either
    for forbidden in (
        "test_hold_created",
        "test_charge_rounds",
        "test_refund_releases_hold",
        "hold-basic-1",
        "rule-charge-2",
        "cross-flow-3",
    ):
        assert forbidden not in out, f"CLI printed {forbidden!r}"


# --- chaos: plan_shape edges and the CLI argument rule -------------------------


def test_plan_shape_dependency_on_an_unknown_id_is_dangling_and_not_an_edge():
    plan = {
        "tasks": [
            {"id": "a-root", "depends_on": []},
            {"id": "b-mid", "depends_on": ["a-root"]},
            {"id": "c-leaf", "depends_on": ["b-mid", "ghost-task"]},
        ]
    }
    shape = plan_shape(plan)
    assert shape.tasks == 3
    assert shape.edges == 2  # the ghost entry is not an edge
    assert shape.dangling == 1
    assert shape.longest_chain == 3  # a-root -> b-mid -> c-leaf; the ghost adds no node


def test_plan_shape_dangling_entry_does_not_lengthen_the_chain():
    """A lone task whose only dependency is unknown is a chain of ONE node."""
    shape = plan_shape({"tasks": [{"id": "only-task", "depends_on": ["ghost-task"]}]})
    assert shape.tasks == 1
    assert shape.edges == 0
    assert shape.dangling == 1
    assert shape.longest_chain == 1


def test_plan_shape_of_an_empty_plan_is_all_zero():
    shape = plan_shape({"tasks": []})
    assert shape.tasks == 0
    assert shape.edges == 0
    assert shape.longest_chain == 0
    assert shape.dangling == 0


def _exit_code(argv: list[str]) -> int:
    """The CLI's refusal, however the module expresses it: a non-zero
    return from main(), or a SystemExit (argparse error, usage exit)."""
    from scripts.decomposition_report import main

    try:
        rc = main(argv)
    except SystemExit as exc:
        code = exc.code
        return 1 if code is None else (code if isinstance(code, int) else 1)
    return int(rc or 0)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--case", "synthetic-tier-case"],
        ["--bench-run", "bench-synthetic-1"],
    ],
    ids=["no-arguments", "case-without-bench-run", "bench-run-without-case"],
)
def test_cli_refuses_an_incomplete_argument_set(argv):
    """Names: at least one of the two groups is given; --case and
    --bench-run go together."""
    assert _exit_code(argv) != 0


def test_cli_refuses_a_case_without_a_bench_run_even_beside_a_baseline_plan(tmp_path):
    plan = tmp_path / "plan-v1.json"
    plan.write_text(json.dumps(DIAMOND_PLAN), encoding="utf-8")
    assert _exit_code(["--baseline-plan", str(plan), "--case", "synthetic-tier-case"]) != 0


def _figure(out: str, word: str, n: int) -> bool:
    """`word` and the number n adjacent in either order, whatever the
    separator style ('tasks: 4', 'tasks=4', '4 tasks', 'chain 3 nodes')."""
    return bool(
        re.search(rf"{word}\w*\D{{0,3}}\b{n}\b", out, re.IGNORECASE)
        or re.search(rf"\b{n}\b\s*(?:node\w*\s+)?{word}", out, re.IGNORECASE)
    )


def test_cli_baseline_plans_alone_print_each_shape_and_exit_zero(tmp_path, capsys):
    """Baselines-only mode needs neither --case nor --bench-run. Two plans
    with distinct figures: the diamond (tasks 4, edges 4, chain 3,
    dangling 0) and a 5-task line with one unknown dependency (tasks 5,
    edges 4, chain 5, dangling 1)."""
    from scripts.decomposition_report import main

    line = {
        "tasks": [
            {"id": "l1", "depends_on": []},
            {"id": "l2", "depends_on": ["l1"]},
            {"id": "l3", "depends_on": ["l2", "ghost-task"]},
            {"id": "l4", "depends_on": ["l3"]},
            {"id": "l5", "depends_on": ["l4"]},
        ]
    }
    first = tmp_path / "plan-diamond.json"
    second = tmp_path / "plan-line.json"
    first.write_text(json.dumps(DIAMOND_PLAN), encoding="utf-8")
    second.write_text(json.dumps(line), encoding="utf-8")

    rc = main(["--baseline-plan", str(first), "--baseline-plan", str(second)])
    out = capsys.readouterr().out
    assert rc == 0
    # the diamond's figures
    assert _figure(out, "task", 4), out
    assert _figure(out, "edge", 4), out
    assert _figure(out, "chain", 3), out
    # the line's figures (chain 5, tasks 5, dangling 1)
    assert _figure(out, "task", 5), out
    assert _figure(out, "chain", 5), out
    assert _figure(out, "dangling", 1), out
