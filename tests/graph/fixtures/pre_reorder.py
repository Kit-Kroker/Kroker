"""The pre-FR-301 default graph, frozen verbatim (the in-flight-run pin).

FR-301 Task 3 reorders every shipped graph with plan stages to
``planner -> plan_check (ok) -> gate.plan``. Runs already in flight stay
pinned to the graph stored in their workflow INPUT, so this literal --
byte-identical to ``src/sdlc/workflows/graphs/default.graph.yaml`` at
commit 9b630b36 (the FR-301 base) -- is what they keep executing.
Characterization tests run it through the CURRENT registry and router to
pin that its behavior survives the reorder: the gate approves BEFORE the
validators run, and a validator failure rides the edgeless halt port to a
terminal ``failed`` outcome.
"""

from __future__ import annotations

from sdlc.graph import from_yaml
from sdlc.graph.model import PipelineGraph

PRE_REORDER_DEFAULT_YAML = """\
schema_version: 1
nodes:
- {id: intake, type: intake}
- {id: context, type: context}
- {id: clarify, type: clarify}
- {id: architect, type: architect}
- {id: architecture, type: gate.architecture}
- {id: planner, type: plan}
- {id: plan, type: gate.plan}
- {id: plan_check, type: plan_check}
- {id: code, type: code}
- {id: analyze, type: analyze}
- {id: merge, type: merge}
- {id: deploy, type: deploy}
edges:
- {source: intake, source_port: ok, target: clarify, target_port: trigger}
- {source: intake, source_port: brownfield, target: context, target_port: trigger}
- {source: context, source_port: map, target: clarify, target_port: codebase_map}
- {source: context, source_port: map, target: architect, target_port: codebase_map}
- {source: clarify, source_port: requirements, target: architect, target_port: requirements}
- {source: clarify, source_port: requirements, target: planner, target_port: requirements}
- {source: architect, source_port: spec, target: architecture, target_port: artifact}
- {source: architecture, source_port: revise, target: architect, target_port: guidance, max_traversals: 2}
- {source: architecture, source_port: approve, target: planner, target_port: spec}
- {source: architecture, source_port: approve, target: merge, target_port: spec}
- {source: planner, source_port: plan, target: plan, target_port: artifact}
- {source: plan, source_port: revise, target: planner, target_port: guidance, max_traversals: 2}
- {source: plan, source_port: approve, target: plan_check, target_port: plan}
- {source: plan_check, source_port: ok, target: code, target_port: plan}
- {source: plan_check, source_port: ok, target: analyze, target_port: plan}
- {source: plan_check, source_port: ok, target: merge, target_port: plan}
- {source: code, source_port: results, target: analyze, target_port: results}
- {source: code, source_port: results, target: merge, target_port: results}
- {source: analyze, source_port: analysis, target: merge, target_port: analysis}
- {source: merge, source_port: pr, target: deploy, target_port: pr}
"""


def pre_reorder_default() -> PipelineGraph:
    return from_yaml(PRE_REORDER_DEFAULT_YAML)
