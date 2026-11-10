"""The analyze stage is wired into the pipeline before the merge gate,
and both advisory checks are built from its output.

020 T026: the source read moved off FeatureWorkflow's _build_and_merge
(deleted) to the graph's nodes — postplan.py's analyze_node calls
analyze.step, and merge_node delegates to merge.step. The ordering row
became the shipped topology assertion: analysis precedes merge in the
graph's node order."""

import inspect
import pathlib

from sdlc.workflows.graph_catalog import SHIPPED

MERGE_SRC = pathlib.Path("src/sdlc/stages/merge/step.py").read_text(encoding="utf-8")
ANALYZE_NODE = inspect.getsource(
    __import__("sdlc.workflows.graph_nodes.postplan", fromlist=["analyze_node"]).analyze_node
)
POSTPLAN_SRC = pathlib.Path("src/sdlc/workflows/graph_nodes/postplan.py").read_text(
    encoding="utf-8"
)


def test_analyze_stage_calls_analyst_and_builds_both_checks():
    # Analyst invoked (analyze_node calls analyze.step with analyst_agent=t_analyst)
    assert "t_analyst," in POSTPLAN_SRC
    # Enforcement helper used (not an LLM verdict)
    assert "outcome.untraced" in POSTPLAN_SRC
    # Both advisory checks built in merge stage
    assert "build_check(" in MERGE_SRC and '"traceability"' in MERGE_SRC
    assert '"coverage"' in MERGE_SRC
    assert "measure_coverage" in MERGE_SRC


def test_analysis_precedes_merge_in_the_shipped_graph():
    """Topological, not list order (nodes are normalized into a total order
    on construction): a directed edge path analyze -> ... -> merge must
    exist, because the merge gate consumes the analysis."""
    graph = SHIPPED["default"]
    adj: dict[str, list[str]] = {}
    for e in graph.edges:
        adj.setdefault(e.source, []).append(e.target)
    seen, frontier = {"analyze"}, ["analyze"]
    while frontier:
        cur = frontier.pop()
        for nxt in adj.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    assert "merge" in seen, (
        "analysis must feed the merge gate's evidence — the shipped graph "
        "must reach merge from analyze"
    )
