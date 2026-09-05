"""Deploy stage slice contract test (spec A §3.3)."""

from __future__ import annotations

import inspect
import pathlib
from unittest.mock import AsyncMock, patch

import pytest

from sdlc.benchmarks.models import BenchmarkOutcome
from sdlc.core.models import (
    DeployConfig,
    GateDecision,
    GateOutcome,
    PipelineConfig,
)
from sdlc.stages import deploy
from sdlc.stages.deploy.activities import (
    deploy_apply,
    deploy_current_version,
    deploy_rollback,
    smoke_check,
)
from sdlc.stages.deploy.models import (
    DeployPlan,
    DeployReport,
)


class _StubCtx:
    def __init__(
        self,
        gate_decisions: list[GateDecision] | None = None,
    ) -> None:
        self.gate_decisions = gate_decisions or [
            GateDecision(gate="deploy", outcome=GateOutcome.APPROVE, decided_by="human")
        ]
        self.gate_call_count = 0
        self.recorded: list[dict] = []
        self.retained: list[dict] = []
        self.emitted: list[tuple] = []
        self.gates_called: list[str] = []
        self.stages_called: list[tuple[str, str]] = []

    async def gate(
        self,
        name: str,
        settings: dict,
        round: int = 1,
        context=None,
        default_policy=None,
    ) -> GateDecision:
        self.gates_called.append(name)
        decision = self.gate_decisions[min(self.gate_call_count, len(self.gate_decisions) - 1)]
        self.gate_call_count += 1
        return decision

    async def record(self, cfg, record) -> None:
        self.recorded.append({"stage": record.stage, "outcome": record.outcome})

    async def retain(self, cfg, kind, bank, text, metadata=None) -> None:
        self.retained.append({"kind": kind, "text": text, "metadata": metadata})

    def emit(self, kind, **kwargs) -> None:
        self.emitted.append((kind, kwargs))

    def stage(self, status: str, stage_name: str) -> None:
        self.stages_called.append((status, stage_name))


@pytest.mark.clause("DEPLOY-1.1")
def test_slice_exports_step_and_activities():
    assert callable(deploy.step)
    assert callable(deploy.prompt_digest)
    assert isinstance(deploy.ACTIVITIES, list)
    assert deploy_apply in deploy.ACTIVITIES
    assert deploy_rollback in deploy.ACTIVITIES
    assert smoke_check in deploy.ACTIVITIES
    assert deploy_current_version in deploy.ACTIVITIES

    params = inspect.signature(deploy.step).parameters
    param_names = list(params)
    assert param_names[0] == "ctx"
    assert "cfg" in param_names
    assert "deploy_plan" in param_names
    assert "repo_path" in param_names
    assert "pr_url" in param_names

    src = pathlib.Path("src/sdlc/stages/deploy/step.py").read_text(encoding="utf-8")
    assert "@workflow.defn" not in src
    assert "@workflow.signal" not in src
    assert "@workflow.query" not in src


@pytest.mark.clause("DEPLOY-1.2")
@pytest.mark.asyncio
async def test_deploy_fails_closed_when_gate_rejected_or_disabled():
    ctx = _StubCtx(
        gate_decisions=[GateDecision(gate="deploy", outcome=GateOutcome.REJECT, decided_by="human")]
    )
    cfg = PipelineConfig(deploy=DeployConfig(enabled=True))
    plan = DeployPlan(environment="staging", version="v1", smoke_checks=[])

    res = await deploy.step(
        ctx,
        cfg=cfg,
        deploy_plan=plan,
        repo_path="/repo",
        pr_url="https://pr.url/1",
    )

    assert res == "merged-not-deployed:https://pr.url/1"
    assert "deploy" in ctx.gates_called
    assert any(r["outcome"] == BenchmarkOutcome.REVISED for r in ctx.recorded)


