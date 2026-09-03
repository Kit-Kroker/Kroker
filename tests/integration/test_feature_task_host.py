# tests/integration/test_feature_task_host.py
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.task_host import TaskHost


def test_task_host_is_on_the_mro():
    assert issubclass(FeatureWorkflow, TaskHost)
    assert hasattr(FeatureWorkflow, "_dev_task")


def test_escalation_round_is_not_instance_state():
    # Rule 2. Wave mode runs _dev_task concurrently; an instance counter is
    # the same latent defect gates.py:84-88 documents for gate confidence.
    src = __import__("pathlib").Path("src/sdlc/workflows/feature.py").read_text(encoding="utf-8")
    assert "self._escalation_round" not in src

    host = __import__("pathlib").Path("src/sdlc/workflows/task_host.py").read_text(encoding="utf-8")
    assert "self._escalation_round" not in host
    assert "escalation_round" in host  # it survives as a local
