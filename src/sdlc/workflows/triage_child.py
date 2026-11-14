"""The shared triage-child helper (023a T008, plan E1).

`triage_gates` was lifted UNCHANGED from `workflows/tidyup.py` (its
birthplace, E-42) so `workflows/maintenance.py` can hand a TriageWorkflow
child the same not-gating settings without importing across workflows.
`tidyup` imports it from here, so every existing
`from sdlc.workflows.tidyup import triage_gates` keeps working and its
replay coverage is untouched (import move only, no behaviour change).
"""

from __future__ import annotations

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..core.models import GatePolicy, GateSettings


def triage_gates(inp_gates: GateSettings, gating: bool) -> GateSettings:
    """The gates handed to a TriageWorkflow child.

    The BEFORE triage gates admission, so the operator's settings apply. The
    AFTER triage only measures the verification tree to classify the delta;
    it must not open a readiness gate and park 48h on a non-READY verdict
    (which --no-build-probe makes INDETERMINATE by construction). OFF resolves
    automatically; the verdict is still computed and recorded as
    readiness_after, and the override does not feed compute_delta.
    """
    if gating:
        return inp_gates
    return GateSettings(default_gate_policy=GatePolicy.OFF)
