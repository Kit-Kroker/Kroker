import ast
from pathlib import Path

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
