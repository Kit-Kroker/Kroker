"""D1: a seeded run skips stages 0-3 and keeps everything from _dev_task down.

The unit tests here pin the contract and the skip predicate; the end-to-end
'no proposer was called' assertion is the temporal test at the bottom.
"""

import pytest

from sdlc.core.models import PipelineConfig
from sdlc.stages.architecture.models import (
    ArchitectureDecision,
    ArchitectureSpec,
    ValidationContract,
)
from sdlc.stages.plan.models import (
    DevTask,
    ImplementationPlan,
)
from sdlc.workflows.graph_catalog import SHIPPED, build_run_input, select_graph
from sdlc.workflows.models import SeededWork
from tests.fakes.canned import greenfield_idea


def _seeded():
    return SeededWork(
        arch=ArchitectureSpec(
            overview="Tidy-up: add .env to .gitignore",
            decisions=[
                ArchitectureDecision(
                    id="D1",
                    decision="Edit .gitignore only",
                    rationale="triage finding baseline/gitignore_missing_env",
                )
            ],
        ),
        plan=ImplementationPlan(
            tasks=[
                DevTask(
                    id="T01",
                    title="gitignore_missing_env in .gitignore",
                    description="Add .env to .gitignore.",
                    acceptance_criteria=["triage no longer reports the rule"],
                    files_hint=[".gitignore"],
                    contract=ValidationContract(
                        task_id="T01", assertions=[".env is ignored"], frozen=True
                    ),
                )
            ]
        ),
    )


def test_seeded_work_carries_an_arch_and_a_plan():
    s = _seeded()
    assert s.arch.overview.startswith("Tidy-up")
    assert [t.id for t in s.plan.tasks] == ["T01"]


def test_seeded_work_round_trips_through_json():
    """It crosses a Temporal child-workflow boundary, so it must serialize."""
    s = _seeded()
    assert SeededWork.model_validate_json(s.model_dump_json()) == s


def test_seeded_work_selects_the_seeded_graph_and_rides_the_run_input():
    """020 T026: the third-argument contract became the catalog pin —
    build_run_input(idea, cfg, seeded) selects SHIPPED['seeded'] and
    carries the SeededWork through GraphWorkflow's single input."""
    cfg = PipelineConfig()
    assert select_graph(cfg, _seeded()) is SHIPPED["seeded"]
    run_input = build_run_input(greenfield_idea(), cfg, _seeded())
    assert run_input.seeded == _seeded()


def test_seeded_plan_must_carry_at_least_one_task():
    with pytest.raises(ValueError):
        SeededWork(arch=_seeded().arch, plan=ImplementationPlan(tasks=[]))


# 020 T026: the temporal skip proof (a seeded run skipping clarify/
# architect/planner, E-44 D1) is deleted: the `seeded` golden replays the
# same shipped graph with the seeded input — counterpart
# tests/replay/test_graph_golden.py::test_graph_workflow_reproduces_the_golden_trace[seeded].
