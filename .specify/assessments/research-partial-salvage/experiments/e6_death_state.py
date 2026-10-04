# ruff: noqa: E501 -- experiment harness; report lines carry long f-strings by design
"""E6 (assessment research-partial-salvage): what partial state exists when a
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
from pydantic_ai import Agent, RunContext, capture_run_messages  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel  # noqa: E402
from pydantic_ai.usage import RunUsage, UsageLimits  # noqa: E402
from pydantic_ai_harness import CodeMode  # noqa: E402

from sdlc.stages.research.budget_store import charge_scoped  # noqa: E402
from sdlc.stages.research.deps import ResearchDeps  # noqa: E402
from sdlc.stages.research.models import ResearchBrief, SubQuestion  # noqa: E402
from sdlc.stages.research.stage import (  # noqa: E402
    SubQuestionInput,
    _research_subquestion_impl,
)
from sdlc.stages.research.verify import pages_dir, verify_brief, write_page  # noqa: E402

PAGES = {
    f"https://example.org/p{i}": (
        f"Page {i} header. PAGE-{i} verbatim sentence: the limit is {i * 10} requests. Page {i} footer."
    )
    for i in range(1, 9)
}


def fetch_script(i: int) -> str:
    return f'r = await get_page(url="https://example.org/p{i}")\nr'


def make_agent(model, *, code_mode=True):
    caps = [CodeMode()] if code_mode else []
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


def deps(run_id, max_fetches=10):
    return ResearchDeps(
        run_id=run_id, provider="fake", max_searches=5, max_fetches=max_fetches, max_cost_usd=1.0
    )


def inp(run_id, max_requests=40, max_fetches=10):
    return SubQuestionInput(
        sub_question=SubQuestion(id="sq-0", question="what is the request limit?"),
        deps=deps(run_id, max_fetches),
        model="function",
        max_requests=max_requests,
        max_run_cost_usd=4.0,
    )


def fetching_model():
    """Fetches a new page every turn and never concludes."""
    state = {"n": 0}

    def fn(messages, info):
        state["n"] += 1
        return ModelResponse(parts=[ToolCallPart("run_code", {"code": fetch_script(state["n"])})])

    return FunctionModel(fn)


def bad_output_model():
    """Fetches one page, then emits a schema-invalid final brief forever."""
    state = {"n": 0}

    def fn(messages, info):
        state["n"] += 1
        if state["n"] == 1:
            return ModelResponse(parts=[ToolCallPart("run_code", {"code": fetch_script(1)})])
        return ModelResponse(parts=[ToolCallPart("final_result", {"confidence": 7})])

    return FunctionModel(fn)


def describe(messages):
    kinds = []
    returns = retries = calls = 0
    chars = 0
    page_hits = set()
    for m in messages:
        tag = "REQ" if isinstance(m, ModelRequest) else "RESP"
        names = []
        for p in m.parts:
            names.append(type(p).__name__)
            if isinstance(p, ToolReturnPart):
                returns += 1
                text = str(p.content)
                chars += len(text)
                for url, body in PAGES.items():
                    if body in text:
                        page_hits.add(url)
            elif isinstance(p, RetryPromptPart):
                retries += 1
            elif isinstance(p, ToolCallPart):
                calls += 1
        kinds.append(f"{tag}[{','.join(names)}]")
    print(
        f"  messages={len(messages)} tool_calls={calls} tool_returns={returns} retry_prompts={retries}"
    )
    print(f"  tool-return chars={chars}; full page bodies present in history: {len(page_hits)}")
    print(f"  last two: {kinds[-2:]}")
    dangling = isinstance(messages[-1], ModelResponse) and any(
        isinstance(p, ToolCallPart) for p in messages[-1].parts
    )
    print(f"  history ends in an unanswered tool call: {dangling}")
    return page_hits


def wrapup_model(log, *, fabricate=False):
    """One-shot: reads the history it is handed, quotes a page body it can see."""

    def fn(messages, info):
        seen = []
        for m in messages:
            for p in m.parts:
                if isinstance(p, ToolReturnPart):
                    for url, body in PAGES.items():
                        if body in str(p.content) and url not in seen:
                            seen.append(url)
        log["seen"] = list(seen)
        log["tools_offered"] = sorted(t.name for t in info.function_tools)
        log["output_tools"] = sorted(t.name for t in info.output_tools)
        log["n_messages"] = len(messages)
        grounded = []
        for url in seen:
            body = PAGES[url]
            quote = "a sentence that is not on the page" if fabricate else body[15:60]
            grounded.append({"source_url": url, "quote": quote, "claim": "limit stated"})
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "final_result",
                    {"grounded_findings": grounded, "summary": f"partial: {len(seen)} pages"},
                )
            ]
        )

    return FunctionModel(fn)


async def die(label, run_id, model, *, via_stage, max_requests=40, max_fetches=10):
    print(f"\n== {label}")
    agent = make_agent(model)
    usage = RunUsage()
    with capture_run_messages() as messages:
        try:
            if via_stage:
                out = await _research_subquestion_impl(
                    inp(run_id, max_requests, max_fetches), _model=model, _agent=agent
                )
                print(
                    f"  stage RETURNED failed={out.failed} grounded={len(out.brief.grounded_findings)} "
                    f"sources={len(out.brief.sources_consulted)} gaps={[g.why_it_matters for g in out.brief.gaps]}"
                )
                print(f"  usage in={out.usage.input_tokens} out={out.usage.output_tokens}")
            else:
                await agent.run(
                    "go",
                    deps=deps(run_id, max_fetches),
                    usage_limits=UsageLimits(request_limit=max_requests),
                    usage=usage,
                )
                print("  completed (unexpected)")
        except Exception as e:  # noqa: BLE001
            print(f"  RAISED {type(e).__name__}: {' '.join(str(e).split())[:140]}")
    describe(messages)
    d = pages_dir(run_id)
    n = len(list(d.glob("*.txt"))) if d.exists() else 0
    print(f"  page files on disk: {n} (file names are sha256(url); no url index)")
    return list(messages), agent


async def wrap(
    label, run_id, history, agent, *, fabricate=False, toolless=False, prior_requests=None
):
    print(f"\n-- {label}")
    log = {}
    model = wrapup_model(log, fabricate=fabricate)
    runner = Agent(model, deps_type=ResearchDeps, output_type=ResearchBrief) if toolless else agent
    usage = RunUsage()
    limits = UsageLimits(request_limit=1)
    if prior_requests is not None:
        usage = RunUsage(requests=prior_requests)
        limits = UsageLimits(request_limit=prior_requests + 1)
    try:
        result = await runner.run(
            "Stop researching. Conclude now with what you have already fetched.",
            deps=deps(run_id),
            message_history=history,
            model=model,
            usage_limits=limits,
            usage=usage,
        )
    except Exception as e:  # noqa: BLE001
        print(f"  wrap-up RAISED {type(e).__name__}: {' '.join(str(e).split())[:200]}")
        print(f"  model was reached: {bool(log)}")
        return
    brief = result.output
    print(
        f"  completed: requests={usage.requests} model saw {log['n_messages']} messages, "
        f"{len(log['seen'])} page bodies; tools offered={log['tools_offered']} "
        f"output tools={log['output_tools']}"
    )
    violations = verify_brief(brief, run_id)
    print(
        f"  brief: grounded={len(brief.grounded_findings)} summary={brief.summary!r}; "
        f"verify_brief violations={[(v.kind) for v in violations]}"
    )


async def main():
    print("pydantic_ai", pydantic_ai.__version__)

    h1, a1 = await die(
        "D1 request limit (max_requests=3), through the real stage handler",
        "e6-d1",
        fetching_model(),
        via_stage=True,
        max_requests=3,
    )
    await wrap("W1a same agent, history from D1, fresh usage, limit 1", "e6-d1", h1, a1)
    await wrap("W1b toolless agent, history from D1", "e6-d1", h1, a1, toolless=True)
    await wrap("W1c same agent, fabricated quote", "e6-d1", h1, a1, fabricate=True)
    await wrap(
        "W1d same agent, carried request count 3, limit 3+1", "e6-d1", h1, a1, prior_requests=3
    )

    h2, a2 = await die(
        "D2 N4 after a refused fetch (max_fetches=2), through the real stage handler",
        "e6-d2",
        fetching_model(),
        via_stage=True,
        max_fetches=2,
    )
    await wrap("W2a same agent, history from D2", "e6-d2", h2, a2)
    await wrap("W2b toolless agent, history from D2", "e6-d2", h2, a2, toolless=True)

    h3, a3 = await die(
        "D3 output-validation exhaustion (no refusal), direct run",
        "e6-d3",
        bad_output_model(),
        via_stage=False,
    )
    await wrap("W3a same agent, history from D3", "e6-d3", h3, a3)

    h4, a4 = await die(
        "D4 = D3 through the real stage handler (expected: raises, Temporal would retry)",
        "e6-d4",
        bad_output_model(),
        via_stage=True,
    )


asyncio.run(main())
