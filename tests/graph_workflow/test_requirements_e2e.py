"""FR-113 E2E (spec test-strategy, temporal tier): the default-requirements
graph runs flag-on end to end on the production sandbox.

select_graph picks default-requirements for a requirements_enabled run; the
run ships (deployed:); the requirements stage drafts -> freezes ->
STAGE_ENDED pass (the frozen artifact visible in the exported trace and in
exactly one draft_requirements activity); and the frozen digest reaches
clarify's memo key — the run's clarify memo entry is stored under the
digest-salted key and never under the digest-less one.
"""

from __future__ import annotations

import json

import pytest
from temporalio import activity

from sdlc.core.models import RoleUsage
from sdlc.stages.requirements.models import DraftOutput, DraftStory
from sdlc.stages.requirements.stage import DraftInput, _DraftResult
from sdlc.stages.requirements.verify import freeze
from tests.fakes.canned import AGENT_SPECS, CLARIFIED, e2e_config, greenfield_idea
from tests.fakes.fake_activities import GIT_FAKES
from tests.fakes.fake_agents import fake_agent_activities
from tests.fakes.fake_deploy import DEPLOY_FAKES
from tests.fakes.fake_deploy import reset as reset_deploy
from tests.replay.harness import GRAPH_STARTER, capture
from tests.replay.scenarios import Scenario, _drive_happy, fake_notify

pytestmark = pytest.mark.temporal

# The raw draft the fake drafter returns: one story citing a source_ref,
# one without (greenfield freeze keeps both — the source_ref drop is
# brownfield-only, requirements verify's rules). The expected Requirements
# is the verify module's own output, never re-implemented here.
_DRAFT = DraftOutput(
    stories=[
        DraftStory(
            narrative="As a caller, I want a greeting, so that I can check the service is up.",
            functional=["GET /hello returns 200"],
            success_criteria=["GET /hello responds within 100ms at p95"],
            source_ref="AGENTS.md",
        ),
        DraftStory(
            narrative="As an operator, I want a health check, so that I can monitor the service.",
            functional=["GET /healthz returns 200"],
            success_criteria=[],
            source_ref=None,
        ),
    ]
)
_EXPECTED = freeze(_DRAFT, mode="greenfield").frozen


@activity.defn(name="draft_requirements")
async def fake_draft_requirements(inp: DraftInput) -> _DraftResult:
    """The canned drafter: the raw draft plus its spend, the real activity's
    return contract (freeze stays workflow-side, so the workflow's frozen
    digest is asserted against the run, not the fake)."""
    return _DraftResult(
        draft=_DRAFT,
        usage=RoleUsage(
            role="product",
            model="anthropic:glm-5.2",
            calls=1,
            input_tokens=11,
            output_tokens=7,
        ),
    )


def _requirements_cfg():
    cfg = e2e_config()
    cfg.requirements_enabled = True
    cfg.deploy.enabled = True
    cfg.memoization_enabled = True  # clarify's memo key is an asserted surface
    return cfg


def _requirements_activities() -> list:
    from sdlc.memoization.activities import cache_get, cache_put
    from sdlc.observability.activities import export_run_artifacts
    from sdlc.stages.merge.activities import evaluate_gate

    return [
        evaluate_gate,
        export_run_artifacts,
        fake_notify,
        fake_draft_requirements,
        cache_get,
        cache_put,
        *GIT_FAKES,
        *DEPLOY_FAKES,
        *fake_agent_activities(AGENT_SPECS),
    ]


def _clarify_memo_key(cfg, idea, digest: str) -> str:
    """The key RoleHost._cached_stage derives for clarify, composed from the
    same production helpers (content_key, PROMPT_SHAS, resolve_role_model).
    The two "" slots are brief_digest and constitution_digest — both empty
    on default-requirements (no research node, no constitution node)."""
    from sdlc.agents.roles import PROMPT_SHAS, resolve_role_model
    from sdlc.memoization.cache import content_key
    from sdlc.stages.clarify.prompts import _clarify_memo_extra, prompt_digest

    return content_key(
        "clarify",
        idea.model_dump_json() + "" + "" + digest + _clarify_memo_extra(cfg, None),
        PROMPT_SHAS["clarify"] + prompt_digest(cfg),
        resolve_role_model(cfg, "clarify"),
        "none",  # memory off: no recall watermark
    )


@pytest.mark.asyncio
async def test_default_requirements_graph_runs_flag_on_end_to_end(monkeypatch, tmp_path):
    from sdlc.workflows.graph_catalog import SHIPPED, build_run_input, select_graph
    from sdlc.workflows.graph_nodes.base import graph_has_requirements

    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / "memo"))
    cfg = _requirements_cfg()
    idea = greenfield_idea()

    # the wiring itself: the flag (not a pinned graph) selects the graph
    assert select_graph(cfg, None) is SHIPPED["default-requirements"]
    assert graph_has_requirements(build_run_input(idea, cfg, None).graph)

    scenario = Scenario(
        "requirements_flag_on",
        greenfield_idea,
        _requirements_cfg,
        _requirements_activities,
        _drive_happy,
        before=reset_deploy,
    )
    captured = await capture(scenario, GRAPH_STARTER, monkeypatch, tmp_path, sandboxed=True)

    # the run completes, and the one draft activity crossed the wire
    assert captured.golden["close"].startswith("deployed:")
    assert captured.golden["commands"].count("activity:draft_requirements") == 1

    # the stage finished happy in the exported trace: drafted, priced, pass
    events = [
        json.loads(line)
        for line in (tmp_path / captured.workflow_id / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    usage = [e for e in events if e["kind"] == "model_usage" and e["stage"] == "requirements"]
    assert usage and usage[0]["data"]["role"] == "product"
    ended = [
        e["data"] for e in events if e["kind"] == "stage_ended" and e["stage"] == "requirements"
    ]
    assert len(ended) == 1
    assert ended[0]["role"] == "product"
    assert ended[0]["outcome"] == "pass"  # greenfield freeze kept both stories

    # the frozen digest reached clarify's memo key: the run's clarify entry
    # is stored under the digest-salted key (never under the digest-less one)
    memo_root = tmp_path / "memo"
    salted = memo_root / f"{_clarify_memo_key(cfg, idea, _EXPECTED.digest)}.json"
    assert salted.exists(), sorted(p.name for p in memo_root.glob("*.json"))
    assert json.loads(salted.read_text(encoding="utf-8")) == CLARIFIED.model_dump(mode="json")
    assert not (memo_root / f"{_clarify_memo_key(cfg, idea, '')}.json").exists()
