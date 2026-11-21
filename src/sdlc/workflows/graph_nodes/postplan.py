"""Post-plan node handlers (E-74 spec §6; coarse `code` per U1)."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ... import pools
    from ...agents.roles import STAGE_MODELS, resolve_role_model, t_analyst, t_merge_verdict
    from ...artifacts.read import LoadDiffInput, load_diff
    from ...core.models import GateDecision, GateOutcome, PipelineConfig
    from ...graph.router import Activation
    from ...stages import analyze, deploy, merge
    from ...validators.verdicts import plan_valid
    from ...vcs import DiffInput, get_task_diff
    from ..build import run_tasks
    from ..models import AnalyzeResult, BuildResult, PullRequest
    from .base import NodeContext, NodeResult, input_model

ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)


async def plan_check_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    """The plan validators (FR-301 D2/D3): gate.plan's deterministic input.

    One composition, shared with the gate's ADR-24 conjunct: `plan_valid`
    runs the ordered family (ids_unique -> deps_resolve -> dag_acyclic ->
    covers_all -> task_size, the order part of the PLAN-1.8 contract --
    duplicate ids are named before the graph checks because the downstream
    {t.id: t} collapse would silently drop tasks and hide every later
    fault) with this run's cfg.plan, so the gate can never contradict it.
    """
    plan = input_model(nc, act, "plan")
    assert plan is not None
    req_doc = input_model(nc, act, "requirements_doc")
    verdict = plan_valid(plan, req_doc, plan_cfg=cfg.plan)
    if not verdict.ok:
        reason = verdict.findings[0].evidence.evidence
        # D3: a connected, unexhausted revise loop returns the validator
        # text to the planner as REVISE guidance -- no human gate ever
        # opens for a validator failure. Anything else keeps today's
        # terminal halt: an old pinned graph wires no revise edge (the
        # halt port has none by construction), and a max_traversals-exhausted
        # loop must not escalate on an unavailable port.
        if nc.connected("revise") and "revise" not in act.unavailable_ports:
            return NodeResult(
                port="revise",
                payload=GateDecision(
                    gate=nc.node.id,
                    round=act.round,
                    outcome=GateOutcome.REVISE,
                    decided_by="policy",
                    guidance=reason,
                ),
            )
        return NodeResult(port="halt", result=f"failed:plan-validation:{reason}")
    # The gate's conjunct reads the producer stash (FR-301): the
    # requirements doc this plan was validated against, None on graphs
    # that wire no requirements_doc edge; "validated" tells the gate's
    # publish that THIS node ok'd the artifact and deferred the board
    # sync to the version it mints.
    carry = nc.carry(nc.node.id)
    carry["requirements_doc"] = req_doc
    carry["validated"] = True
    # The gate's finish reads its prep from the ARTIFACT PRODUCER's carry
    # ("prep" is the plan stage's own state, stashed by the planner). This
    # node now sits between the planner and the gate, so the ok path passes
    # the prep through from the plan token's producer -- gate_node's
    # carry(producer)["prep"] read keeps working unchanged. Tolerant by
    # absence: on an old pinned graph this node's plan token comes from the
    # GATE's approve emission (a producer with no prep), nothing downstream
    # reads the pass-through there, and the run keeps its exact old shape.
    plan_ref = act.inputs["plan"]
    assert isinstance(plan_ref, str)  # multiplicity "one": a single payload ref
    prep_producer = nc.payload(plan_ref).producer.rpartition("#")[0]
    prep = nc.carry(prep_producer).get("prep")
    if prep is not None:
        carry["prep"] = prep
    # The reorder runs this node BEFORE gate.plan mints a plan version
    # (_plan_version is None), so the sync waits for the gate's publish.
    # Old pinned graphs still gate first: their finalize has minted a
    # version by the time this activation runs, and the sync fires here
    # exactly as before -- the in-flight command stream is unchanged.
    if nc.host._plan_version is not None:
        await nc.host._board_sync_tasks(cfg, nc.host._plan_version, plan.tasks)
    return NodeResult(port="ok", payload=plan)


async def seed_spec_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    seeded = nc.facts.seeded
    if seeded is None:
        raise RuntimeError(f"{nc.node.id} activated on a run without SeededWork")
    return NodeResult(port="spec", payload=seeded.arch)


async def seed_plan_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    seeded = nc.facts.seeded
    if seeded is None:
        raise RuntimeError(f"{nc.node.id} activated on a run without SeededWork")
    nc.host._stage("coding", "code")  # feature.py:518 -- the seeded path's only stage event here
    return NodeResult(port="plan", payload=seeded.plan)


async def code_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    plan = input_model(nc, act, "plan")
    assert plan is not None
    done, failure = await run_tasks(nc.host, cfg=cfg, plan=plan, repo_path=nc.facts.repo_path)
    if failure is not None:
        return NodeResult(port="halt", result=failure)
    return NodeResult(port="results", payload=BuildResult(task_results=list(done.values())))


async def analyze_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    results = input_model(nc, act, "results")
    assert results is not None
    plan = input_model(nc, act, "plan")
    assert plan is not None
    integration = nc.facts.integration
    assert integration is not None, "intake sets RunFacts.integration before any post-plan node"
    art = await workflow.execute_activity(
        get_task_diff,
        DiffInput(
            worktree=integration.worktree_path,
            branch_point=nc.facts.base_sha or "",
            label="integration",
        ),
        **pools.on_harness(ACT, cfg.harness_queue),
    )
    # FR-702: the analyst's prompt patch is a bounded read-back of the
    # stored artifact; the payload carries the artifact (metadata + ref).
    # patch_ref=None (propose arm / legacy fakes) -> empty text, NO
    # read-back command (Review Focus 3).
    patch_text = (
        (await workflow.execute_activity(load_diff, LoadDiffInput(ref=art.patch_ref), **ACT)).text
        if art.patch_ref is not None
        else ""
    )
    done = {r.task_id: r for r in results.task_results}
    outcome = await analyze.step(
        nc.ctx,
        cfg=cfg,
        plan=plan,
        task_results=done,
        diff=art,
        patch=patch_text,
        integration_wt=integration.worktree_path,
        base_branch=nc.facts.idea.base_branch,
        base_sha=nc.facts.base_sha,
        analyst_agent=t_analyst,
        analyst_model=resolve_role_model(cfg, "analyze"),
    )
    return NodeResult(
        port="analysis",
        payload=AnalyzeResult(
            report=outcome.report,
            untraced=outcome.untraced,
            integration_diff=art,
        ),
    )


async def merge_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    results = input_model(nc, act, "results")
    assert results is not None
    analysis = input_model(nc, act, "analysis")
    assert analysis is not None
    integration = nc.facts.integration
    assert integration is not None, "intake sets RunFacts.integration before any post-plan node"
    pr_url = await merge.step(
        nc.ctx,
        cfg=cfg,
        task_results=list(results.task_results),
        integration_wt=integration.worktree_path,
        idea=nc.facts.idea,
        arch=input_model(nc, act, "spec"),
        plan=input_model(nc, act, "plan"),
        base_sha=nc.facts.base_sha or "",
        integration_diff=analysis.integration_diff,
        untraced=analysis.untraced,
        merge_agent=t_merge_verdict,
        merge_model=STAGE_MODELS.get("merge_verdict", "unknown"),
    )
    if pr_url.startswith("rejected:"):
        return NodeResult(port="reject", result=pr_url)
    return NodeResult(port="pr", payload=PullRequest(url=pr_url))


async def deploy_node(nc: NodeContext, act: Activation, cfg: PipelineConfig) -> NodeResult:
    pr = input_model(nc, act, "pr")
    assert pr is not None
    out = await deploy.step(
        nc.ctx,
        cfg=cfg,
        deploy_plan=deploy._deploy_plan(cfg, nc.facts.run_id),
        repo_path=nc.facts.repo_path,
        pr_url=pr.url,
    )
    return NodeResult(port="done", result=out)
