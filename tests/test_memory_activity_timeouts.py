"""The memory activity's two ceilings, pinned to each other.

A 2026-10-28 smoke run died four recalls in a row: real recall latency
(~42s end-to-end, ~30s per Hindsight LLM call) sat above BOTH the client
read timeout and the activity StartToClose (then 30s each). The invariant
that keeps a slow backend diagnosable: the client raises ReadTimeout
first, recall degrades to an empty snapshot (memory/activities.py), and
Temporal never kills the activity on a timeout that says nothing about
the backend. If either constant moves, move the other with it.
"""

from __future__ import annotations

from datetime import timedelta

from sdlc.memory.activities import HINDSIGHT_TIMEOUT_S
from sdlc.workflows.memory_host import MEM_ACT


def test_client_timeout_sits_inside_start_to_close():
    stc = MEM_ACT["start_to_close_timeout"]
    assert stc == timedelta(seconds=120)
    assert HINDSIGHT_TIMEOUT_S == 100.0
    assert timedelta(seconds=HINDSIGHT_TIMEOUT_S) < stc
