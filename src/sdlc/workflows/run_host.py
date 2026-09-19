"""RunHost -- what every pipeline-run workflow shares (E-74 spec §4.3).

A mixin, following GateHost (workflows/gates.py:54). FeatureWorkflow and
GraphWorkflow list it BEFORE GateHost so its gate hooks override GateHost's
no-ops. Bodies are moved verbatim from FeatureWorkflow; the run_state and
run_summary queries stay on each concrete class as one-line delegates
(workflows/AGENTS.md rule 4 -- the dashboard queries by name).

Owns: _cfg, _idea, _started_at, _run_id, _run_summary.
Consumes via the MRO: ReportHost (_emit, _trace, _status, _role_usage),
GateHost (_gate_decisions), RoleHost (_budget_crossings), MemoryHost
(_retain, _memory_watermark), TaskHost (_session_refs).
"""

from __future__ import annotations

from datetime import datetime

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..core.models import (
        GateDecision,
        GatePolicy,
        IdeaBrief,
        PipelineConfig,
        RunState,
        RunSummary,
    )
    from ..memory.models import MemoryKind
    from ..notify.contract import NotifyReason
    from ..observability.summary import build_run_summary
    from ..observability.trace import RunEventKind
    from ..stages import retro


class RunHost:
    """Mixin. Subclasses must call super().__init__()."""

    def __init__(self) -> None:
        super().__init__()
        # Stashed state for hooks/queries (E-42, E-10, ADR-14, E-84). _run_id: run_state()
        # is unit-tested on bare instances (no event loop); "" sentinels: no reader before setup.
        self._cfg: PipelineConfig | None = None
        self._idea: IdeaBrief | None = None
        self._started_at: datetime | None = None
        self._run_id: str = ""
        self._run_summary: RunSummary | None = None

    async def _on_gate_awaited(self, name: str, round: int) -> None:
        self._emit(RunEventKind.GATE_AWAITED, stage=name, gate=name, round=str(round))  # type: ignore[attr-defined]

    async def _on_gate_decided(
        self,
        name: str,
        round: int,
        policy: GatePolicy,
        decision: GateDecision,
        confidence: float | None = None,
        author_model: str | None = None,
    ) -> None:
        conf = confidence
        self._emit(  # type: ignore[attr-defined]
            RunEventKind.GATE_DECIDED,
            stage=name,
            gate=name,
            round=str(round),
            policy=policy.value,
            decided_by=decision.decided_by,
            approved=("true" if decision.approved else "false"),
            **({"confidence": str(conf)} if conf is not None else {}),
            **({"author_model": author_model} if author_model else {}),
        )
        cfg = self._cfg
        if cfg is None:
            return
        await self._retain(  # type: ignore[attr-defined]
            cfg,
            MemoryKind.GATE_FEEDBACK,
            cfg.memory.project_bank,
            text=f"gate {name}#{round}: {decision.outcome.value}"
            f"{' — ' + decision.comments if decision.comments else ''}",
            metadata={"gate": name, "round": str(round), "run_id": workflow.info().workflow_id},
        )

    async def _on_notified(
        self, gate: str, reason: NotifyReason, notifier: str, delivered: bool, error: str = ""
    ) -> None:
        self._emit(  # type: ignore[attr-defined]
            RunEventKind.GATE_NOTIFIED,
            stage=gate,
            gate=gate,
            reason=reason.value,
            notifier=notifier,
            delivered="true" if delivered else "false",
            **({"error": error} if error else {}),
        )

    async def _retro(self, cfg: PipelineConfig, idea: IdeaBrief, result: str) -> None:
        """Stage 14 (E-32). Best-effort: any failure is swallowed so the run's
        return string is never changed."""
        try:
            summary = build_run_summary(
                run_id=workflow.info().workflow_id,
                mode=idea.mode.value,
                outcome=result,
                trace=self._trace,  # type: ignore[attr-defined]
                memory_enabled=cfg.memory.enabled,
                memory_watermark=self._memory_watermark,  # type: ignore[attr-defined]
                budget_usd=(cfg.run_budget_usd if cfg.run_budget_usd > 0 else None),
                title=idea.title,
                repo_url=idea.repo_url,
                # E-77 R-3: the run's pinned graph, when the host is a
                # GraphWorkflow; None for FeatureWorkflow (content only, no
                # command change, U6).
                graph_sha=getattr(self, "_graph_sha", "") or None,
            )
            self._run_summary = summary
            await retro.step(
                self._ctx,  # type: ignore[attr-defined]
                cfg=cfg,
                summary=summary,
                session_refs=self._session_refs,  # type: ignore[attr-defined]
                trace=self._trace,  # type: ignore[attr-defined]
            )
        except Exception:
            # Retro must never change the run outcome (best-effort stage).
            pass

    def _snapshot_run_state(self) -> RunState | None:
        """Live run state for the dashboard fleet view (E-10).

        None until run() stashes the brief. Every field is read from state
        the run already holds -- this query adds no bookkeeping.
        """
        if self._idea is None or self._started_at is None:
            return None
        priced = [
            u.cost_usd
            for u in self._role_usage.values()  # type: ignore[attr-defined]
            if u.cost_usd is not None
        ]  # determinism: insertion-ordered usage dict
        budget = self._cfg.run_budget_usd if self._cfg and self._cfg.run_budget_usd > 0 else None
        stage = next(
            (e.stage for e in reversed(self._trace) if e.kind is RunEventKind.STAGE_STARTED),  # type: ignore[attr-defined]
            None,
        )
        return RunState(
            run_id=self._run_id,
            title=self._idea.title,
            repo_url=self._idea.repo_url,
            mode=self._idea.mode.value,
            status=self._status,  # type: ignore[attr-defined]
            current_stage=stage,
            started_at=self._started_at,
            decisions=list(self._gate_decisions.values()),  # type: ignore[attr-defined]
            roles=list(self._role_usage.values()),  # type: ignore[attr-defined]
            # None, not 0.0: a pricing miss must never read as a free run.
            cost_usd_total=sum(priced) if priced else None,
            budget_usd=budget,
            budget_crossings=self._budget_crossings,  # type: ignore[attr-defined]
        )
