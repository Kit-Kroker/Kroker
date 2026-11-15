"""Evidence schemas of the FR-205 library (`sdlc.validators.evidence`).

The pins here are almost entirely about SHAPE, not behavior: ADR-24 (docs/adr.md)
commits every output schema to listing evidence fields before status fields, and
the future verdict functions consume exactly these models -- so field order is a
contract, pinned via `model_fields`, not an implementation detail. The module
deliberately has no consumers yet (ADR-24 handoff); the only behavior to test is
construction, the defaults from the signatures, and purity (no temporalio, no I/O).
"""

from __future__ import annotations

import subprocess
import sys

from sdlc.validators import AssertionEvidence, Coverage, Finding


def test_assertionevidence_field_order_is_claim_evidence_source():
    assert tuple(AssertionEvidence.model_fields) == ("claim", "evidence", "source")


def test_finding_field_order_is_evidence_then_status():
    # ADR-24/AP-1.4: evidence first, status (detail/blocking) after.
    assert tuple(Finding.model_fields) == ("evidence", "detail", "blocking")


def test_coverage_field_order_is_total_covered_uncovered():
    assert tuple(Coverage.model_fields) == ("total", "covered", "uncovered")


def test_models_construct_with_signature_defaults():
    ev = AssertionEvidence(claim="plan covers FR-1", evidence="plan.md cites FR-1 at :12")
    assert ev.source == ""
    f = Finding(evidence=ev)
    assert f.evidence is ev
    assert f.detail == ""
    assert f.blocking is False
    cov = Coverage(total=3, covered=["FR-1"], uncovered=["FR-2", "FR-3"])
    assert cov.total == 3 and cov.covered == ["FR-1"] and cov.uncovered == ["FR-2", "FR-3"]


def test_models_construct_with_all_fields():
    ev = AssertionEvidence(claim="c", evidence="e", source="src/app.py:10")
    assert ev.source == "src/app.py:10"
    f = Finding(evidence=ev, detail="named gap", blocking=True)
    assert f.detail == "named gap" and f.blocking is True


def test_evidence_module_and_package_import_stay_temporalio_free():
    """Layering: evidence.py is pure Pydantic, and the package's eager re-export
    of it must not drag temporalio into `import sdlc.validators` (only touching
    ACTIVITIES may)."""
    cmd = [
        sys.executable,
        "-c",
        "import sys, sdlc.validators.evidence, sdlc.validators; "
        "assert 'temporalio' not in sys.modules, 'temporalio leaked'",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"stdout: {res.stdout}, stderr: {res.stderr}"
