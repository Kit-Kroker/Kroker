"""Dump JSON fixtures from the Pydantic models so the TS mapper is tested
against real shapes (spec 8, contract drift guard).

    python scripts/dump_dashboard_fixtures.py

D3 chose hand-written adaptation over codegen, so nothing structurally
prevents http.ts drifting from the models. These fixtures make drift break
a test instead of a page.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.gate import CheckClass, CheckResult
from sdlc.models import GateDecision, GateOutcome, RoleUsage, RunState, RunSummary
from sdlc.pending import (ClarifyPending, MergeGatePending,
                          StageGatePending, TaskEscalationPending)
from sdlc.channels.inbox import RunInbox

OUT = Path("interfaces/dashboard/frontend/src/api/__fixtures__")
AT = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


def main() -> None:
    snap = FleetSnapshot(
        at=AT + timedelta(hours=2),
        total_open_runs=2,
        runs=[
            RunState(
                run_id="feature-add-sso", title="Add SSO to customer portal",
                repo_url="git@github.com:acme/portal", mode="brownfield",
                status="awaiting:architecture", current_stage="architecture",
                started_at=AT,
                decisions=[GateDecision(
                    gate="clarify", round=1, outcome=GateOutcome.APPROVE,
                    decided_by="human", reviewer="human:mika",
                    comments="all suggestions accepted", decided_at=AT)],
                roles=[RoleUsage(role="architect", model="m", calls=2,
                                 cost_usd=3.12)],
                cost_usd_total=3.12, budget_usd=40.0),
            RunState(
                run_id="feature-unpriced", title="Unpriced run",
                mode="greenfield", status="running", current_stage="code",
                started_at=AT, cost_usd_total=None, budget_usd=None),
        ],
        closed=[RunSummary(
            run_id="feature-dark-mode", mode="brownfield",
            outcome="deployed:ok", terminal_stage="retro", started_at=AT,
            ended_at=AT + timedelta(hours=3), duration_s=10800.0,
            title="Dark mode for settings pages",
            repo_url="git@github.com:acme/portal", cost_usd_total=7.88),
            # E-10 review F2: rolled-back is a failure outcome; the fixture
            # must exercise closedStatus's success-vs-everything-else split.
            RunSummary(
                run_id="fix-payment-retry", mode="brownfield",
                outcome="rolled-back:pr-142", terminal_stage="deploy",
                started_at=AT, ended_at=AT + timedelta(hours=2),
                duration_s=7200.0, title="Payment retry hotfix",
                repo_url="git@github.com:acme/billing", cost_usd_total=11.3),
            # merged-not-deployed is success-family (tidyup.py): merged with
            # deploy disabled/unapproved must render done, not failed.
            RunSummary(
                run_id="feature-flag-cleanup", mode="greenfield",
                outcome="merged-not-deployed:pr-151", terminal_stage="merge",
                started_at=AT, ended_at=AT + timedelta(hours=1),
                duration_s=3600.0, title="Feature flag cleanup",
                repo_url=None, cost_usd_total=2.5)],
        inbox=[RunInbox(run_id="feature-add-sso", pending=[
            ClarifyPending(key="Q1", question="Which identity protocol?",
                           why_it_matters="no auth abstraction exists",
                           suggested_answer="OIDC", opened_at=AT),
            StageGatePending(key="architecture#1", gate="architecture",
                             round=1, spec_summary="Adds MeteringService",
                             opened_at=AT),
            MergeGatePending(key="merge#1", gate="merge", round=1,
                             verdict="MergeVerdict 0.91 - approve",
                             opened_at=AT, checks=[
                                 CheckResult(name="lint", passed=True,
                                             classification=CheckClass.ABSOLUTE,
                                             detail="clean"),
                                 CheckResult(name="diff coverage",
                                             passed=False,
                                             classification=CheckClass.ADVISORY,
                                             detail="0.68 - target 0.80")]),
            TaskEscalationPending(key="task:T07#1", gate="task:T07", round=1,
                                  task_id="T07", attempts=3,
                                  analysis="test_retry_budget flakes",
                                  opened_at=AT)])])

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fleet-snapshot.json").write_text(
        json.dumps(json.loads(snap.model_dump_json()), indent=2) + "\n",
        encoding="utf-8")
    print(f"wrote {OUT / 'fleet-snapshot.json'}")


if __name__ == "__main__":
    main()
