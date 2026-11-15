"""Capture test for the 023a state fixture (023b T002, R7).

Builds a representative 023a ``MaintenanceState`` and writes it to
``T/maintenance/fixtures/state_023a.json``. The run is gated behind
``SDLC_CAPTURE_FIXTURES=1`` so ordinary test runs never rewrite the
fixture; the committed JSON is the pin that ``test_models_023b.py``
loads to prove the 023b model additions are backward-compatible.

The state covers: the baseline, ``prev``, one incident in every 023a
``IncidentState``, a plan, a policy decision and a not-collected streak.
It is built with the 023a models only, so the committed payload carries
no 023b key — that is what makes the T004 pin meaningful.

This is NOT a ``T/replay/`` fixture: no stored replay golden is touched
(``T/replay/AGENTS.md``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sdlc.core.models import GateDecision, GateOutcome
from sdlc.maintenance.models import (
    Baseline,
    Incident,
    IncidentState,
    MaintenanceConfig,
    MaintenanceState,
    RepairAction,
    RepairPlan,
)
from tests.maintenance.conftest import (
    DEFAULT_VERSIONS,
    build_break_finding,
    credential_finding,
    env_file_findings,
    make_triage,
)

FIXTURE = Path(__file__).parent / "fixtures" / "state_023a.json"
CAPTURE_ENV = "SDLC_CAPTURE_FIXTURES"

_ANALYSIS = "The .env file is tracked and holds a live token."


def _representative_state() -> MaintenanceState:
    cfg = MaintenanceConfig(
        project="demo",
        repo_dir="/srv/repos/demo",
        ack_unattended_build_probe=True,
    )
    baseline = Baseline(
        identities=frozenset({"secrets:env-file:.env"}),
        signal_versions=dict(DEFAULT_VERSIONS),
        recorded_cycle=1,
        commit_sha="a" * 40,
    )
    env_tracked, env_secret = env_file_findings()
    plan = RepairPlan(
        analysis=_ANALYSIS,
        actions=[
            RepairAction(
                kind="code_fix",
                summary="untrack .env",
                target_paths=[".env"],
                ops_action=None,
            )
        ],
        self_confidence=0.9,
        floor=0.6,
        effective=0.6,
        author_model="claude-sonnet-5-5",
    )
    policy_decision = GateDecision(
        gate="repair:1",
        round=1,
        outcome=GateOutcome.APPROVE,
        decided_by="policy",
        comments="mechanical plan above the floor (023a R9)",
    )

    def inc(
        no: int,
        key: str,
        state: IncidentState,
        *,
        kind: str = "finding",
        finding=None,
        commit: str = "b" * 40,
        seen: int = 2,
        **extra,
    ) -> Incident:
        values = dict(
            no=no,
            key=key,
            kind=kind,
            finding=finding,
            commit_sha=commit,
            first_seen_cycle=1,
            last_seen_cycle=3,
            seen_count=seen,
            state=state,
            plan=None,
            plan_attempts=0,
            decision=None,
            note="",
        )
        values.update(extra)
        return Incident(**values)

    incidents = [
        # live states
        inc(
            1,
            "build_probe:build_failed::",
            IncidentState.OPEN,
            finding=build_break_finding(),
            commit="c" * 40,
            seen=1,
        ),
        inc(
            2,
            "secrets:env-file:.env",
            IncidentState.AWAITING_DECISION,
            finding=env_tracked,
            plan=plan,
            decision=policy_decision,
        ),
        inc(
            3,
            "build_probe:not_collected::",
            IncidentState.DEFERRED,
            kind="detect_escalation",
            finding=None,
            note="not collected twice",
        ),
        # terminal states
        inc(
            4,
            "secrets:env-file:.env",
            IncidentState.APPROVED_NOT_EXECUTED,
            finding=env_secret,
            note="approved with execute off",
        ),
        inc(
            5,
            "secrets:aws-access-key-id:config/settings.ini",
            IncidentState.REJECTED,
            finding=credential_finding(),
            note="human rejected",
        ),
        inc(6, "build_probe:build_failed::", IncidentState.TIMED_OUT, note="gate timed out"),
        inc(
            7,
            "secrets:env-file:.env",
            IncidentState.RESOLVED_EXTERNALLY,
            note="fixed on the default branch by hand",
        ),
        inc(
            8,
            "secrets:aws-access-key-id:config/settings.ini",
            IncidentState.ESCALATED,
            note="two plan attempts failed",
        ),
        inc(9, "build_probe:build_failed::", IncidentState.WITHDRAWN, note="project disabled"),
    ]
    return MaintenanceState(
        config=cfg,
        cycle=4,
        baseline=baseline,
        prev=make_triage({"secrets": env_file_findings()}, commit_sha="d" * 40),
        incidents=incidents,
        not_collected_streak={"dependencies": 2},
        next_incident_no=10,
        nudged=False,
    )


def test_capture_023a_state_fixture():
    """Write the 023a fixture — only when ``SDLC_CAPTURE_FIXTURES=1``."""
    if os.environ.get(CAPTURE_ENV) != "1":
        pytest.skip(f"capture run only: set {CAPTURE_ENV}=1 to (re)write {FIXTURE.name}")
    state = _representative_state()
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    payload = state.model_dump(mode="json")
    FIXTURE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # capture-time sanity: the written bytes reload to an equal state
    # under the same (023a) models.
    reloaded = MaintenanceState.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert reloaded == state
