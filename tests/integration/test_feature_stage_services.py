# 020 T026: re-pointed from FeatureWorkflow to GraphWorkflow; the historical rationale is kept.
from sdlc.core.context import StageContext
from sdlc.workflows.graph import GraphWorkflow


def test_ctx_is_built_in_init_and_satisfies_the_protocol():
    wf = GraphWorkflow()
    assert isinstance(wf._ctx, StageContext)


def test_ctx_cannot_reach_workflow_internals():
    wf = GraphWorkflow()
    for private in ("_pending", "_status", "_trace", "_question_answers", "_gate_decisions"):
        assert not hasattr(wf._ctx, private), private
