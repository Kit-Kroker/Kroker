"""Spec D3: the tool layer must stay framework-free so E-11 can reuse it."""
import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "sdlc" / "operator"
FORBIDDEN = ("pydantic_ai", "fastapi", "starlette")


def imported_roots(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_agent_py_may_know_about_frameworks():
    for path in SRC.glob("*.py"):
        if path.name == "agent.py":
            continue
        offenders = imported_roots(path) & set(FORBIDDEN)
        assert not offenders, f"{path.name} imports {offenders}"


def test_agent_py_is_the_one_that_does():
    assert "pydantic_ai" in imported_roots(SRC / "agent.py")
