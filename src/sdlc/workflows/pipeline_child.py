"""Start one pipeline child from a parent workflow (E-74 spec §8.2, D13).

The patch id is PER CHILD: workflow.patched memoises per id per execution
(temporalio/worker/_workflow_instance.py:1362), so a single id would let an
in-flight parent keep starting FeatureWorkflow children after cutover. A child
already in history replays as FeatureWorkflow; every child not yet started
goes to GraphWorkflow. The else-branch is deleted with FeatureWorkflow (§8.5).
"""

from __future__ import annotations

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..agents import (
        loader as _loader,  # noqa: F401 -- validate()'s lazy import stays passthrough
    )
    from ..agents.roles import REGISTRY
    from ..core.models import IdeaBrief, PipelineConfig
    from .feature import FeatureWorkflow
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
) -> str:
    if workflow.patched(f"e74-graph-child:{child_id}"):
        run_input = build_run_input(
            idea, cfg, seeded, registry_roles=REGISTRY, handler_types=HANDLERS
        )  # GraphStartError propagates into the parent's existing failure branch
        return await workflow.execute_child_workflow(
            GraphWorkflow.run, run_input, id=child_id, task_queue=task_queue
        )
    return await workflow.execute_child_workflow(
        FeatureWorkflow.run, args=[idea, cfg, seeded], id=child_id, task_queue=task_queue
    )
