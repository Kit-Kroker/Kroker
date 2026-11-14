"""The incident machine's pure step (023a T013, RED).

Authorship note: both QA seats are quota-blocked until 23:50; this file is
executor-written under the degradation ruling — every test is a row of the
T013 matrix in tasks.md (FR-006/007/008, R5–R7) or a direct consequence.

Subject: ``sdlc.maintenance.incidents.step(state, curr) -> (state, events)``
— does not exist yet (T014 implements). Builders: tests/maintenance/conftest.py
(`make_triage` with per-signal findings, `not_collected`, `versions`).
"""

from __future__ import annotations

import pytest
from sdlc.maintenance.incidents import step

from sdlc.maintenance.models import (
    DETECT_SIGNALS,
    MAX_PREV_FINDINGS,
    IncidentState,
    MaintenanceConfig,
    MaintenanceState,
)
from tests.maintenance.conftest import (
    build_break_finding,
    credential_finding,
    critical_advisory,
    env_file_findings,
    make_triage,
)


def _cfg(**kw) -> MaintenanceConfig:
    base = dict(project="demo", repo_dir="/srv/repos/demo", ack_unattended_build_probe=True)
    base.update(kw)
    return MaintenanceConfig(**base)


def _state(prev=None, *, cycle=2, cfg=None, incidents=None) -> MaintenanceState:
    return MaintenanceState(
        config=cfg or _cfg(),
        cycle=cycle,
        baseline=None,
        prev=prev,
        incidents=incidents or [],
        not_collected_streak={},
        next_incident_no=1,
        nudged=False,
    )


def _with_baseline(state: MaintenanceState, triage) -> MaintenanceState:
    """Run one first cycle to record the baseline, return the carried state."""
    after, _ = step(state.model_copy(update={"cycle": 1, "prev": None, "baseline": None}), triage)
    return after


# --- SC-001: the first cycle records the baseline and opens nothing --------- #


def test_first_triage_records_baseline_and_opens_zero_incidents():
    # Pre-existing findings of every kind: none may open an incident.
    triage = make_triage(
        {
            "build_probe": [build_break_finding()],
            "dependencies": [critical_advisory()],
            "secrets": env_file_findings(),
        }
    )
    state, events = step(_state(cycle=1), triage)
    assert state.incidents == []
    assert state.baseline is not None
    assert state.baseline.recorded_cycle == 1
    assert state.baseline.commit_sha == triage.commit_sha
    assert len(state.baseline.identities) == 4
    assert state.prev is not None
    assert events.baseline_recorded is True


# --- SC-001 per-kind matrix: a seeded NEW fault opens exactly one incident --- #


@pytest.fixture
def baselined():
    """A state whose cycle 1 recorded a clean baseline (no findings)."""
    return _with_baseline(_state(cycle=1), make_triage())


KIND_FAULTS = {
    "build_probe": lambda: (build_break_finding(),),
    "dependencies": lambda: (critical_advisory(),),
    "secrets": lambda: tuple(env_file_findings()),
}


@pytest.mark.parametrize("signal", sorted(KIND_FAULTS))
def test_each_detect_kind_opens_exactly_one_incident(baselined, signal):
    findings = KIND_FAULTS[signal]()
    triage = make_triage({signal: list(findings)}, commit_sha="c" * 40)
    state, events = step(baselined, triage)

    opened = [i for i in state.incidents if i.kind == "finding"]
    assert len(opened) == len(findings)
    for inc, f in zip(opened, findings, strict=True):
        assert inc.key == f"{f.signal}:{f.rule}:{f.path}:{f.key}"
        assert inc.commit_sha == "c" * 40  # pinned at the detecting cycle
        assert inc.first_seen_cycle == 2
        assert inc.last_seen_cycle == 2
        assert inc.state is IncidentState.OPEN
        assert inc.finding == f
        assert inc.no >= 1
    assert state.next_incident_no > baselined.next_incident_no
    assert set(state.baseline.identities) == set(baselined.baseline.identities)  # untouched


