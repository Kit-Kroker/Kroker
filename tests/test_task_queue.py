"""T003 (plan T010): TASK_QUEUE lives in a framework-free module.

RED until src/sdlc/task_queue.py exists and worker.py re-exports it.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_task_queue_value_is_ai_sdlc():
    from sdlc.task_queue import TASK_QUEUE

    assert TASK_QUEUE == "ai-sdlc"


def test_worker_reexports_the_same_task_queue_name():
    from sdlc import task_queue, worker

    assert worker.TASK_QUEUE is task_queue.TASK_QUEUE


def test_importing_task_queue_loads_no_temporal_or_agents():
    probe = (
        "import sys, sdlc.task_queue; "
        "bad = [m for m in ('temporalio', 'sdlc.agents') if m in sys.modules]; "
        "print(','.join(bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == ""