@pytest.mark.clause("DEPLOY-1.3")
@pytest.mark.asyncio
async def test_deploy_success_executes_child_and_records_pass():
    ctx = _StubCtx(
        gate_decisions=[
            GateDecision(gate="deploy", outcome=GateOutcome.APPROVE, decided_by="human")
        ]
    )
    cfg = PipelineConfig(deploy=DeployConfig(enabled=True))
    plan = DeployPlan(environment="staging", version="v1", smoke_checks=[])
    report = DeployReport(deployed=True, environment="staging", version="v1", adapter="compose")

    with patch(
        "sdlc.stages.deploy.step._execute_deployment_workflow", new_callable=AsyncMock
    ) as mock_wf:
        mock_wf.return_value = report
        res = await deploy.step(
            ctx,
            cfg=cfg,
            deploy_plan=plan,
            repo_path="/repo",
            pr_url="https://pr.url/1",
        )

    assert res == "deployed:https://pr.url/1"
    assert ("deployed", "deploy") in ctx.stages_called
    assert any(r["outcome"] == BenchmarkOutcome.PASS for r in ctx.recorded)


@pytest.mark.clause("DEPLOY-1.4")
@pytest.mark.asyncio
async def test_deploy_retries_on_human_revise():
    ctx = _StubCtx(
        gate_decisions=[
            GateDecision(gate="deploy", outcome=GateOutcome.APPROVE, decided_by="human"),
            GateDecision(
                gate="deploy_failed", round=1, outcome=GateOutcome.REVISE, decided_by="human"
            ),
            GateDecision(
                gate="deploy_failed", round=2, outcome=GateOutcome.APPROVE, decided_by="human"
            ),
        ]
    )
    cfg = PipelineConfig(deploy=DeployConfig(enabled=True), max_gate_rounds=3)
    plan = DeployPlan(environment="staging", version="v1", smoke_checks=[])
    failing_report = DeployReport(
        deployed=False,
        environment="staging",
        version="v1",
        adapter="compose",
        rolled_back=True,
        rolled_back_to="v0",
        rollback_reason="smoke failed",
    )

    with patch(
        "sdlc.stages.deploy.step._execute_deployment_workflow", new_callable=AsyncMock
    ) as mock_wf:
        mock_wf.side_effect = [failing_report, failing_report]
        res = await deploy.step(
            ctx,
            cfg=cfg,
            deploy_plan=plan,
            repo_path="/repo",
            pr_url="https://pr.url/1",
        )

    assert res == "rolled-back:https://pr.url/1"
    assert ctx.gate_call_count == 3
    assert any(r["outcome"] == BenchmarkOutcome.FAIL for r in ctx.recorded)


@pytest.mark.clause("DEPLOY-1.5")
@pytest.mark.asyncio
async def test_deploy_broken_rollback_failure():
    ctx = _StubCtx(
        gate_decisions=[
            GateDecision(gate="deploy", outcome=GateOutcome.APPROVE, decided_by="human"),
            GateDecision(
                gate="deploy_failed", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
            ),
        ]
    )
    cfg = PipelineConfig(deploy=DeployConfig(enabled=True))
    plan = DeployPlan(environment="staging", version="v1", smoke_checks=[])
    broken_report = DeployReport(
        deployed=False,
        environment="staging",
        version="v1",
        adapter="compose",
        rolled_back=False,
        rollback_reason="rollback timeout",
    )

    with patch(
        "sdlc.stages.deploy.step._execute_deployment_workflow", new_callable=AsyncMock
    ) as mock_wf:
        mock_wf.return_value = broken_report
        res = await deploy.step(
            ctx,
            cfg=cfg,
            deploy_plan=plan,
            repo_path="/repo",
            pr_url="https://pr.url/1",
        )

    assert res == "deploy-broken:https://pr.url/1"
    assert ("deploy_failed", "deploy") in ctx.stages_called
    assert any(r["outcome"] == BenchmarkOutcome.FAIL for r in ctx.recorded)
