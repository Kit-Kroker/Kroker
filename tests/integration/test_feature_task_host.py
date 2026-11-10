# tests/integration/test_feature_task_host.py
# 020 T026: re-pointed from FeatureWorkflow to GraphWorkflow; the historical rationale is kept.
from sdlc.workflows.graph import GraphWorkflow
from sdlc.workflows.task_host import TaskHost


def test_task_host_is_on_the_mro():
    assert issubclass(GraphWorkflow, TaskHost)
    assert hasattr(GraphWorkflow, "_dev_task")


def test_escalation_round_is_not_instance_state():
    # Rule 2. Wave mode runs _dev_task concurrently; an instance counter is
    # the same latent defect gates.py:84-88 documents for gate confidence.
    host = __import__("pathlib").Path("src/sdlc/workflows/task_host.py").read_text(encoding="utf-8")
    assert "self._escalation_round" not in host
    assert "escalation_round" in host  # it survives as a local
