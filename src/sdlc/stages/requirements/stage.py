"""The requirements drafting activity (FR-113, plan Task 6): the stage's
ONLY model-call site. The workflow stays deterministic; this activity runs
the product drafter registry agent once, over a read-only workspace, and
hands the RAW draft back alongside its spend.

The return is deliberately NOT a Requirements: freeze() (verify.py) assigns
US/FR/SC ids and the digest workflow-side (Task 8), and an activity that
calls a model must hand its usage back as a RoleUsage or the spend is
silently lost (E-33 amendment -- the same rule research's fan-out and
constitution's drafting activities follow).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from pydantic import BaseModel
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_ai.workspaces import LocalWorkspaceBackend
from temporalio import activity

from ...core.models import RoleUsage
from .deps import RequirementsDeps
from .models import DraftOutput


class DraftInput(BaseModel):
    """One drafting run's whole input (crosses the activity boundary as data).

    `repo_path` is the brownfield checkout; None (or a path that is not a
    directory) means the run gets an empty scratch workspace AND a
    greenfield prompt -- the workspace branch is the one source of truth
    for both, so the prompt can never instruct repo citation over a tree
    the agent cannot read (`deps.mode` remains the freeze contract).
    """

    idea_json: str
    repo_path: str | None
    deps: RequirementsDeps
    model: str


class _DraftResult(BaseModel):
    """The raw draft plus its model spend. freeze() is the workflow's job
    (Task 8); this activity never returns a Requirements."""

    draft: DraftOutput
    usage: RoleUsage


def _role_usage(run_usage: RunUsage, model: str) -> RoleUsage:
    """One pydantic-ai run's usage as a RoleUsage. The role is the REGISTRY
    name ("product" -- STAGE_ROLES reconciles 'requirements' the stage to
    it) because usage is priced and attributed per role, not per stage.
    cost_usd stays None: dollars are a lookup the WORKFLOW performs via
    price_usage, because pricing must stay replay-safe and must never fail
    a stage."""
    return RoleUsage(
        role="product",
        model=model,
        calls=1,
        input_tokens=run_usage.input_tokens or 0,
        output_tokens=run_usage.output_tokens or 0,
        cache_read_tokens=run_usage.cache_read_tokens or 0,
        cache_write_tokens=run_usage.cache_write_tokens or 0,
        cost_usd=None,
    )


def _scratch_workspace(run_id: str) -> LocalWorkspaceBackend:
    """The greenfield workspace: the run's scratch dir under
    $SDLC_RUNS_ROOT (default CWD-relative `runs/` -- the same root
    research's budget_store/pages and constitution's scratch use), created
    empty before the run. The FileSystem capability fails a workspace-less
    run at start, so an empty tree is still a tree: the drafter reads
    nothing and drafts from the idea alone."""
    root = Path(os.environ.get("SDLC_RUNS_ROOT", "runs"))
    scratch = root / run_id / "requirements"
    scratch.mkdir(parents=True, exist_ok=True)
    return LocalWorkspaceBackend(scratch)


def _repo_workspace(inp: DraftInput) -> LocalWorkspaceBackend | None:
    """The brownfield workspace: the repo checkout, when repo_path names an
    existing directory; None otherwise. This one predicate is the single
    source of truth BOTH the workspace fallback and the prompt's mode line
    derive from, so mode and readability can never diverge."""
    if inp.repo_path and Path(inp.repo_path).is_dir():
        return LocalWorkspaceBackend(inp.repo_path)
    return None


def _draft_prompt(inp: DraftInput, *, repo_attached: bool) -> str:
    """The user prompt. The system prompt (agents/product/instructions.md)
    already fixes the method, the story shape, and the source_ref rules
    (exactly one repo-relative path, no line numbers, never quote
    contents); this only carries the run's particulars: the idea, the mode,
    the two caps.

    The mode line derives from the RESOLVED WORKSPACE, not deps.mode: the
    brownfield instruction ("read the repo... cite source_ref") is only
    truthful when the repo branch was actually taken. Keying it off
    deps.mode instead would let a brownfield mode over a missing repo_path
    instruct the model to cite files it cannot read -- inviting
    hallucinated refs that pass the path-only shape. deps.mode remains the
    FREEZE contract (verify.py, Task 8); the prompt speaks only to what
    this run can actually read."""
    if repo_attached:
        mode_line = (
            "Mode: brownfield — the repo at the workspace root is the source "
            "of truth. Read it with your tools; every story must cite exactly "
            "one repo-relative file path as its source_ref."
        )
    else:
        mode_line = (
            "Mode: greenfield — there is no repo to read. Draft from the "
            "idea alone and leave source_ref unset."
        )
    return (
        f"Feature idea (JSON):\n\n{inp.idea_json}\n\n"
        f"{mode_line}\n\n"
        f"Propose at most {inp.deps.max_stories} user stories — each "
        f"functional requirement and each success criterion one testable "
        f"sentence, and no ids of your own (code assigns US/FR/SC ids when "
        f"freezing). Stay within at most {inp.deps.max_requests} model "
        f"requests."
    )


async def _draft_requirements_impl(inp: DraftInput, _model=None, _agent=None) -> _DraftResult:
    """Run the product drafter once and return the RAW draft.

    Runs the registry `product_agent` in-activity (pydantic-ai falls back
    to in-process execution inside an activity), bounded by
    UsageLimits(request_limit=inp.deps.max_requests). A UsageLimitExceeded
    degrades to an EMPTY draft -- never a raise: the bound is config, so a
    retry hits the same exhausted cap and burns the attempt budget for a
    guaranteed failure; the workflow-side freeze handles the empty case.
    Any OTHER exception propagates for the activity retry policy. The
    caller-owned run_usage survives an abort and holds every completed
    request's spend, so even a degraded draft is priced.

    Single retry layer (004): the loader-supplied capability on the
    registry agent already turns SDK retries off -- NOT re-added here. The
    run is short, so no heartbeat (research's timer is for minutes-long
    sub-questions, not one draft).

    `_model` / `_agent` are test seams; production passes neither.
    """
    if _agent is None:
        from sdlc.agents.roles import product_agent

        if product_agent is None:
            raise RuntimeError("product agent is not available (agents/product/ missing)")
        agent = product_agent
    else:
        agent = _agent

    # One predicate decides both facts: which workspace the run gets, and
    # whether the prompt may instruct repo citation at all.
    repo = _repo_workspace(inp)
    workspace = repo if repo is not None else _scratch_workspace(inp.deps.run_id)
    run_usage = RunUsage()
    usage_limits = UsageLimits(request_limit=inp.deps.max_requests)
    prompt = _draft_prompt(inp, repo_attached=repo is not None)
    try:
        if _model is not None:
            result = await agent.run(
                prompt,
                deps=inp.deps,
                usage_limits=usage_limits,
                model=_model,
                usage=run_usage,
                workspace=workspace,
            )
        else:
            # 004 D7a (FR-001 path b): forward the resolved model only when
            # it differs from the registry one; an equal or absent override
            # calls exactly as before, so no-override behaviour and replays
            # are untouched.
            from sdlc.agents.roles import REGISTRY

            registry_model = REGISTRY["product"].model
            if registry_model is not None and inp.model != registry_model:
                result = await agent.run(
                    prompt,
                    deps=inp.deps,
                    usage_limits=usage_limits,
                    model=inp.model,
                    usage=run_usage,
                    workspace=workspace,
                )
            else:
                result = await agent.run(
                    prompt,
                    deps=inp.deps,
                    usage_limits=usage_limits,
                    usage=run_usage,
                    workspace=workspace,
                )
    except UsageLimitExceeded as exc:
        # Expected exhaustion: degrade ONCE. NEVER re-raise -- the bound is
        # config, so a retry hits the same exhausted cap and burns the
        # attempt budget for a guaranteed failure. The caller-owned
        # run_usage survives the abort and holds every completed request's
        # spend; a run refused before any request completed reports a
        # zero-spend RoleUsage (calls=0), so pricing never charges a call
        # that made no request (research's distinction, 008 FR-001/FR-002).
        activity.logger.info("requirements draft degraded: %s", exc)
        if run_usage.input_tokens or run_usage.output_tokens:
            usage = _role_usage(run_usage, inp.model)
        else:
            usage = RoleUsage(role="product", model=inp.model)
        return _DraftResult(draft=DraftOutput(), usage=usage)

    # The agent's output_type IS DraftOutput; the generic run() result is
    # untyped, so state the contract here.
    return _DraftResult(
        draft=cast(DraftOutput, result.output),
        usage=_role_usage(run_usage, inp.model),
    )


@activity.defn(name="draft_requirements")
async def draft_requirements(inp: DraftInput) -> _DraftResult:
    """Thin activity wrapper -- see research stage.py `plan_research`'s
    docstring for why the `_model`/`_agent` test seams cannot live on the
    registered activity's own signature (Temporal discards ALL arg type
    hints the moment the payload count sent by the caller doesn't match the
    signature's param count, so a seam param would silently turn `inp`
    back into a plain dict)."""
    return await _draft_requirements_impl(inp)


# The slice's worker registration (the research activities.py role): the
# activity and its registration list live together.
ACTIVITIES: list = [draft_requirements]
