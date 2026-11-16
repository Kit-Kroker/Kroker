"""Static call-site guard: every harness activity call is routed (024 T024; R3/R4 layer 1).

Walks the AST of every ``src/sdlc/**/*.py`` and classifies each activity
scheduling call by the activity it names (a function ``Name`` resolved through
the registered activities, or a string ``Constant``).

A *site* is a direct ``workflow.execute_activity`` / ``workflow.start_activity``
call, or a call to a **forwarding function**: any function or method one of
whose positional parameters is passed on, as the activity, to a scheduler or to
another forwarding function. Forwarders are found across the whole tree by
fixpoint (``merge/step.py:_exec_activity``, ``triage.py:_one`` ->
``fanout.py:run_or_degrade`` -> the scheduler). Callees match by bare name or
by method name (``self._one``); method calls do not count ``self``.

Rules (all offenders are listed ``file:line`` in one assertion message):

1. A harness-class activity site routes through ``on_harness``: a call to
   ``<anything>.on_harness(...)`` among its arguments, as a ``**`` splat or as a
   value passed on to a forwarder (call sites use ``pools.on_harness``).
2. A core-class activity site has no ``task_queue=`` keyword and no
   ``on_harness`` call.
3. Nothing aliases ``workflow.execute_activity`` / ``workflow.start_activity``
   (any use other than calling it), so the walk cannot be dodged.
4. No ``workflow.execute_local_activity`` call names a harness activity.

RED until T026-T028 route the harness sites (research R3's 33, plus the
analyze-stage and triage-probe sites R3's grep missed).
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "sdlc"
SCHEDULERS = {"execute_activity", "start_activity"}

Classes = tuple[dict[str, str], frozenset[str], set[str]]


def _is_workflow_attr(node: ast.AST, names: set[str]) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr in names
        and isinstance(node.value, ast.Name)
        and node.value.id == "workflow"
    )


def _is_on_harness_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "on_harness"
    )


def _routed(call: ast.Call) -> bool:
    values = [*call.args, *(k.value for k in call.keywords)]
    return any(_is_on_harness_call(v) for v in values)


def _callee_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _parse_tree() -> dict[str, ast.Module]:
    root = SRC.parent.parent
    return {
        p.relative_to(root).as_posix(): ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for p in sorted(SRC.rglob("*.py"))
    }


def _forwarders(trees: dict[str, ast.Module]) -> dict[str, set[int]]:
    """name -> call-site argument indices that carry the activity (whole-tree fixpoint)."""
    fns: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
        n
        for t in trees.values()
        for n in ast.walk(t)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    found: dict[str, set[int]] = {}
    changed = True
    while changed:
        changed = False
        for fn in fns:
            params = [a.arg for a in fn.args.posonlyargs + fn.args.args]
            shift = 1 if params[:1] in (["self"], ["cls"]) else 0
            for call in ast.walk(fn):
                if not isinstance(call, ast.Call):
                    continue
                if _is_workflow_attr(call.func, SCHEDULERS):
                    indices = {0}
                else:
                    name = _callee_name(call)
                    indices = found.get(name, set()) if name else set()
                for i in indices:
                    if i >= len(call.args) or isinstance(call.args[i], ast.Starred):
                        continue
                    arg = call.args[i]
                    if isinstance(arg, ast.Name) and arg.id in params:
                        idx = params.index(arg.id) - shift
                        if idx >= 0 and idx not in found.setdefault(fn.name, set()):
                            found[fn.name].add(idx)
                            changed = True
    return found


@pytest.fixture(scope="module")
def classes() -> Classes:
    """(function name -> activity name, harness names, every registered activity name)."""
    from sdlc.pools import HARNESS_ACTIVITIES
    from sdlc.worker import get_worker_activities

    by_func: dict[str, str] = {}
    for act in get_worker_activities():
        defn: Any = act.__temporal_activity_definition  # type: ignore[attr-defined]
        by_func[act.__name__] = defn.name
        by_func.setdefault(defn.name, defn.name)
    return by_func, HARNESS_ACTIVITIES, set(by_func.values())


def _resolve(arg: ast.expr, by_func: dict[str, str], aliases: dict[str, str]) -> str | None:
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.Name):
        return by_func.get(aliases.get(arg.id, arg.id))
    return None


def test_harness_sites_routed(classes: Classes) -> None:
    by_func, harness, registered = classes
    trees = _parse_tree()
    forwarders = _forwarders(trees)
    offenders: list[tuple[str, str]] = []
    sites = 0

    for rel, tree in trees.items():
        aliases = {
            a.asname: a.name
            for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom)
            for a in n.names
            if a.asname
        }

        # Rule 3: workflow.execute_activity / start_activity only ever appear as a call target.
        call_targets = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and _is_workflow_attr(n, SCHEDULERS):
                if id(n) not in call_targets:
                    offenders.append(
                        (rel, f"{rel}:{n.lineno}: rule 3: scheduler used other than as a call")
                    )
            if (
                isinstance(n, ast.ImportFrom)
                and (n.module or "").endswith("workflow")
                and any(a.name in SCHEDULERS for a in n.names)
            ):
                offenders.append(
                    (rel, f"{rel}:{n.lineno}: rule 3: scheduler imported by bare name")
                )

        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            if _is_workflow_attr(n.func, {"execute_local_activity"}):
                nm = _resolve(n.args[0], by_func, aliases) if n.args else None
                if nm in harness:
                    offenders.append(
                        (rel, f"{rel}:{n.lineno}: rule 4: local activity {nm!r} is harness")
                    )
                continue
            if _is_workflow_attr(n.func, SCHEDULERS):
                indices = {0}
            else:
                callee = _callee_name(n)
                indices = forwarders.get(callee, set()) if callee else set()
            for i in sorted(indices):
                if i >= len(n.args):
                    continue
                name = _resolve(n.args[i], by_func, aliases)
                if name is None or name not in registered:
                    continue  # indirect (a parameter) or not a registered activity
                sites += 1
                routed = _routed(n)
                if name in harness and not routed:
                    offenders.append(
                        (rel, f"{rel}:{n.lineno}: rule 1: harness {name!r} not routed")
                    )
                if name not in harness and (
                    routed or any(k.arg == "task_queue" for k in n.keywords)
                ):
                    offenders.append(
                        (rel, f"{rel}:{n.lineno}: rule 2: core {name!r} must stay unrouted")
                    )

    assert sites, "the walk found no activity call sites at all; the test is broken"
    census = Counter(rel for rel, _ in offenders)
    summary = "\n".join(f"  {c:2d} {f}" for f, c in sorted(census.items()))
    listing = "\n".join(msg for _, msg in sorted(offenders))
    assert not offenders, (
        f"{len(offenders)} offending site(s) over {sites} resolved sites.\n"
        f"per file:\n{summary}\n{listing}"
    )


# ------------------------------------------------------------------ start paths
# 024 T029 (R6, static layer). Every product start path must resolve the harness
# queue (``resolve_harness_queue``) before it starts a workflow or a schedule.

# update_schedule has no caller today; it is in the set so a future one is guarded.
START_CALLS = {"start_workflow", "create_schedule", "update_schedule"}
# The demo drives its own demo queue, not the product start paths.
START_ALLOWLIST = {"src/sdlc/demo/run.py"}
EXPECTED_START_SITES = {
    "src/sdlc/graph/start.py": 1,  # start_graph_run
    "src/sdlc/cli.py": 3,  # three direct client.start_workflow sites
    "src/sdlc/benchmarks/cli.py": 1,
    "src/sdlc/maintenance/cli.py": 1,
    "src/sdlc/schedules/apply.py": 1,  # create_schedule inside apply_changes
}


def _is_workflow_defn_class(node: ast.AST) -> bool:
    if not isinstance(node, ast.ClassDef):
        return False
    return any(
        _is_workflow_attr(d.func if isinstance(d, ast.Call) else d, {"defn"})
        for d in node.decorator_list
    )


def _called_names(fn: ast.AST) -> set[str]:
    return {
        name
        for c in ast.walk(fn)
        if isinstance(c, ast.Call) and (name := _callee_name(c)) is not None
    }


def _start_sites(
    tree: ast.Module,
) -> list[tuple[ast.Call, list[ast.FunctionDef | ast.AsyncFunctionDef]]]:
    """Start calls outside ``@workflow.defn`` classes, with enclosing functions (inner first)."""
    out: list[tuple[ast.Call, list[ast.FunctionDef | ast.AsyncFunctionDef]]] = []

    def visit(node: ast.AST, fns: list[ast.FunctionDef | ast.AsyncFunctionDef]) -> None:
        if _is_workflow_defn_class(node):
            return  # child starts inside workflows stay on the parent queue (W-2)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in START_CALLS
        ):
            out.append((node, fns))
        inner = [node, *fns] if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) else fns
        for child in ast.iter_child_nodes(node):
            visit(child, inner)

    visit(tree, [])
    return out


def test_start_paths_resolve() -> None:
    trees = _parse_tree()

    resolvers = {
        fn.name
        for t in trees.values()
        for fn in ast.walk(t)
        if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef)
        and "resolve_harness_queue" in _called_names(fn)
    }

    census: Counter[str] = Counter()
    offenders: list[str] = []
    for rel, tree in trees.items():
        if rel in START_ALLOWLIST:
            continue
        for call, fns in _start_sites(tree):
            census[rel] += 1
            ok = any({"resolve_harness_queue", *resolvers} & _called_names(fn) for fn in fns)
            if not ok:
                where = fns[0].name if fns else "<module>"
                offenders.append(
                    f"{rel}:{call.lineno}: {where}() starts without resolve_harness_queue"
                )

    assert dict(census) == EXPECTED_START_SITES, (
        f"start-path census drifted: found {dict(sorted(census.items()))}, "
        f"expected {dict(sorted(EXPECTED_START_SITES.items()))}"
    )
    assert not offenders, f"{len(offenders)} unresolved start path(s):\n" + "\n".join(
        sorted(offenders)
    )


# ----------------------------------------------- chaos: the walk cannot be evaded


def _outside_workflows(tree: ast.AST) -> list[ast.AST]:
    """Every node outside ``@workflow.defn`` class bodies (same exclusion as ``_start_sites``)."""
    out: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        if _is_workflow_defn_class(node):
            return
        out.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return out


def _alias_sites(tree: ast.AST) -> list[str]:
    """Ways to reach a start scheduler other than calling ``<client>.<scheduler>(...)``."""
    nodes = _outside_workflows(tree)
    call_targets = {id(n.func) for n in nodes if isinstance(n, ast.Call)}
    found: list[str] = []
    for n in nodes:
        line = getattr(n, "lineno", 0)
        if isinstance(n, ast.Attribute) and n.attr in START_CALLS and id(n) not in call_targets:
            found.append(f"{line}: {n.attr} used other than as a call (alias or argument)")
        elif isinstance(n, ast.ImportFrom) and any(a.name in START_CALLS for a in n.names):
            found.append(f"{line}: scheduler imported by bare name")
        elif (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "getattr"
            and any(isinstance(a, ast.Constant) and a.value in START_CALLS for a in n.args[1:2])
        ):
            found.append(f"{line}: scheduler fetched with getattr")
    return found


def test_start_schedulers_are_never_aliased() -> None:
    offenders = [
        f"{rel}:{hit}" for rel, tree in _parse_tree().items() for hit in _alias_sites(tree)
    ]

    assert not offenders, "start scheduler aliased (dodges the walk):\n" + "\n".join(offenders)


@pytest.mark.parametrize(
    "src",
    [
        "start = client.start_workflow",
        "self._s = c.create_schedule",
        "run = c.update_schedule",
        "x: Any = c.start_workflow",
        "helper(c.start_workflow)",
        "from temporalio.client import start_workflow",
        "from x import create_schedule as cs",
        "f = getattr(c, 'start_workflow')",
        "class Plain:\n    s = c.start_workflow",
    ],
)
def test_alias_detector_catches_evasions(src: str) -> None:
    assert _alias_sites(ast.parse(src)), src


def test_alias_detector_ignores_plain_calls_and_workflow_bodies() -> None:
    plain = "async def f(c):\n    await c.start_workflow(W.run, i)\n    c.update_schedule(1)"
    in_workflow = "@workflow.defn\nclass W:\n    s = c.start_workflow"

    assert _alias_sites(ast.parse(plain)) == []
    assert _alias_sites(ast.parse(in_workflow)) == []


_EXCLUSION_SRC = """
class Plain:
    async def f(self, c):
        await c.start_workflow(1)

