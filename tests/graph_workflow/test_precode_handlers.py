"""E-74 §6: pre-code handlers adapt the stage steps; host mirrors and carry (§5.3, D4)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from sdlc.core.models import GateDecision, GateOutcome, IdeaBrief, PipelineConfig, ProjectMode
from sdlc.graph import NODE_TYPES, from_yaml, validate
from sdlc.graph.router import Activation
from sdlc.vcs import IntegrationHandle, IntegrationInput
from sdlc.workflows.graph_catalog import SHIPPED
from sdlc.workflows.graph_nodes import precode
from sdlc.workflows.graph_nodes.base import NodeContext, RunFacts, StoredPayload
from tests.fakes.canned import ARCH, CLARIFIED, PLAN, greenfield_idea
from tests.graph.fixtures.registries import roles

PRE_CODE = Path(__file__).resolve().parents[1] / "graph" / "fixtures" / "pre_code.graph.yaml"


class Host:
    def __init__(self):
        self._integration_head = ""
        self._base_sha = ""
        self._integration_wt = ""
        self._codebase_map = None
        self._memory_watermark = "wm"
        self.published: list[tuple[str, bool]] = []

    async def _board_publish(self, cfg, key, content_json, *, approved=True):
        self.published.append((key, approved))
        return 7


def _nc(
    node_id: str,
    *,
    graph=None,
    idea: IdeaBrief | None = None,
    payloads=None,
    host=None,
    services=None,
    registry_roles=None,
):
    graph = graph or SHIPPED["default"]
    topology = validate(graph, roles=registry_roles or roles()).topology
    node = next(n for n in graph.nodes if n.id == node_id)
    facts = RunFacts(
        idea=idea or greenfield_idea(),
        repo_path="/fake/repo",
        run_id="wf-1",
        seeded=None,
        memory_watermark="wm",
    )
    return NodeContext(
        ctx=services or SimpleNamespace(),
        host=host or Host(),
        facts=facts,
        node=node,
        spec=NODE_TYPES[node.type],
        topology=topology,
        payloads=payloads or {},
        carries={},
    )


def _act(node_id: str, round_: int = 1, inputs=None) -> Activation:
    return Activation(
        activation_id=f"{node_id}#{round_}",
        node_id=node_id,
        round=round_,
        inputs=inputs or {},
        unavailable_ports={},
    )


def test_intake_sets_up_integration_after_passing_and_mirrors_the_host(monkeypatch):
    calls = []

    async def fake_step(ctx, *, cfg, idea, repo_path):
        calls.append(("intake", repo_path))
        return None

    async def fake_activity(fn, arg, **kw):
        calls.append(("activity", fn.__name__, arg))
        return IntegrationHandle(head_sha="h1", worktree_path="/wt")

    monkeypatch.setattr(precode, "intake", SimpleNamespace(step=fake_step))
    monkeypatch.setattr(precode.workflow, "execute_activity", fake_activity)
    nc = _nc("intake")
    out = asyncio.run(precode.intake_node(nc, _act("intake"), PipelineConfig()))
    assert out.port == "ok"
    assert calls[0] == ("intake", "/fake/repo")
    assert calls[1][2] == IntegrationInput(
        repo_path="/fake/repo", run_id="wf-1", base_branch="main"
    )
    assert (nc.host._integration_head, nc.host._base_sha, nc.host._integration_wt) == (
        "h1",
        "h1",
        "/wt",
    )
    assert nc.facts.base_sha == "h1"


def test_intake_rejection_creates_no_branch(monkeypatch):
    async def fake_step(ctx, *, cfg, idea, repo_path):
        return "rejected:intake (not a git repository)"

    async def no_activity(*a, **k):
        raise AssertionError("no branch on a rejected intake")

    monkeypatch.setattr(precode, "intake", SimpleNamespace(step=fake_step))
    monkeypatch.setattr(precode.workflow, "execute_activity", no_activity)
    out = asyncio.run(precode.intake_node(_nc("intake"), _act("intake"), PipelineConfig()))
    assert (out.port, out.result) == ("reject", "rejected:intake (not a git repository)")


def test_intake_rejects_a_mode_the_graph_has_no_path_for(monkeypatch):
    async def fake_step(ctx, *, cfg, idea, repo_path):
        return None

    async def no_activity(*a, **k):
        raise AssertionError("no branch without a path")

    monkeypatch.setattr(precode, "intake", SimpleNamespace(step=fake_step))
    monkeypatch.setattr(precode.workflow, "execute_activity", no_activity)
    brown = IdeaBrief(title="t", description="d", mode=ProjectMode.BROWNFIELD, repo_url="/r")
    nc = _nc("intake", graph=from_yaml(PRE_CODE.read_text(encoding="utf-8")), idea=brown)
    out = asyncio.run(precode.intake_node(nc, _act("intake"), PipelineConfig()))
    assert out.result == "rejected:intake (graph has no brownfield path)"


def test_clarify_passes_the_research_digest_publishes_and_retains(monkeypatch):
    seen = {}

    async def fake_step(ctx, **kw):
        seen.update(kw)
        return CLARIFIED

    retained = []

    async def retain(cfg, kind, bank, text, metadata):
        retained.append((text, metadata))

    monkeypatch.setattr(precode, "clarify", SimpleNamespace(step=fake_step))
    graph = SHIPPED["default-research"]
    payloads = {
        "research#1.brief": StoredPayload(model=None, producer="research#1", meta={"digest": "d1"})
    }
    nc = _nc("clarify", graph=graph, payloads=payloads, services=SimpleNamespace(retain=retain))
    act = _act("clarify", inputs={"research": "research#1.brief"})
    out = asyncio.run(precode.clarify_node(nc, act, PipelineConfig()))
    assert out.payload is CLARIFIED
    assert seen["brief_digest"] == "d1" and seen["codebase_map"] is None
    assert nc.host.published == [("requirements", True)]
    assert retained == [(f"clarify: {CLARIFIED.summary}", {"stage": "clarify", "run_id": "wf-1"})]


def test_architect_prepares_once_and_reads_guidance(monkeypatch):
    prepared, produced = [], []

    async def fake_prepare(ctx, **kw):
        prepared.append(kw)
        return SimpleNamespace(resolved_model="m-arch")

    async def fake_produce(ctx, prep, **kw):
        produced.append(kw["guidance"])
        return ARCH

    monkeypatch.setattr(precode, "arch_prepare", fake_prepare)
    monkeypatch.setattr(precode, "arch_produce", fake_produce)
    monkeypatch.setattr(precode, "resolve_role_model", lambda cfg, stage: f"model-{stage}")
    decision = GateDecision(
        gate="architecture", outcome=GateOutcome.REVISE, decided_by="human", guidance="g1"
    )
    payloads = {
        "clarify#1.requirements": StoredPayload(model=CLARIFIED, producer="clarify#1"),
        "architecture#1.revise": StoredPayload(model=decision, producer="architecture#1"),
    }
    nc = _nc("architect", payloads=payloads)
    first = asyncio.run(
        precode.architect_node(
            nc, _act("architect", 1, {"requirements": "clarify#1.requirements"}), PipelineConfig()
        )
    )
    second = asyncio.run(
        precode.architect_node(
            nc,
            _act(
                "architect",
                2,
                {"requirements": "clarify#1.requirements", "guidance": "architecture#1.revise"},
            ),
            PipelineConfig(),
        )
    )
    assert len(prepared) == 1 and prepared[0]["architect_model"] == "model-architect"
    assert produced == [None, "g1"]
    assert (first.port, first.author_model, second.payload) == ("spec", "m-arch", ARCH)


# ---- constitution (FR-112 Task 7) ----------------------------------------------


def _constitution_graph():
    from sdlc.graph import from_yaml
    from sdlc.workflows.graph_catalog import GRAPHS_DIR

    return from_yaml((GRAPHS_DIR / "default-constitution.graph.yaml").read_text(encoding="utf-8"))


def _constitution_roles():
    from sdlc.core.models import RoleConfig

    return roles(constitution=RoleConfig(kind="proposer", model="anthropic:glm-5.2"))


def _constitution_nc(**kw):
    kw.setdefault("graph", _constitution_graph())
    kw.setdefault("registry_roles", _constitution_roles())
    return _nc("constitution", **kw)


def test_constitution_node_flag_off_schedules_nothing(monkeypatch):
    """A constitution node with the flag force-disabled: the handler runs
    (the node is present) but the step's fast path schedules zero activities
    and emits the empty artifact -- identical to no constitution stage."""
    from sdlc.stages.constitution.models import Constitution

    async def no_activity(*a, **k):
        raise AssertionError("flag off must schedule zero activities")

    monkeypatch.setattr(precode.workflow, "execute_activity", no_activity)
    out = asyncio.run(
        precode.constitution_node(_constitution_nc(), _act("constitution"), PipelineConfig())
    )
    assert out.port == "constitution"
    assert out.payload == Constitution(drafted_by="empty", principles=[], digest="")


def test_constitution_node_freezes_and_emits_the_payload(monkeypatch):
    """Flag on: the handler drives the real step, the activity's raw draft is
    frozen workflow-side, and the payload IS the Constitution."""
    from sdlc.core.models import RoleUsage
    from sdlc.stages.constitution.models import DraftOutput, DraftPrinciple
    from sdlc.stages.constitution.stage import _DraftResult

    scheduled = []

    class _Services:
        def stage(self, status, trace=None):
            return None

        def emit(self, kind, stage=None, **data):
            return None

        async def retain(self, cfg, kind, bank, text, metadata):
            return None

    async def fake_execute(fn, inp, **kw):
        scheduled.append((fn.__temporal_activity_definition.name, inp))
        if fn.__temporal_activity_definition.name == "draft_constitution":
            return _DraftResult(
                draft=DraftOutput(
                    principles=[
                        DraftPrinciple(
                            statement="s1",
                            normative="MUST",
                            rationale="r",
                            source_ref="AGENTS.md",
                        )
                    ]
                ),
                usage=RoleUsage(role="constitution", model="m", input_tokens=1, output_tokens=1),
            )
        if fn.__temporal_activity_definition.name == "price_usage":
            return 0.0
        raise AssertionError(scheduled[-1][0])

    monkeypatch.setattr(precode.workflow, "execute_activity", fake_execute)
    cfg = PipelineConfig(constitution_enabled=True)
    nc = _constitution_nc(services=_Services())
    out = asyncio.run(precode.constitution_node(nc, _act("constitution"), cfg))
    assert out.port == "constitution"
    assert out.payload.principles[0].id == "CP-1"
    assert out.payload.digest
    assert scheduled[0][1].model  # the resolved constitution model crossed the boundary


def test_constitution_node_refuses_a_worker_without_the_agent(monkeypatch):
    monkeypatch.setattr(precode, "t_constitution", None)
    with pytest.raises(RuntimeError, match="agents/constitution"):
        asyncio.run(
            precode.constitution_node(_constitution_nc(), _act("constitution"), PipelineConfig())
        )


def test_downstream_handlers_receive_object_and_digest_from_one_payload(monkeypatch):
    """Ruling (d): clarify/architect/plan get the constitution OBJECT and
    constitution_digest=c.digest -- both read from the same stored payload, so
    the prompt and the memo key can never move apart. Without the input
    (the default graph): None and "" -- byte-identical calls to today."""
    from tests.fakes.canned import CONSTITUTION

    seen: dict[str, dict] = {}

    async def fake_clarify(ctx, **kw):
        seen["clarify_with"] = kw
        return CLARIFIED

    async def fake_clarify_plain(ctx, **kw):
        seen["clarify_without"] = kw
        return CLARIFIED

    async def fake_prepare(ctx, **kw):
        return SimpleNamespace(resolved_model="m")

    async def fake_arch_produce(ctx, prep, **kw):
        seen["architect"] = kw
        return ARCH

    async def fake_plan_produce(ctx, prep, **kw):
        seen["plan"] = kw
        return PLAN

    async def retain(cfg, kind, bank, text, metadata):
        return None

    payloads = {
        "constitution#1.constitution": StoredPayload(model=CONSTITUTION, producer="constitution#1"),
        "clarify#1.requirements": StoredPayload(model=CLARIFIED, producer="clarify#1"),
        "architect#1.spec": StoredPayload(model=ARCH, producer="architect#1"),
    }

    graph = _constitution_graph()
    reg_roles = _constitution_roles()

    # clarify, with a constitution input
    monkeypatch.setattr(precode, "clarify", SimpleNamespace(step=fake_clarify))
    nc = _nc(
        "clarify",
        graph=graph,
        registry_roles=reg_roles,
        payloads=payloads,
        services=SimpleNamespace(retain=retain),
    )
    asyncio.run(
        precode.clarify_node(
            nc,
            _act("clarify", inputs={"constitution": "constitution#1.constitution"}),
            PipelineConfig(),
        )
    )
    assert seen["clarify_with"]["constitution"] is CONSTITUTION
    assert seen["clarify_with"]["constitution_digest"] == CONSTITUTION.digest

    # clarify, without one (the default graph): object None, digest ""
    monkeypatch.setattr(precode, "clarify", SimpleNamespace(step=fake_clarify_plain))
    plain = _nc("clarify", services=SimpleNamespace(retain=retain))
    asyncio.run(precode.clarify_node(plain, _act("clarify"), PipelineConfig()))
    assert (
        seen["clarify_without"]["constitution"],
        seen["clarify_without"]["constitution_digest"],
    ) == (
        None,
        "",
    )

    # architect, with a constitution input
    monkeypatch.setattr(precode, "arch_prepare", fake_prepare)
    monkeypatch.setattr(precode, "arch_produce", fake_arch_produce)
    arch_nc = _nc("architect", graph=graph, registry_roles=reg_roles, payloads=payloads)
    asyncio.run(
        precode.architect_node(
            arch_nc,
            _act(
                "architect",
                inputs={
                    "requirements": "clarify#1.requirements",
                    "constitution": "constitution#1.constitution",
                },
            ),
            PipelineConfig(),
        )
    )
    assert seen["architect"]["constitution"] is CONSTITUTION
    assert seen["architect"]["constitution_digest"] == CONSTITUTION.digest

    # planner, with a constitution input
    monkeypatch.setattr(precode, "plan_prepare", fake_prepare)
    monkeypatch.setattr(precode, "plan_produce", fake_plan_produce)
    plan_nc = _nc("planner", graph=graph, registry_roles=reg_roles, payloads=payloads)
    asyncio.run(
        precode.plan_node(
            plan_nc,
            _act(
                "planner",
                inputs={
                    "spec": "architect#1.spec",
                    "requirements": "clarify#1.requirements",
                    "constitution": "constitution#1.constitution",
                },
            ),
            PipelineConfig(),
        )
    )
    assert seen["plan"]["constitution"] is CONSTITUTION
    assert seen["plan"]["constitution_digest"] == CONSTITUTION.digest
