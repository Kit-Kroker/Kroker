"""`plan_valid` and the Verdict envelope (`sdlc.validators.verdicts`).

The first consumer of the ADR-24 evidence schemas. The pins here: the
envelope shape (D1), the FR-205 check order as first-failure-wins, and the
verbatim failure texts -- `Finding.evidence.evidence` must equal the failing
check's reason exactly, because the same strings ride plan_check's halt port
(the `failed:plan-validation:` prefix aside) and the calibration ledger will
quote them. The vacuous-coverage pin (requirements=None) carries the FR-205
precedent: no requirements artifact means nothing to cover, not a failure.
"""

from __future__ import annotations

import subprocess
import sys

from sdlc.core.models import PlanConfig
from sdlc.stages.plan.models import DevTask, ImplementationPlan
from sdlc.stages.requirements.models import FunctionalRequirement, Requirements, Story
from sdlc.validators import GATE_PROVIDERS, Verdict, plan_valid


def _task(
    id_: str,
    depends_on: list[str] | None = None,
    *,
    covers: list[str] | None = None,
    files_hint: list[str] | None = None,
    criteria: list[str] | None = None,
) -> DevTask:
    return DevTask(
        id=id_,
        title="t",
        description="d",
        depends_on=depends_on or [],
        acceptance_criteria=criteria or [],
        files_hint=files_hint or [],
        covers=covers or [],
    )


OVERSIZE = PlanConfig().max_files_hint + 1


def _oversized(id_: str) -> DevTask:
    return _task(id_, files_hint=[f"f{i}" for i in range(OVERSIZE)])


def _plan(*tasks: DevTask) -> ImplementationPlan:
    return ImplementationPlan(tasks=list(tasks))


def _req(*fr_ids: str) -> Requirements:
    return Requirements(
        stories=[
            Story(
                id="US-1",
                narrative="n",
                functional=[FunctionalRequirement(id=fid, text="t") for fid in fr_ids],
                success_criteria=[],
            )
        ],
        digest="d",
        drafted_by="agent",
    )


def test_verdict_field_order_is_checks_run_ok_findings():
    # D1 shape; the calibration conjunct reads `verdict.ok`, so the envelope
    # is pinned the way evidence.py pins its field order.
    assert tuple(Verdict.model_fields) == ("checks_run", "ok", "findings")


def test_verdict_defaults_are_ran_and_passed():
    v = Verdict()
    assert v.checks_run is True
    assert v.ok is True
    assert v.findings == []


def test_vacuous_constructor_is_checks_run_false_ok_true():
    # D1: checks_run=False -> vacuous pass (no deterministic provider ran).
    v = Verdict.vacuous()
    assert v.checks_run is False
    assert v.ok is True
    assert v.findings == []


def test_valid_plan_passes_with_no_findings():
    v = plan_valid(
        _plan(_task("T1", covers=["FR-1"]), _task("T2", ["T1"], covers=["FR-2"])),
        _req("FR-1", "FR-2"),
    )
    assert v.checks_run is True
    assert v.ok is True
    assert v.findings == []


def test_duplicate_ids_fail_with_verbatim_text():
    v = plan_valid(_plan(_task("T2"), _task("T1"), _task("T2"), _task("T1")), None)
    assert v.ok is False
    assert len(v.findings) == 1
    assert v.findings[0].evidence.evidence == "duplicate task id(s): ['T1', 'T2']"
    assert v.findings[0].detail == "ids_unique"
    assert v.findings[0].blocking is True


def test_unknown_dependency_fails_with_verbatim_text():
    v = plan_valid(_plan(_task("A", ["Z"])), None)
    assert v.ok is False
    assert v.findings[0].evidence.evidence == "task 'A' depends on unknown task id(s) ['Z']"


def test_cycle_fails_with_verbatim_text():
    v = plan_valid(_plan(_task("A", ["B"]), _task("B", ["A"])), None)
    assert v.ok is False
    assert v.findings[0].evidence.evidence == "dependency cycle: A -> B -> A"


def test_uncovered_requirement_fails_with_verbatim_text():
    v = plan_valid(_plan(_task("T1", covers=["FR-1"])), _req("FR-1", "FR-2"))
    assert v.ok is False
    assert v.findings[0].evidence.evidence == "requirement(s) not covered by any task: ['FR-2']"


def test_oversized_task_fails_with_verbatim_text():
    v = plan_valid(_plan(_oversized("T1")), None)
    assert v.ok is False
    assert v.findings[0].evidence.evidence == (
        f"task 'T1' exceeds plan limits: files_hint={OVERSIZE}>{PlanConfig().max_files_hint}"
    )


def test_requirements_none_skips_coverage_vacuously():
    # The FR-205 precedent: without a requirements artifact there is nothing
    # to cover -- the same plan fails coverage when the artifact exists and
    # passes when it is None; the family still ran (checks_run=True).
    tasks = [_task("T1")]
    assert plan_valid(_plan(*tasks), _req("FR-1")).ok is False
    v = plan_valid(_plan(*tasks), None)
    assert v.ok is True
    assert v.checks_run is True
    assert v.findings == []


def test_first_failure_wins_ids_unique_before_all_later_checks():
    # A plan failing every family must report only the FIRST family's text,
    # in plan_check's contract order: ids_unique beats everything.
    fat = _task("T2", ["Z"], files_hint=[f"f{i}" for i in range(OVERSIZE)])
    v = plan_valid(_plan(fat, _task("T1"), _task("T2"), _task("T1")), _req("FR-1"))
    assert v.ok is False
    assert len(v.findings) == 1
    assert v.findings[0].evidence.evidence == "duplicate task id(s): ['T1', 'T2']"


def test_deps_resolve_precedes_dag_acyclic():
    # A dangling ref AND a true cycle: deps_resolve fires first (plan_check's
    # order -- the dangling ref is named before the cycle).
    v = plan_valid(_plan(_task("A", ["B", "Z"]), _task("B", ["A"])), None)
    assert v.findings[0].evidence.evidence == "task 'A' depends on unknown task id(s) ['Z']"


def test_dag_acyclic_precedes_coverage():
    v = plan_valid(_plan(_task("A", ["B"]), _task("B", ["A"])), _req("FR-1"))
    assert v.findings[0].evidence.evidence == "dependency cycle: A -> B -> A"


def test_coverage_precedes_task_size():
    v = plan_valid(_plan(_oversized("T1")), _req("FR-1"))
    assert v.findings[0].evidence.evidence == "requirement(s) not covered by any task: ['FR-1']"


def test_gate_providers_maps_plan_to_plan_valid():
    assert GATE_PROVIDERS["plan"] is plan_valid


def test_gate_providers_unknown_gate_reads_vacuous():
    provider = GATE_PROVIDERS["architecture"]
    v = provider(object(), None)
    assert v.checks_run is False
    assert v.ok is True
    assert v.findings == []


def test_verdicts_module_import_stays_temporalio_free():
    """Layering: verdicts.py is pure -- importable in the workflow sandbox."""
    cmd = [
        sys.executable,
        "-c",
        "import sys, sdlc.validators.verdicts; "
        "assert 'temporalio' not in sys.modules, 'temporalio leaked'",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"stdout: {res.stdout}, stderr: {res.stderr}"
