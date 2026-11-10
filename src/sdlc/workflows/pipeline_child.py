"""Start one pipeline child from a parent workflow (E-74 spec §8.2, D13).

The patch id is PER CHILD: workflow.patched memoises per id per execution
(temporalio/worker/_workflow_instance.py:1362). 020 (R-1): the patch is
deprecated — workflow.deprecate_patch replaces the patched() branch test and
every child starts GraphWorkflow unconditionally. A pre-cutover history still
replays: a child recorded as FeatureWorkflow keeps its own branch, and a
stripped marker no longer issues a command the history lacks (the
replay-safe restart, pinned in tests/replay/test_benchmark_replay.py).
Removing the deprecated marker entirely is a standing item (020 bookkeeping).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..agents import (
        loader as _loader,  # noqa: F401 -- validate()'s lazy import stays passthrough
    )
    from ..agents.roles import REGISTRY
    from ..core.models import IdeaBrief, PipelineConfig
    from .graph import GraphWorkflow
    from .graph_catalog import build_run_input
    from .graph_nodes import HANDLERS
    from .models import SeededWork


async def execute_pipeline_child(
    *,
    child_id: str,
    idea: IdeaBrief,
    cfg: PipelineConfig,
    seeded: SeededWork | None,
    task_queue: str,
    on_graph: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    """`on_graph` (E-77 R-9): awaited with the child's pinned graph
    content_sha once the run input is built, BEFORE the child starts — only
    on the graph branch. The benchmark parent keeps the cell's sha from it."""
    workflow.deprecate_patch(f"e74-graph-child:{child_id}")
    run_input = build_run_input(
        idea, cfg, seeded, registry_roles=REGISTRY, handler_types=HANDLERS
    )  # GraphStartError propagates into the parent's existing failure branch
    if on_graph is not None:
        await on_graph(run_input.graph.content_sha())
    return await workflow.execute_child_workflow(
        GraphWorkflow.run, run_input, id=child_id, task_queue=task_queue
    )
