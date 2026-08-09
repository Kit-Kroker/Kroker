"""D7/D10 and the authored DevTask. Pure -- no Temporal."""
import pytest

from sdlc.measurement import Measurement
from sdlc.tidyup.backlog import admitted, mechanical_backlog, seeded_work_for
from sdlc.triage.models import (
    FixClass, Readiness, ReadinessOverride, RepoTriage, SignalResult,
    TriageFinding, Verdict,
)
from datetime import datetime, timezone


def _f(rule, fix_class=FixClass.MECHANICAL, key="", path="p", signal="s"):
    return TriageFinding(signal=signal, rule=rule, severity="high",
                         detail=f"{rule} detail", path=path, key=key,
                         evidence="the offending line", fix_class=fix_class)


def _triage(findings, verdict=Verdict.READY, override=None):
    m = Measurement.measured(1.0)
    return RepoTriage(
        repo_dir="/r", commit_sha="a" * 40, override=override,
        readiness=Readiness(buildable=m, runnable=m, tests_present=m,
                            structure_discernible=m, verdict=verdict),
        signals=[SignalResult(signal="s", version=4,
                              collected=Measurement.measured(
                                  float(len(findings))),
                              findings=findings)])


def test_backlog_holds_only_mechanical_findings():
    t = _triage([_f("a"), _f("b", FixClass.JUDGEMENT),
                 _f("c", FixClass.STRUCTURAL)])
    assert [f.rule for _, f in mechanical_backlog(t)] == ["a"]


def test_backlog_is_sorted_by_identity():
    """D10: child workflow ids derive from position, and replay must produce
    the same ids."""
    t = _triage([_f("z", key="1"), _f("a", key="2")])
    ids = [i for i, _ in mechanical_backlog(t)]
    assert ids == sorted(ids)


def test_backlog_is_empty_when_nothing_is_mechanical():
    assert mechanical_backlog(_triage([_f("a", FixClass.JUDGEMENT)])) == []


def test_admitted_on_ready():
    assert admitted(_triage([], Verdict.READY)) is True


@pytest.mark.parametrize("verdict", [Verdict.NOT_READY, Verdict.INDETERMINATE])
def test_not_admitted_without_an_override(verdict):
    assert admitted(_triage([], verdict)) is False


@pytest.mark.parametrize("verdict", [Verdict.NOT_READY, Verdict.INDETERMINATE])
def test_admitted_with_an_audited_override(verdict):
    """D7: E-42's rule verbatim -- READY or override is not None."""
    o = ReadinessOverride(approved_by="human", reason="proceeding anyway",
                          decided_at=datetime.now(timezone.utc), gate_round=1)
    assert admitted(_triage([], verdict, override=o)) is True


def test_seeded_work_has_exactly_one_task():
    s = seeded_work_for("s:a:p:", _f("a"), signal_version=4)
    assert len(s.plan.tasks) == 1


def test_authored_task_names_the_rule_the_path_and_the_evidence():
    s = seeded_work_for("s:a:p:", _f("a"), signal_version=4)
    t = s.plan.tasks[0]
    assert "a" in t.title and "p" in t.title
    assert "the offending line" in t.description
    assert t.files_hint == ["p"]
    assert t.role == "dev"


def test_authored_task_constrains_the_change():
    """One PR per finding means the run must not wander."""
    t = seeded_work_for("s:a:p:", _f("a"), signal_version=4).plan.tasks[0]
    assert "Change nothing else" in t.description


def test_acceptance_criterion_names_the_signal_rule_and_version():
    t = seeded_work_for("s:a:p:", _f("a"), signal_version=4).plan.tasks[0]
    criterion = t.acceptance_criteria[0]
    assert "s" in criterion and "a" in criterion and "4" in criterion


def test_contract_is_frozen_at_acceptance():
    """FR-803 freezes at planning, before code. Backlog acceptance is the
    analogous moment: still before code, deterministic producer."""
    t = seeded_work_for("s:a:p:", _f("a"), signal_version=4).plan.tasks[0]
    assert t.contract is not None
    assert t.contract.frozen is True
    assert t.contract.task_id == t.id


def test_arch_overview_becomes_a_usable_pr_body():
    s = seeded_work_for("s:a:p:", _f("a"), signal_version=4)
    assert "a" in s.arch.overview
    assert s.arch.decisions, "the PR body should say why the change is scoped"


def test_a_finding_with_no_path_still_authors_a_task():
    """no_env_example carries path=''."""
    s = seeded_work_for("s:x::", _f("x", path=""), signal_version=4)
    assert s.plan.tasks[0].files_hint == []
    assert s.plan.tasks[0].title
