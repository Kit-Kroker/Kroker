"""The handoff lens runner (FR-805; FR-702 carries the patch in).

Split out of ``step.py`` at the FR-702 close-out for the 1000-line
ceiling — a pure, line-neutral move following ``acts.py`` (024 T021) and
``freeze.py``: ``step.py`` imports this under the ``_run_handoff`` name,
so every call site keeps working. The claim cross-check itself is pure
and lives in ``sdlc.handoff``; this module only runs the lens.

ALL runtime imports sit at module top inside the passthrough block —
step.py's own shape. Payload types (HandoffSummary above all) imported
inside the function body load as a SECOND class inside the workflow
sandbox, and TaskResult's validator then rejects the handoff it just
built ("instance of HandoffSummary" failing isinstance HandoffSummary);
the passthrough block keeps one class object across both worlds.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ...artifacts.read import LoadSessionInput, load_session
    from ...benchmarks.models import BenchmarkOutcome
    from ...benchmarks.record_builder import stage_record
    from ...core.context import StageContext
    from ...core.models import PipelineConfig, RoleUsage
    from ...handoff import claim_survival_score, cross_check_claims
    from ...harness.session import session_text_from_jsonl
    from .acts import ACT
    from .models import HandoffSummary


def _now() -> datetime:
    try:
        return workflow.now()
    except Exception:
        return datetime.now(UTC)


async def run_handoff(
    ctx: StageContext,
    cfg: PipelineConfig,
    run: Any,
    contract: Any,
    assertions: list[str],
    patch: str,
    files: list[str],
    task: Any,
    handoff_agent: Any = None,
) -> HandoffSummary:
    fallback = HandoffSummary(task_id=task.id, files_touched=files)
    if not (
        handoff_agent is not None
        and run is not None
        and getattr(run, "session_ref", None) is not None
    ):
        return fallback
    _started = _now()
    try:
        # Lazy like the original step.py body: agents.roles EAGERLY builds
        # the agent registry at import, and a module-level edge here puts
        # that build inside unrelated import chains (loader circular).
        from ...agents.roles import resolve_role_model

        loaded = await workflow.execute_activity(
            load_session, LoadSessionInput(ref=run.session_ref), **ACT
        )
        model = resolve_role_model(cfg, "handoff")
        spend = RoleUsage(role="handoff", model=model)
        session_text = session_text_from_jsonl(loaded.text)
        out = (
            await ctx.run_role(
                cfg,
                "handoff",
                model,
                handoff_agent,
                "Frozen contract assertions:\n- "
                + "\n- ".join(assertions)
                + f"\nDiff:\n{patch}"
                + "\nScrubbed harness transcript:\n"
                + session_text,
                into=spend,
            )
        ).output

        kept_total = 0
        dropped_total = 0
        fields = {}
        for name in ("what_changed", "decisions_made", "open_concerns"):
            checked = cross_check_claims(getattr(out, name), files, session_text=session_text)
            fields[name] = checked.kept
            kept_total += len(checked.kept)
            dropped_total += checked.dropped_paths + checked.dropped_quotes

        handoff = HandoffSummary(task_id=task.id, files_touched=files, **fields)
        await ctx.record(
            cfg,
            stage_record(
                cfg,
                stage="handoff",
                role="handoff",
                started=_started,
                ended=_now(),
                quality_score=claim_survival_score(kept_total, dropped_total).value,
                judge="handoff",
                outcome=BenchmarkOutcome.PASS,
                model=model,
                spend=spend,
                task_id=task.id,
                fix_attempts=0,
            ),
        )
        return handoff
    except Exception:
        workflow.logger.warning(
            "handoff extraction failed for task %s; using mechanical handoff",
            task.id,
            exc_info=True,
        )
        return fallback