@pytest.mark.parametrize("signal", sorted(KIND_FAULTS))
def test_recurrence_attaches_without_a_second_incident(baselined, signal):
    findings = KIND_FAULTS[signal]()
    first, _ = step(baselined, make_triage({signal: list(findings)}))
    # The fault persists into the next cycle's detect.
    second, _ = step(first, make_triage({signal: list(findings)}, commit_sha="d" * 40))

    same_key = [i for i in second.incidents if i.kind == "finding"]
    assert len(same_key) == len(findings)
    for inc in same_key:
        assert inc.seen_count == 2
        assert inc.last_seen_cycle == 3
        assert inc.state is IncidentState.OPEN
    assert second.next_incident_no == first.next_incident_no  # nothing new opened


# --- PERSISTED / RESOLVED / UNVERIFIABLE -------------------------------------- #


def test_persisted_on_open_incident_bumps_seen_count_only():
    baselined = _with_baseline(_state(cycle=1), make_triage())
    fault = build_break_finding()
    first, _ = step(baselined, make_triage({"build_probe": [fault]}))
    second, _ = step(first, make_triage({"build_probe": [fault]}))
    third, _ = step(second, make_triage({"build_probe": [fault]}))
    assert len(third.incidents) == 1
    assert third.incidents[0].seen_count == 3


def test_collected_disappearance_resolves_externally():
    baselined = _with_baseline(_state(cycle=1), make_triage())
    fault = build_break_finding()
    first, _ = step(baselined, make_triage({"build_probe": [fault]}))
    # Someone fixed it by hand: the signal is collected and clean.
    second, events = step(first, make_triage())
    assert len(second.incidents) == 1
    assert second.incidents[0].state is IncidentState.RESOLVED_EXTERNALLY
    assert second.incidents[0].last_seen_cycle == 2


def test_unverifiable_neither_opens_nor_resolves():
    baselined = _with_baseline(_state(cycle=1), make_triage())
    fault = build_break_finding()
    first, _ = step(baselined, make_triage({"build_probe": [fault]}))
    # The probe times out on the next cycle: not collected, not clean.
    second, events = step(first, make_triage(not_collected={"build_probe"}))
    assert len(second.incidents) == 1
    assert second.incidents[0].state is IncidentState.OPEN  # no transition
    assert second.incidents[0].seen_count == 1


# --- signal-version changes ---------------------------------------------------- #


def test_signal_version_change_rebaselines_that_signal_and_records_the_event():
    baselined = _with_baseline(_state(cycle=1), make_triage())
    fault = build_break_finding()
    first, _ = step(baselined, make_triage({"build_probe": [fault]}))
    # The secrets signal bumps version: its findings become UNVERIFIABLE and
    # the signal is re-baselined at the new version.
    second, events = step(first, make_triage({"build_probe": [fault]}, versions={"secrets": 99}))
    assert "secrets" in events.rebaselined_signals
    assert second.baseline.signal_versions["secrets"] == 99
    # The build fault is untouched by the secrets version change.
    assert second.incidents[0].state is IncidentState.OPEN
    assert second.incidents[0].seen_count == 2


# --- not-collected escalations -------------------------------------------------- #


def test_two_consecutive_not_collected_cycles_open_one_detect_escalation():
    baselined = _with_baseline(_state(cycle=1), make_triage())
    first, _ = step(baselined, make_triage(not_collected={"dependencies"}))
    assert first.not_collected_streak.get("dependencies") == 1
    assert first.incidents == []  # one missed cycle is never a fault

    second, _ = step(first, make_triage(not_collected={"dependencies"}))
    esc = [i for i in second.incidents if i.kind == "detect_escalation"]
    assert len(esc) == 1
    assert esc[0].key == "dependencies:not_collected::"
    assert esc[0].state is IncidentState.OPEN

    # A third missed cycle must not open a second escalation.
    third, _ = step(second, make_triage(not_collected={"dependencies"}))
    esc3 = [i for i in third.incidents if i.kind == "detect_escalation"]
    assert len(esc3) == 1


def test_collected_cycle_resets_the_streak():
    baselined = _with_baseline(_state(cycle=1), make_triage())
    first, _ = step(baselined, make_triage(not_collected={"secrets"}))
    second, _ = step(first, make_triage())  # collected again
    assert second.not_collected_streak.get("secrets", 0) == 0
    assert second.incidents == []


