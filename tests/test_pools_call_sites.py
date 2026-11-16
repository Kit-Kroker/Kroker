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
