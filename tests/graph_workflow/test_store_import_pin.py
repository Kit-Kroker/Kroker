# tests/graph_workflow/test_store_import_pin.py
"""E-75 D1/D4: workflow code never reaches the store or the client helper,
and ACTIVATION is set in exactly one place."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "sdlc"


def test_workflows_never_import_the_store_or_start():
    pattern = re.compile(r"graph\.store|graph\.start|graph import (store|start)")
    offenders = [
        p.relative_to(SRC).as_posix()
        for p in (SRC / "workflows").rglob("*.py")
        if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_activation_is_set_only_in_the_dispatcher_task():
    hits = [
        (p.relative_to(SRC).as_posix(), line.strip())
        for p in SRC.rglob("*.py")
        for line in p.read_text(encoding="utf-8").splitlines()
        if "ACTIVATION.set(" in line
    ]
    assert hits == [
        (
            "workflows/graph_dispatch.py",
            "ACTIVATION.set(act.activation_id)  # the ONLY set site (E-75 D4; pinned)",
        )
    ]