@pytest.mark.parametrize(
    "cfg_kw,signal",
    [
        ({"build_probe": False, "ack_unattended_build_probe": False}, "build_probe"),
        ({"advisory_source": "none"}, "dependencies"),
    ],
)
def test_configured_off_signals_never_increment_a_streak(cfg_kw, signal):
    # Configured off reads "not configured", never "fault": no streak, no
    # escalation, even when the signal reports not-collected every cycle.
    cfg = _cfg(**cfg_kw)
    state = _state(cycle=1, cfg=cfg)
    after, _ = step(state, make_triage(not_collected={signal}))
    twice, _ = step(after, make_triage(not_collected={signal}))
    assert twice.not_collected_streak.get(signal, 0) == 0
    assert [i for i in twice.incidents if i.kind == "detect_escalation"] == []


# --- the per-cycle cap ----------------------------------------------------------- #


def test_excess_new_incidents_is_deferred_and_picked_up_next_cycle():
    cfg = _cfg(max_new_incidents_per_cycle=2)
    baselined = _with_baseline(_state(cycle=1, cfg=cfg), make_triage())
    faults = [critical_advisory(package=f"pkg{i}") for i in range(4)]
    first, events = step(baselined, make_triage({"dependencies": faults}))

    assert len(first.incidents) == 4
    states = [i.state for i in first.incidents]
    assert states.count(IncidentState.OPEN) == 2
    assert states.count(IncidentState.DEFERRED) == 2
    assert len(events.deferred) == 2

    # Next cycle the faults persist: deferred ones are picked up (promoted),
    # still without a second incident per key.
    second, _ = step(first, make_triage({"dependencies": faults}))
    assert len(second.incidents) == 4
    assert all(i.state is IncidentState.OPEN for i in second.incidents)


# --- the prev cap ------------------------------------------------------------------ #


def test_prev_over_max_prev_findings_truncates_and_opens_nothing():
    baselined = _with_baseline(_state(cycle=1), make_triage())
    flood = [critical_advisory(package=f"p{i}") for i in range(MAX_PREV_FINDINGS + 1)]
    assert len(flood) > MAX_PREV_FINDINGS
    state, events = step(baselined, make_triage({"dependencies": flood}))
    assert events.truncated is True
    assert state.incidents == []  # never guess on a partial picture


def test_curr_over_max_prev_findings_also_truncates():
    baselined = _with_baseline(_state(cycle=1), make_triage())
    flood = [critical_advisory(package=f"p{i}") for i in range(MAX_PREV_FINDINGS + 5)]
    state, events = step(baselined, make_triage({"dependencies": flood}))
    assert events.truncated is True
    assert state.incidents == []


# --- filtering and determinism ------------------------------------------------------- #


def test_non_detect_signals_are_ignored():
    from sdlc.triage.models import FixClass, TriageFinding

    scaffold = TriageFinding(
        signal="scaffold",  # a triage signal Detect does not keep
        rule="anything",
        severity="high",
        detail="fixture",
        fix_class=FixClass.STRUCTURAL,
    )
    state, _ = step(_state(cycle=1), make_triage({"scaffold": [scaffold]}))
    # The baseline records only the three detect signals' identities.
    assert state.baseline is not None
    assert all("scaffold" not in i for i in state.baseline.identities)

    baselined = _with_baseline(_state(cycle=1), make_triage())
    after, _ = step(baselined, make_triage({"scaffold": [scaffold]}))
    assert after.incidents == []


def test_output_is_byte_identical_across_input_orderings():
    # Same findings, shuffled across signal list order and finding order:
    # the serialized state must be byte-identical.
    def shuffled_triage(seed: int):
        import random

        rng = random.Random(seed)
        findings = {
            "build_probe": [build_break_finding()],
            "dependencies": [critical_advisory(package=f"p{i}") for i in range(3)],
            "secrets": env_file_findings() + [credential_finding()],
        }
        for sig in findings:
            rng.shuffle(findings[sig])
        t = make_triage(findings)
        rng.shuffle(t.signals)
        return t

    a, _ = step(_state(cycle=1), shuffled_triage(1))
    b, _ = step(_state(cycle=1), shuffled_triage(2))
    assert a.model_dump_json() == b.model_dump_json()

    a2, _ = step(_with_baseline(_state(cycle=1), make_triage()), shuffled_triage(3))
    b2, _ = step(_with_baseline(_state(cycle=1), make_triage()), shuffled_triage(4))
    assert a2.model_dump_json() == b2.model_dump_json()


def test_detect_signals_are_exactly_three():
    assert DETECT_SIGNALS == {"secrets", "build_probe", "dependencies"}
