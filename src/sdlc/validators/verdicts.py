"""ADR-24's verdict functions (FR-301): evidence in, verdict out, computed.

First consumer of the evidence.py schemas. A verdict function composes the
FR-205 pure checks over a stored artifact and returns a `Verdict` -- the
envelope the SOFT auto-approve conjunct (`calibration/decision.py`) requires,
so a gate's deterministic AND-clause is computed in code, never a model's
say-so ("evidence before verdict"; docs/adr.md ADR-24). `plan_valid` IS the
ordered family (FR-301 D3: plan_check calls it with its run's PlanConfig, so
the halt port and the conjunct share one composition, ids_unique ->
deps_resolve -> dag_acyclic -> covers_all -> task_size), first failure wins,
and each Finding carries the failing check's reason verbatim -- the same
wire text plan_check rides on its halt port, minus the
`failed:plan-validation:` prefix -- so the ledger and the halt port disagree
about nothing but the port name.

Pure module: no I/O, no temporalio -- importable inside the workflow sandbox
and from plain tests alike.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel

from ..core.models import PlanConfig
from ..stages.plan.models import ImplementationPlan
from ..stages.requirements.models import Requirements
from .evidence import AssertionEvidence, Finding
from .pure import covers_all, dag_acyclic, deps_resolve, ids_unique, task_size


class Verdict(BaseModel):
    """One gate's deterministic verdict: did checks run, and did they pass.

    D1 shape (`checks_run, ok, findings`). `checks_run=False, ok=True` is the
    vacuous pass -- `vacuous()`: no deterministic provider exists for the
    gate (architecture today), so the conjunct passes on nothing. What is
    forbidden is a provider that ran and failed reading as a pass: a ran-and-
    failed verdict is `checks_run=True, ok=False` with the failing check's
    reason as a blocking Finding. `ok` is the only field a consumer may gate
    on; findings are for the ledger and the human.
    """

    checks_run: bool = True
    ok: bool = True
    findings: list[Finding] = []

    @classmethod
    def vacuous(cls) -> Verdict:
        """The pass of a gate with no deterministic provider: nothing ran,
        nothing failed. Deliberately NOT the value a failing or skipped
        provider may return."""
        return cls(checks_run=False, ok=True, findings=[])


def _failed(check: str, claim: str, reason: str) -> Verdict:
    """A ran-and-failed verdict: the check's reason verbatim as the finding's
    evidence text, the check's name as the detail, blocking because it is
    precisely what made `ok` False."""
    return Verdict(
        checks_run=True,
        ok=False,
        findings=[
            Finding(
                evidence=AssertionEvidence(claim=claim, evidence=reason),
                detail=check,
                blocking=True,
            )
        ],
    )


def plan_valid(
    plan: ImplementationPlan,
    requirements: Requirements | None,
    *,
    plan_cfg: PlanConfig | None = None,
) -> Verdict:
    """The plan gate's deterministic AND-clause over the stored plan.

    plan_check's halt family in plan_check's order -- ids_unique, then the
    graph checks (deps_resolve before dag_acyclic; the graph check needs
    resolved ids), then coverage, then task_size -- first failure wins, and
    the winner's reason rides the Finding verbatim. Coverage is skipped
    entirely when `requirements` is None (vacuous, the FR-205 precedent: a
    graph without the requirements_doc edge has nothing to cover).
    task_size defaults to the PlanConfig limits: a verdict over a stored
    artifact where no PipelineConfig is at hand. plan_check (FR-301 D3)
    passes its run's `plan_cfg` so it computes the SAME composition here
    instead of duplicating the family -- the defaults are deliberately
    generous (FR-205), so the gate never contradicts a plan_check that
    passed under them.
    """
    tasks = plan.tasks

    halt = ids_unique(tasks)
    if halt:
        return _failed("ids_unique", "task ids are unique", halt)

    halt = deps_resolve(tasks)
    if halt:
        return _failed("deps_resolve", "every depends_on resolves to a task in the plan", halt)

    halt = dag_acyclic(tasks)
    if halt:
        return _failed("dag_acyclic", "the dependency graph is acyclic", halt)

    if requirements is not None:
        uncovered = covers_all(tasks, [fr.id for s in requirements.stories for fr in s.functional])
        if uncovered:
            return _failed(
                "covers_all",
                "every requirement id is covered by a task",
                f"requirement(s) not covered by any task: {uncovered!r}",
            )

    halt = task_size(tasks, plan_cfg or PlanConfig())
    if halt:
        return _failed("task_size", "every task fits the plan limits", halt)

    return Verdict(checks_run=True, ok=True, findings=[])


def _vacuous_provider(*_args: Any) -> Verdict:
    """The lookup fallback's verdict: no provider for this gate, so the
    conjunct passes vacuously (D1 -- architecture today)."""
    return Verdict.vacuous()


class _GateProviders(dict[str, Callable[[Any, Any], Verdict]]):
    """GATE_PROVIDERS' registry: gate node id -> deterministic provider.

    Lookup is by gate node id; a gate with no provider yet (architecture)
    resolves to `_vacuous_provider` instead of raising -- every gate must be
    answerable for the conjunct, known or not. Consumers may equally use
    `.get(name, fallback)`; the registry carries the default so the
    unknown-gate-passes-vacuously contract lives beside the providers.
    """

    def __missing__(self, gate_id: str) -> Callable[[Any, Any], Verdict]:
        return _vacuous_provider


GATE_PROVIDERS: Mapping[str, Callable[[Any, Any], Verdict]] = _GateProviders({"plan": plan_valid})
