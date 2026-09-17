"""E-74 §10.1: determinism rules on the graph workflow modules (constraint 6)."""

from __future__ import annotations

import ast
from pathlib import Path

WF = Path(__file__).resolve().parents[2] / "src" / "sdlc" / "workflows"
MODULES = sorted(
    [
        WF / "build.py",
        WF / "graph.py",
        WF / "graph_catalog.py",
        WF / "graph_dispatch.py",
        WF / "pipeline_child.py",
        WF / "run_host.py",
        *sorted((WF / "graph_nodes").glob("*.py")),
    ]
)
ALLOW = "# determinism:"
EXPECTED_ALLOWS = {"build.py": 3, "run_host.py": 1}
BANNED_ATTR_CALLS = {
    ("asyncio", "wait"),
    ("asyncio", "as_completed"),
    ("time", "time"),
    ("uuid", "uuid4"),
    ("datetime", "now"),
    ("datetime", "utcnow"),
}


def _is_unordered_iter(node: ast.expr) -> bool:
    if isinstance(node, (ast.Set, ast.SetComp)):
        return True
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in {"set", "frozenset"}:
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"keys", "values", "items"}:
            return True
    return False


def _violations(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    out: list[str] = []

    tree = ast.parse(src)
    spans = sorted(
        (n.lineno, n.end_lineno or n.lineno) for n in ast.walk(tree) if isinstance(n, ast.stmt)
    )

    def flag(node: ast.AST, why: str) -> None:
        # The allowlist comment may sit on any line of the innermost enclosing
        # statement: ruff format moves trailing comments when it wraps a line.
        line_no = node.lineno
        start, end = min((s for s in spans if s[0] <= line_no <= s[1]), key=lambda s: s[1] - s[0])
        if not any(ALLOW in lines[i - 1] for i in range(start, end + 1)):
            out.append(f"{path.name}:{line_no}: {why}")

    for node in ast.walk(tree):
        if isinstance(node, ast.For) and _is_unordered_iter(node.iter):
            flag(node, "for-loop over an unordered collection; wrap in sorted()")
        if isinstance(node, ast.comprehension) and _is_unordered_iter(node.iter):
            flag(node.iter, "comprehension over an unordered collection; wrap in sorted()")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + (
                [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            )
            if "random" in names:
                flag(node, "random is banned in workflow code")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if (node.value.id, node.attr) in BANNED_ATTR_CALLS:
                flag(node, f"{node.value.id}.{node.attr} is nondeterministic")
            if (node.value.id, node.attr) == ("os", "environ"):
                flag(node, "os.environ read in workflow code")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and (node.func.value.id, node.func.attr) == ("asyncio", "gather")
        ):
            for arg in node.args:
                inner = arg.value if isinstance(arg, ast.Starred) else arg
                ok = isinstance(inner, (ast.List, ast.Tuple)) and not any(
                    isinstance(e, ast.Starred) for e in inner.elts
                )
                ok = ok or (
                    isinstance(inner, ast.ListComp)
                    and all(
                        isinstance(g.iter, ast.Call)
                        and isinstance(g.iter.func, ast.Name)
                        and g.iter.func.id == "sorted"
                        for g in inner.generators
                    )
                )
                if not ok:
                    flag(node, "asyncio.gather over a non-literal, unsorted collection")
    return out


def test_graph_workflow_modules_obey_the_determinism_rules():
    problems = [v for path in MODULES for v in _violations(path)]
    assert problems == []


def test_allowlist_comments_are_counted():
    counts = {p.name: p.read_text(encoding="utf-8").count(ALLOW) for p in MODULES}
    assert {k: v for k, v in counts.items() if v} == EXPECTED_ALLOWS


def test_the_lint_catches_what_it_claims():
    import tempfile

    bad = (
        "import random\n"
        "import asyncio\n"
        "d = {}\n"
        "for k in d.keys():\n"
        "    pass\n"
        "asyncio.gather(*[f(x) for x in d])\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad.py"
        path.write_text(bad, encoding="utf-8")
        assert len(_violations(path)) == 3
