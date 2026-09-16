"""Chaos + edge-case characterization for E-74 Task 11 boot-safe payload resolution.

RED until ``_resolve_payload`` widens its ``except`` clause: today it catches
only ``(ImportError, AttributeError)``, so a payload module that raises
ANYTHING else at import time -- RuntimeError, TypeError, ValueError, a custom
exception -- or whose attribute lookup explodes (module ``__getattr__``
raising, per PEP 562) crashes the call outright. The same crash escapes
``check_node_types``, which worker boot will run (E-74: boot must report,
never crash). Post-landing, every such exception becomes the problem string

    payload '<name>' does not resolve (<target>): <ExcType>: <message>

and the boot check collects it instead of dying.

The crashing modules are generated into ``tmp_path`` (a unique module name
per test) and put on ``sys.path`` via ``monkeypatch`` -- nothing under
``tests/graph/fixtures/`` is touched or depended on. A module that fails to
import is never cached in ``sys.modules``, so the parametrized imports
re-raise cleanly every run.
"""

from __future__ import annotations

import pytest

from sdlc.graph import node_types
from sdlc.graph.node_types import NodePort, NodeTypeSpec, check_node_types

_CUSTOM_PRELUDE = "class VendorSDKError(Exception):\n    pass\n\n\n"


def _crash_module(tmp_path, monkeypatch, name, source):
    (tmp_path / f"{name}.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))


def _register_boom(monkeypatch, module_name):
    monkeypatch.setattr(
        node_types,
        "PAYLOAD_TYPES",
        {**node_types.PAYLOAD_TYPES, "ChaosBoom": f"{module_name}:ChaosBoom"},
    )


def _boom_spec(payload: str, type_: str = "chaos.boom") -> NodeTypeSpec:
    return NodeTypeSpec(
        type=type_,
        kind="stage",
        role=None,
        canonical_stage=None,
        ports=(NodePort(name="out", direction="out", payload=payload),),
    )


# ---- non-ImportError import crashes become problem strings -------------------


@pytest.mark.parametrize(
    ("module_name", "source", "exc_name", "message"),
    [
        (
            "chaos_boom_runtime",
            "raise RuntimeError('import-time crash')\n",
            "RuntimeError",
            "import-time crash",
        ),
        (
            "chaos_boom_type",
            "raise TypeError('payload class is the wrong shape')\n",
            "TypeError",
            "payload class is the wrong shape",
        ),
        (
            "chaos_boom_value",
            "raise ValueError('unparseable payload constant')\n",
            "ValueError",
            "unparseable payload constant",
        ),
        (
            "chaos_boom_custom",
            _CUSTOM_PRELUDE + "raise VendorSDKError('vendor sdk exploded at import')\n",
            "VendorSDKError",
            "vendor sdk exploded at import",
        ),
    ],
    ids=["runtime", "type", "value", "custom"],
)
def test_resolve_payload_reports_non_importerror_import_crashes(
    tmp_path, monkeypatch, module_name, source, exc_name, message
):
    _crash_module(tmp_path, monkeypatch, module_name, source)
    _register_boom(monkeypatch, module_name)

    problem = node_types._resolve_payload("ChaosBoom")

    assert problem == (
        f"payload 'ChaosBoom' does not resolve ({module_name}:ChaosBoom): {exc_name}: {message}"
    )


def test_resolve_payload_reports_a_descriptor_raise_on_getattr(tmp_path, monkeypatch):
    # the module imports FINE; only the attribute lookup explodes -- the
    # except clause must cover the getattr half, not just import_module
    module_name = "chaos_boom_getattr"
    _crash_module(
        tmp_path,
        monkeypatch,
        module_name,
        "def __getattr__(name):\n    raise ValueError(f'descriptor exploded for {name}')\n",
    )
    _register_boom(monkeypatch, module_name)

    problem = node_types._resolve_payload("ChaosBoom")

    assert problem == (
        f"payload 'ChaosBoom' does not resolve ({module_name}:ChaosBoom): "
        "ValueError: descriptor exploded for ChaosBoom"
    )


# ---- check_node_types is boot-safe: report, never crash ----------------------


def test_check_node_types_reports_an_import_crash_instead_of_dying(tmp_path, monkeypatch):
    # worker boot runs this: a crashing payload module must surface as a
    # problem string carrying the port prefix, not an exception
    _crash_module(
        tmp_path, monkeypatch, "chaos_boot_boom", "raise RuntimeError('import-time crash')\n"
    )
    _register_boom(monkeypatch, "chaos_boot_boom")

    problems = check_node_types({"chaos.boom": _boom_spec("ChaosBoom")})

    assert problems == [
        "chaos.boom.out: payload 'ChaosBoom' does not resolve (chaos_boot_boom:ChaosBoom): "
        "RuntimeError: import-time crash",
    ]


def test_check_node_types_keeps_collecting_problems_around_a_crash(tmp_path, monkeypatch):
    # one crashing payload must not hide the other problems: the walk
    # continues and the sorted list carries both rows
    _crash_module(
        tmp_path, monkeypatch, "chaos_collect_boom", "raise RuntimeError('import-time crash')\n"
    )
    _register_boom(monkeypatch, "chaos_collect_boom")

    problems = check_node_types(
        {
            "chaos.boom": _boom_spec("ChaosBoom"),
            "chaos.unknown": _boom_spec("NeverHeard", type_="chaos.unknown"),
        }
    )

    assert problems == [
        "chaos.boom.out: payload 'ChaosBoom' does not resolve (chaos_collect_boom:ChaosBoom): "
        "RuntimeError: import-time crash",
        "chaos.unknown.out: payload 'NeverHeard' is not in PAYLOAD_TYPES",
    ]
