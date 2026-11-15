"""The incident machine's execute-side deltas (023b T019, RED).

Subject: ``sdlc.maintenance.incidents.step(state, curr)`` with
``state.config.execute=True`` (R7, R9; data-model.md transitions; B-FR-023/024).
``step`` is pure: the config rides ``state.config``, and the tests chain calls on
a carried state.

Scope: only the R7/R9 deltas. The 023a behaviours are covered by
``tests/maintenance/test_incidents.py`` and are not re-tested here.

The new live states are passed as strings and resolved inside ``_live_state``
(``IncidentState(value)``). Before T005/T020 each test using a new state fails on
its own ``ValueError``, not at collection time.

Identity: ``secrets:env_file_tracked:.gitignore`` (the 023a key format
``signal:rule:path:key``), the mechanical half of ``env_file_findings()``.
"""

from __future__ import annotations

import pytest

from sdlc.maintenance.incidents import step
from sdlc.maintenance.models import Incident, MaintenanceConfig, MaintenanceState
from tests.maintenance.conftest import env_file_findings, make_triage

IDENT_F = env_file_findings()[1]
KEY = f"{IDENT_F.signal}:{IDENT_F.rule}:{IDENT_F.path}:{IDENT_F.key}"
COMMIT_A = "a" * 40
COMMIT_B = "b" * 40
LIVE_STATES = ["approved", "queued", "executing", "verifying", "verified", "reopened"]


def _cfg(*, execute: bool) -> MaintenanceConfig:
    # execute=True needs build_probe (default True) and the ack (R14); the
    # defaults of the 023a helper satisfy both.
    return MaintenanceConfig(
        project="demo",
        repo_dir="/srv/repos/demo",
        ack_unattended_build_probe=True,
        execute=execute,
    )


def _baselined(*, execute: bool) -> MaintenanceState:
    """A state whose cycle 1 recorded a clean baseline (no findings)."""
    state = MaintenanceState(config=_cfg(execute=execute), cycle=1)
    after, _ = step(state, make_triage())
    return after


def _live_state(
    state_value: str,
    *,
    execute: bool = True,
    consecutive_seen: int = 2,
    commit: str = COMMIT_A,
    finding=IDENT_F,
) -> MaintenanceState:
    """One incident in ``state_value`` for IDENT_F, with the identity present
    in prev, so the next cycle's classification is PERSISTED or RESOLVED."""
    from sdlc.maintenance.models import IncidentState

    value = IncidentState(state_value)  # ValueError until the state exists (RED)
    inc = Incident(
        no=1,
        key=KEY,
        kind="finding",
        finding=finding,
        commit_sha=commit,
        first_seen_cycle=1,
        last_seen_cycle=1,
        seen_count=1,
        state=value,
        consecutive_seen=consecutive_seen,
    )
    base = _baselined(execute=execute)
    return base.model_copy(
        update={
            "prev": make_triage({"secrets": [IDENT_F]}, commit_sha=commit),
            "incidents": [inc],
            "cycle": 2,
            "next_incident_no": 2,
        }
    )


def _finding_incidents(state: MaintenanceState) -> list[Incident]:
    return [i for i in state.incidents if i.kind == "finding"]


# ------------------------------------------------ 1. identity matching (live states)


@pytest.mark.parametrize("live", LIVE_STATES)
def test_persisted_matches_a_live_incident_by_identity_without_a_duplicate(live):
    state = _live_state(live)
    nxt, _ = step(state, make_triage({"secrets": [IDENT_F]}, commit_sha=COMMIT_B))

    incidents = _finding_incidents(nxt)
    assert len(incidents) == 1, "a PERSISTED identity must not open a second incident"
    inc = incidents[0]
    assert inc.key == KEY
    assert inc.seen_count == 2
    assert inc.last_seen_cycle == 2
    # Detect never moves a live incident on PERSISTED: Report decides, not Detect.
    assert inc.state.value == live


# ------------------------------------------------------- 2. RESOLVED (collected)


@pytest.mark.parametrize("live", ["approved", "queued"])
def test_resolved_on_approved_or_queued_becomes_resolved_externally(live):
    state = _live_state(live)
    nxt, _ = step(state, make_triage())  # clean, collected: the identity is RESOLVED

    (inc,) = _finding_incidents(nxt)
    assert inc.state.value == "resolved_externally"


