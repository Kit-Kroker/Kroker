"""FR-904 (E-44): what gets fixed, and the work handed to a fix run.

Pure -- no temporalio. Unlike `triage/`, this module MAY import the root
models.py: building pipeline contracts from triage findings is its whole job.
"""
from __future__ import annotations

from ..models import (
    ArchitectureDecision,
    ArchitectureSpec,
    DevTask,
    ImplementationPlan,
    SeededWork,
    ValidationContract,
)
from ..triage.admission import admits
from ..triage.models import (
    FixClass,
    RepoTriage,
    TriageFinding,
    finding_identity,
)


def admitted(triage: RepoTriage) -> bool:
    """D7. Tier 0's strictness of the ONE admission rule (E-45 D2).

    FR-903's gate blocks Tier 2, not tidy-up, so this is not automatic. It is
    adopted for a mechanical reason: on a repository that does not build,
    build_integration_green is an ABSOLUTE merge-gate check, so every fix run
    would produce a correct patch and then be blocked. That is N runs of model
    spend to learn what the build probe already reported.

    That argument does not care WHO approved, hence require_human=False.
    Tier 2 passes True, because an EDCR audit is expensive per-capability
    reasoning terminating in a bundle handed to a customer (FR-921), where "a
    human said proceed" is load-bearing.
    """
    ok, _ = admits(triage, require_human=False)
    return ok


def mechanical_backlog(
        triage: RepoTriage) -> list[tuple[str, TriageFinding]]:
    """Every MECHANICAL finding, as (identity, finding), sorted by identity.

    Sorting is load-bearing, not cosmetic (D10): child workflow ids derive
    from a finding's position in this list, and Temporal replay must produce
    the same ids.
    """
    out = [(finding_identity(f), f)
           for s in triage.signals for f in s.findings
           if f.fix_class is FixClass.MECHANICAL]
    out.sort(key=lambda pair: pair[0])
    return out


def seeded_work_for(identity: str, f: TriageFinding,
                    signal_version: int) -> SeededWork:
    """The deterministically-authored work for one mechanical finding (D1).

    One task, because one accepted finding is one PR (D2). The acceptance
    criterion names the signal, rule and version, so the reviewer and QA are
    validating against the thing that produced the finding rather than
    against the harness's narrative.
    """
    where = f.path or "the repository"
    title = f"{f.rule} in {where}"

    evidence = f"\n\nThe line that triggered it:\n{f.evidence}" if f.evidence \
        else ""
    description = (
        f"Triage finding `{identity}` (severity: {f.severity}).\n\n"
        f"{f.detail}{evidence}\n\n"
        f"Fix exactly this finding. Change nothing else -- this run opens one "
        f"pull request for one finding, and unrelated edits make it "
        f"un-reviewable.")

    criterion = (f"re-running triage signal `{f.signal}` v{signal_version} no "
                 f"longer reports `{f.rule}` for `{where}`")

    task = DevTask(
        id="T01", role="dev", title=title, description=description,
        acceptance_criteria=[criterion],
        files_hint=[f.path] if f.path else [],
        contract=ValidationContract(
            task_id="T01",
            assertions=[criterion],
            # FR-803 freezes the contract at planning, before code. Backlog
            # acceptance is the analogous moment: still before any code, with
            # a deterministic producer instead of the planner.
            frozen=True))

    arch = ArchitectureSpec(
        overview=(f"Tidy-up: {title}\n\n{f.detail}\n\nOpened by an E-44 "
                  f"tidy-up run from triage finding `{identity}`."),
        decisions=[ArchitectureDecision(
            id="D1",
            decision=f"Change only what `{f.rule}` requires"
                     + (f", in {f.path}" if f.path else ""),
            rationale="One PR per accepted finding (E-44 D2), so the client "
                      "can merge this fix without accepting the others.")],
        affected_modules=[f.path] if f.path else [])

    return SeededWork(arch=arch, plan=ImplementationPlan(tasks=[task]))
