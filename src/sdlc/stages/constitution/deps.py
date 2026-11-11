"""Runtime deps for the constitution drafter agent. Serializable (crosses
the Temporal activity boundary via pydantic_data_converter), so it carries
CONFIG and COUNTERS — never a live handle or a filesystem path (the
research/deps.py house warning applies here too: anything the activity needs
from the run travels as data, or it does not travel).

Minimal in Task 5: enough for the agent's `deps_type` to exist. Task 6
extends it with the draft input and the activity that runs the agent.
"""

from __future__ import annotations

from pydantic import BaseModel

from .verify import FreezeMode


class ConstitutionDeps(BaseModel):
    run_id: str
    mode: FreezeMode
    max_principles: int = 12
    max_requests: int = 6