@pytest.mark.parametrize("live", ["executing", "verifying"])
def test_resolved_on_executing_or_verifying_is_left_for_report_to_decide(live):
    state = _live_state(live)
    nxt, _ = step(state, make_triage())  # clean, collected: the identity is RESOLVED

    (inc,) = _finding_incidents(nxt)
    assert inc.state.value == live, "Detect must not resolve a child-owned incident"


# ------------------------------------------------- 3. PERSISTED refresh (execute on)


def test_persisted_refreshes_finding_and_commit_under_execute():
    f_new = IDENT_F.model_copy(update={"detail": "re-read detail", "evidence": "new line"})
    state = _live_state("open", consecutive_seen=2, commit=COMMIT_A)
    nxt, _ = step(state, make_triage({"secrets": [f_new]}, commit_sha=COMMIT_B))

    (inc,) = _finding_incidents(nxt)
    assert inc.finding == f_new, "the current cycle's finding replaces the stored one"
    assert inc.commit_sha == COMMIT_B, "the current cycle's commit replaces the stored one"


def test_collected_persisted_increments_consecutive_seen_under_execute():
    state = _live_state("open", consecutive_seen=2)
    nxt, _ = step(state, make_triage({"secrets": [IDENT_F]}, commit_sha=COMMIT_B))

    (inc,) = _finding_incidents(nxt)
    assert inc.consecutive_seen == 3


def test_new_sets_consecutive_seen_to_one_under_execute():
    state = _baselined(execute=True)  # clean baseline, no incident yet
    nxt, _ = step(state, make_triage({"secrets": [IDENT_F]}, commit_sha=COMMIT_B))

    (inc,) = _finding_incidents(nxt)
    assert inc.consecutive_seen == 1


def test_not_collected_for_the_signal_resets_consecutive_seen_to_zero():
    state = _live_state("open", consecutive_seen=3)
    nxt, _ = step(state, make_triage(not_collected=["secrets"]))

    (inc,) = _finding_incidents(nxt)
    assert inc.consecutive_seen == 0
    assert inc.state.value == "open", "an unmeasured cycle never moves the incident itself"


# ----------------------------------------- 4. execute-off: the 023a deltas are absent


def test_execute_off_does_not_refresh_finding_commit_or_consecutive_seen():
    """Guard pin, expected to PASS at HEAD: with execute off, the R9 refresh and
    streak are inert. 023a's own seen_count bump still applies."""
    f_new = IDENT_F.model_copy(update={"detail": "re-read detail", "evidence": "new line"})
    state = _live_state("open", execute=False, consecutive_seen=2, commit=COMMIT_A)
    nxt, _ = step(state, make_triage({"secrets": [f_new]}, commit_sha=COMMIT_B))

    (inc,) = _finding_incidents(nxt)
    assert inc.finding == IDENT_F, "finding stays the original when execute is off"
    assert inc.commit_sha == COMMIT_A, "commit stays the original when execute is off"
    assert inc.consecutive_seen == 2, "the streak is not tracked when execute is off"
    assert inc.seen_count == 2, "023a's seen_count bump still applies"
    assert inc.last_seen_cycle == 2


# ----------------------------------------------- 5. terminal: only closed is new here


def test_closed_incident_is_terminal_and_a_new_detect_opens_a_fresh_incident():
    """``closed`` is terminal (R7): a NEW of the same identity opens a fresh
    incident with a fresh number, and the closed one is left as it was."""
    closed = _live_state("closed", execute=True).incidents[0]
    base = _baselined(execute=True)  # empty baseline, so the identity is NEW
    state = base.model_copy(
        update={"incidents": [closed], "cycle": 2, "next_incident_no": 2},
    )
    nxt, _ = step(state, make_triage({"secrets": [IDENT_F]}, commit_sha=COMMIT_B))

    incidents = _finding_incidents(nxt)
    assert len(incidents) == 2
    kept = next(i for i in incidents if i.no == 1)
    fresh = next(i for i in incidents if i.no == 2)
    assert kept.state.value == "closed"
    assert fresh.state.value == "open"
    assert fresh.consecutive_seen == 1


# ------------------------------------------------ EDGE (023b T019, RED) -- qa-chaos


def test_reopened_persisted_increments_consecutive_seen_and_stays_reopened():
    """Edge: a reopened incident is live and current under execute, so a collected
    PERSISTED Detect increments its streak and leaves its state alone."""
    state = _live_state("reopened", consecutive_seen=2)
    nxt, _ = step(state, make_triage({"secrets": [IDENT_F]}, commit_sha=COMMIT_B))

    (inc,) = _finding_incidents(nxt)
    assert inc.consecutive_seen == 3
    assert inc.state.value == "reopened"
