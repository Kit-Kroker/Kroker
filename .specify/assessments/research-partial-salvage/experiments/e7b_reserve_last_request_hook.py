# ruff: noqa: E501 -- experiment harness; report lines carry long f-strings by design
"""E7b: same question as E7, using the before_model_request hook instead of PrepareTools.

Generated from e7_reserve_last_request.py.

Generated from e6_death_state.py (same imports/fixtures, different body).

Original header: what partial state exists when a
research sub-question run dies, and can it be turned into a brief?

Scratch script. Scripted FunctionModel only, temp SDLC_RUNS_ROOT, real
charge_scoped / write_page / verify_brief and the real stage handler
(`_research_subquestion_impl`). No network, no repo writes.

Run: docker exec -i kroker-dev python - < e6_death_state.py
"""

import asyncio
import os
import tempfile

os.environ["SDLC_RUNS_ROOT"] = tempfile.mkdtemp(prefix="e6-")

import pydantic_ai  # noqa: E402
from pydantic_ai import Agent, RunContext  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel  # noqa: E402
from pydantic_ai_harness import CodeMode  # noqa: E402

from sdlc.stages.research.budget_store import charge_scoped  # noqa: E402
from sdlc.stages.research.deps import ResearchDeps  # noqa: E402
from sdlc.stages.research.models import ResearchBrief, SubQuestion  # noqa: E402
from sdlc.stages.research.stage import (  # noqa: E402
    SubQuestionInput,
    _research_subquestion_impl,
)
from sdlc.stages.research.verify import verify_brief, write_page  # noqa: E402

PAGES = {
    f"https://example.org/p{i}": (
        f"Page {i} header. PAGE-{i} verbatim sentence: the limit is {i * 10} requests. Page {i} footer."
    )
    for i in range(1, 9)
}


def fetch_script(i: int) -> str:
    return f'r = await get_page(url="https://example.org/p{i}")\nr'


LIMIT = 4
seen_by_hook = []


import dataclasses  # noqa: E402

from pydantic_ai.capabilities import AbstractCapability  # noqa: E402


class ReserveLast(AbstractCapability):
    """Strip every function tool from the last request the limit allows."""

    async def before_model_request(self, ctx, request_context):
        params = request_context.model_request_parameters
        seen_by_hook.append((ctx.usage.requests, sorted(t.name for t in params.function_tools)))
        if ctx.usage.requests >= LIMIT - 1:
            params = dataclasses.replace(params, function_tools=[])
            return dataclasses.replace(request_context, model_request_parameters=params)
        return request_context


def make_agent(model, order):
    caps = [CodeMode(), ReserveLast()] if order == "codemode-first" else [ReserveLast(), CodeMode()]
    agent = Agent(model, deps_type=ResearchDeps, output_type=ResearchBrief, capabilities=caps)

    @agent.tool
    async def get_page(ctx: RunContext[ResearchDeps], url: str) -> str:
        """Fetch a page."""
        await charge_scoped(
            ctx.deps, fetch=1, scope=ctx.deps.scope, run_max_cost_usd=ctx.deps.max_run_cost_usd
        )
        text = PAGES[url]
        write_page(ctx.deps.run_id, url, text)
        return text

    return agent


def obedient_model(log):
    """Fetches while a function tool is offered; concludes when none is."""
    state = {"n": 0}

    def fn(messages, info):
        offered = sorted(t.name for t in info.function_tools)
        log.append(offered)
        if offered:
            state["n"] += 1
            return ModelResponse(
                parts=[ToolCallPart("run_code", {"code": fetch_script(state["n"])})]
            )
        seen = [
            u
            for m in messages
            for p in m.parts
            if isinstance(p, ToolReturnPart)
            for u, b in PAGES.items()
            if b in str(p.content)
        ]
        grounded = [
            {"source_url": u, "quote": PAGES[u][15:60], "claim": "limit stated"} for u in seen
        ]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "final_result",
                    {"grounded_findings": grounded, "summary": f"concluded on {len(seen)} pages"},
                )
            ]
        )

    return FunctionModel(fn)


def stubborn_model(log):
    """Calls run_code even when it is not offered."""
    state = {"n": 0}

    def fn(messages, info):
        log.append(sorted(t.name for t in info.function_tools))
        state["n"] += 1
        return ModelResponse(parts=[ToolCallPart("run_code", {"code": fetch_script(state["n"])})])

    return FunctionModel(fn)


async def run(label, run_id, model_factory, order):
    print(f"== {label} [{order}]")
    log = []
    seen_by_hook.clear()
    model = model_factory(log)
    agent = make_agent(model, order)
    try:
        out = await _research_subquestion_impl(
            SubQuestionInput(
                sub_question=SubQuestion(id="sq-0", question="q"),
                deps=ResearchDeps(
                    run_id=run_id, provider="fake", max_searches=5, max_fetches=10, max_cost_usd=1.0
                ),
                model="function",
                max_requests=LIMIT,
                max_run_cost_usd=4.0,
            ),
            _model=model,
            _agent=agent,
        )
        v = verify_brief(out.brief, run_id)
        print(
            f"  stage RETURNED failed={out.failed} grounded={len(out.brief.grounded_findings)} summary={out.brief.summary[:60]!r} gaps={len(out.brief.gaps)} violations={len(v)}"
        )
    except Exception as e:  # noqa: BLE001
        print(f"  RAISED {type(e).__name__}: {' '.join(str(e).split())[:160]}")
    print(f"  tools offered to the model per request: {log}")
    print(f"  hook saw (requests so far, tool names): {seen_by_hook}")


async def main():
    print("pydantic_ai", pydantic_ai.__version__, "limit", LIMIT)
    await run("K4 obedient model", "e7-a", obedient_model, "codemode-first")
    await run("K4 obedient model", "e7-b", obedient_model, "prepare-first")
    await run("K4 stubborn model", "e7-c", stubborn_model, "codemode-first")


asyncio.run(main())
