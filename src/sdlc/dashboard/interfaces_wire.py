# src/sdlc/dashboard/interfaces_wire.py
"""The interfaces read (018 T075; read-routes.md R-8, data-model 2.3).

Serves the harness containment matrix: one row per harness kind, the
declared containment layers, the strict-parity derivation against the
shipped policy, and the registry family on the dev harness's row.

Two rules shape the module:
- Nothing writes. ``apply_containment`` is never called here - the
  strict cell is derived statically from the policy's rule layers
  against each adapter's declared layers. The parity TEST (T074) is the
  only place the adapter path runs.
- Every read happens at request time (policy, registry), so tests can
  monkeypatch and the import stays inert.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from sdlc.harness.claude_code import ClaudeCodeHarness
from sdlc.harness.containment import ContainmentLayer, load_policy
from sdlc.harness.opencode import OpenCodeHarness

CellState = Literal["yes", "no", "partial", "not_measured", "planned"]


class MatrixCellWire(BaseModel):
    state: CellState
    text: str = ""


class MatrixColumnWire(BaseModel):
    key: str
    name: str
    ref: str


class MatrixRowWire(BaseModel):
    harness: str
    sub: str
    planned: bool
    cells: list[MatrixCellWire]


class AdapterFactWire(BaseModel):
    who: str
    severity: Literal["warn", "error"]
    text: str


class InterfaceMatrixWire(BaseModel):
    columns: list[MatrixColumnWire]
    rows: list[MatrixRowWire]
    facts: list[AdapterFactWire]


_COLUMNS = [
    MatrixColumnWire(key="layers", name="Layers", ref="harness declarations"),
    MatrixColumnWire(key="strict", name="Strict", ref="policy/containment.yaml"),
    MatrixColumnWire(key="family", name="Family", ref="agents/registry.yaml"),
    MatrixColumnWire(key="installed", name="Installed", ref="unmeasured"),
    MatrixColumnWire(key="checkpoint", name="Checkpoint", ref="unmeasured"),
    MatrixColumnWire(key="session", name="Session", ref="unmeasured"),
]

# The harness kinds with adapters that declare containment layers.
_DECLARED: dict[str, frozenset[ContainmentLayer]] = {
    "claude_code": ClaudeCodeHarness.containment,
    "opencode": OpenCodeHarness.containment,
}

# The kinds without an adapter: static layer copy (cursor has none;
# crew fences per role harness - the role's own adapter decides).
_NO_ADAPTER_LAYERS = {"cursor": "none", "crew": "per role harness"}

_SUB = {
    "claude_code": "claude -p",
    "opencode": "opencode run",
    "cursor": "cursor agent",
    "crew": "lead + critics",
    "pyai": "pydantic-ai agents",
}

_PLANNED = "pyai"

_LAYER_TEXT = {
    1: "native",
    2: "native + hook",
}


def _layers_text(declared: frozenset[ContainmentLayer]) -> str:
    return _LAYER_TEXT.get(len(declared), "none")


def _strict_cell(declared: frozenset[ContainmentLayer], policy: Any) -> MatrixCellWire:
    """Derive strict WITHOUT running an adapter.

    The parity contract (read-routes.md): a rule is unenforceable when
    its layer is not among the adapter's declared layers - exactly what
    the adapter's own ``rules_unenforceable`` computes on this policy.
    """
    unenforceable = [r.id for r in policy.rules if r.layer not in declared]
    if not unenforceable:
        return MatrixCellWire(state="yes", text="starts")
    state: CellState = "no" if len(unenforceable) == len(policy.rules) else "partial"
    return MatrixCellWire(state=state, text="refuses: " + ", ".join(unenforceable))


def _row(harness: str, policy: Any, dev_harness: str | None) -> MatrixRowWire:
    cells: list[MatrixCellWire] = []
    if harness == _PLANNED:
        cells = [MatrixCellWire(state="planned", text="") for _ in _COLUMNS]
        return MatrixRowWire(harness=harness, sub=_SUB[harness], planned=True, cells=cells)
    declared = _DECLARED.get(harness)
    if declared is None:
        layers = MatrixCellWire(state="partial", text=_NO_ADAPTER_LAYERS[harness])
        strict = MatrixCellWire(state="not_measured", text="")
    else:
        layers = MatrixCellWire(state="yes", text=_layers_text(declared))
        strict = _strict_cell(declared, policy)
    if harness == dev_harness:
        from sdlc.agents.loader import model_family
        from sdlc.agents.roles import REGISTRY

        model = REGISTRY["dev"].model or ""
        family = MatrixCellWire(
            state="yes" if model else "not_measured",
            text=model_family(model) if model else "",
        )
    else:
        family = MatrixCellWire(state="not_measured", text="")
    cells = [
        layers,
        strict,
        family,
        MatrixCellWire(state="not_measured", text=""),  # installed
        MatrixCellWire(state="not_measured", text=""),  # checkpoint
        MatrixCellWire(state="not_measured", text=""),  # session
    ]
    return MatrixRowWire(harness=harness, sub=_SUB[harness], planned=False, cells=cells)


def interfaces() -> InterfaceMatrixWire:
    """The matrix over the shipped policy and the live registry."""
    policy = load_policy()
    dev_harness: str | None
    try:
        from sdlc.agents.roles import REGISTRY

        dev_harness = REGISTRY["dev"].harness
    except Exception:  # registry unavailable: the family cell stays unmeasured
        dev_harness = None
    rows = [
        _row(harness, policy, dev_harness)
        for harness in ("claude_code", "opencode", "cursor", "crew", _PLANNED)
    ]
    facts: list[AdapterFactWire] = []
    opencode_unenforceable = [r.id for r in policy.rules if r.layer not in _DECLARED["opencode"]]
    if opencode_unenforceable:
        facts.append(
            AdapterFactWire(
                who="opencode",
                severity="warn",
                text="hook-layer rules land in rules_unenforceable: "
                + ", ".join(opencode_unenforceable),
            )
        )
    facts.append(
        AdapterFactWire(
            who="cursor", severity="error", text="no containment layers - nothing to enforce"
        )
    )
    return InterfaceMatrixWire(columns=_COLUMNS, rows=rows, facts=facts)
