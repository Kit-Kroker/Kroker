import ast
from pathlib import Path

import pytest

ARCHITECT_PY = (Path(__file__).resolve().parents[1]
                / "agents" / "architect" / "agent.py")


def test_architect_agent_registers_a_research_tool():
    src = ARCHITECT_PY.read_text(encoding="utf-8")
    assert "research" in src
    # A tool named research is registered on the agent.
    tree = ast.parse(src)
    names = {n.name for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "research" in names


def test_research_subquery_shares_the_budget_object():
    """SGR Routing: a mid-run architect research call draws down the SAME
    per-run budget, so it cannot exceed the run's total by opening a second
    counter."""
    import inspect

    from sdlc.research import toolset
    sig = inspect.signature(toolset.research_subquery)
    assert list(sig.parameters)[0] == "deps"     # the shared ResearchDeps


@pytest.mark.asyncio
async def test_research_subquery_degrades_instead_of_raising_on_budget_exceeded(
        monkeypatch):
    """Regression for the infinite-retry hang observed on a cat-cafe-monitoring
    benchmark run: the architect's mid-run research(question) tool executes
    INSIDE its own Temporal activity, so t_research.run() falls back to plain
    in-process tool dispatch there and the shared budget genuinely accumulates
    (unlike the top-level research stage, where each tool call is its own
    fresh activity). Given a question expensive enough to exceed max_searches,
    charge() really does raise BudgetExceeded mid-run. Left uncaught, that
    plain Exception escapes the activity as an ApplicationFailure that
    Temporal retries with no cap (temporal workflow describe showed attempt 9,
    MaximumAttempts 0, retrying forever) — the same failure class the
    read_repo fix in test_research_tools.py addresses for a different tool.
    research_subquery must catch it and degrade to a ResearchBrief with the
    shortfall recorded in gaps, never let it propagate."""
    import sdlc.agents.roles as roles
    from sdlc.research.deps import BudgetExceeded, ResearchDeps

    class _ExhaustedAgent:
        async def run(self, question, deps):
            raise BudgetExceeded(f"search budget exhausted ({deps.max_searches} searches)")

    monkeypatch.setattr(roles, "t_research", _ExhaustedAgent())

    from sdlc.research import toolset
    deps = ResearchDeps(run_id="r1", provider="fake", max_searches=5,
                        max_fetches=10, max_cost_usd=1.0)
    brief = await toolset.research_subquery(deps, "how many collars fit in one zone?")

    assert brief.gaps, "budget exhaustion must land in gaps, not raise"
    assert "search budget exhausted" in brief.gaps[0].why_it_matters