@workflow.defn
class W:
    async def run(self, c):
        await c.start_workflow(2)

@workflow.defn(name="x")
class Named:
    class Inner:
        async def g(self, c):
            await c.create_schedule(3)

@other.defn
class NotWorkflow:
    async def h(self, c):
        await c.update_schedule(4)

@dataclass
class Data:
    async def i(self, c):
        await c.start_workflow(5)

async def top(c):
    await c.start_workflow(6)

def outer():
    @workflow.defn
    class Local:
        async def run(self, c):
            await c.start_workflow(7)

c.start_workflow(8)
"""


def test_workflow_defn_exclusion_only_covers_workflow_class_bodies() -> None:
    sites = _start_sites(ast.parse(_EXCLUSION_SRC))

    def marker(call: ast.Call) -> int:
        arg = call.args[0]
        assert isinstance(arg, ast.Constant) and isinstance(arg.value, int)
        return arg.value

    kept = sorted(marker(c) for c, _ in sites)
    # 1 plain class, 4 foreign decorator, 5 dataclass, 6 function, 8 module level are kept;
    # 2, 3 (nested in a named workflow class) and 7 (workflow class inside a function) are not.
    assert kept == [1, 4, 5, 6, 8]
    module_level = [fns for c, fns in sites if marker(c) == 8]
    assert module_level == [[]]
