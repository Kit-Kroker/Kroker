"""The research-retain replay scenario (009, plan D3): one research run with
grounded findings and memory on, driven to `awaiting:clarify`.

This module is NOT a test module and the scenario is NOT a member of
`tests.replay.scenarios.SCENARIOS` (FR-010, A6): membership would force a
golden file and edits to two existing pin tests. Its history fixture is
captured once — from workflow code whose `src/` equals main `d51eef5` — by
`test_research_retain_replay.test_capture_research_retain_history`, which
listens to `SDLC_CAPTURE_RESEARCH_RETAIN`, never to `SDLC_CAPTURE_HISTORIES`.

Modelled on the E5 probe (`.workspace/tmp/research-retain-path-e5.py`),
which measured this exact scenario reaching `awaiting:clarify` with
`verify_brief_activity` once and `retain` three times (one `gate_feedback`
for the research gate plus one `research_finding` per grounded finding).
"""

from __future__ import annotations

from typing import Any

from temporalio import activity

from sdlc.core.models import RoleUsage
from sdlc.memory.activities import capture_watermark, recall_snapshot, retain
from sdlc.stages.research import verify
from sdlc.stages.research.models import (
    GroundedFinding,
    ResearchBrief,
    ResearchPlan,
    SubQuestion,
    SubQuestionFinding,
)
from sdlc.stages.research.stage import PlanInput, SubQuestionInput, SynthesizeInput
from tests.replay import scenarios as S
from tests.replay.scenarios import Scenario

NAME = "research_retain_grounded"

# (url, quote, claim): two grounded findings whose quotes appear verbatim
# in the pages the fake sub-question writes.
FINDINGS: tuple[tuple[str, str, str], ...] = (
    ("https://x/1", "quote one is here", "c1"),
    ("https://x/2", "quote two is here", "c2"),
)


def page_text(quote: str) -> str:
    """The one body builder for a page, used at record time (the fake) and at
    replay time (staging the `present` row)."""
    return f"lead-in. {quote}. tail"


BRIEF = ResearchBrief(
    summary="grounded",
    confidence=0.9,
    grounded_findings=[
        GroundedFinding(source_url=url, quote=quote, claim=claim) for url, quote, claim in FINDINGS
    ],
)


@activity.defn(name="plan_research")
async def plan(inp: PlanInput) -> ResearchPlan:
    return ResearchPlan(sub_questions=[SubQuestion(id="sq-0", question="q")])


@activity.defn(name="research_subquestion")
async def subq(inp: SubQuestionInput) -> SubQuestionFinding:
    for url, quote, _claim in FINDINGS:
        verify.write_page(inp.deps.run_id, url, page_text(quote))
    return SubQuestionFinding(sub_question=inp.sub_question, brief=BRIEF)


@activity.defn(name="synthesize_brief")
async def synth(inp: SynthesizeInput) -> tuple[ResearchBrief, RoleUsage]:
    return BRIEF, RoleUsage(role="research", model="unknown")


def cfg():
    c = S._research_cfg()
    c.memory.enabled = True
    c.memory.backend = "fake"
    return c


def activities():
    base = [a for a in S.SCENARIOS if a.name == "research_greenfield"][0].activities()
    drop = {"plan_research", "research_subquestion", "synthesize_brief"}
    keep = [a for a in base if getattr(a, "__temporal_activity_definition").name not in drop]
    return [*keep, plan, subq, synth, capture_watermark, recall_snapshot, retain]


async def drive(handle: Any, env: Any) -> None:
    await S.wait_for(handle, "awaiting:clarify")


SCENARIO = Scenario(
    NAME,
    S.greenfield_idea,
    cfg,
    activities,
    drive,
    mode="partial",
    golden=False,
)


def stage_pages(wf_id: str, how: str) -> None:
    """Stage the run's page files under the CURRENT `SDLC_RUNS_ROOT` for a
    replay row: `present` (the recorded bytes), `overwritten` (same URLs,
    other bytes) or `absent` (nothing written)."""
    if how == "absent":
        return
    for url, quote, _claim in FINDINGS:
        if how == "present":
            text = page_text(quote)
        else:
            text = "rewritten by a later fetch of the same url"
        verify.write_page(wf_id, url, text)


__all__ = [
    "BRIEF",
    "FINDINGS",
    "NAME",
    "SCENARIO",
    "activities",
    "cfg",
    "drive",
    "page_text",
    "stage_pages",
]
