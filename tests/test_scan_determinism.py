"""NFR-10's deterministic half at the PURE-signal layer: the same tree yields
byte-identical SignalOutput / MergeOutput artifacts across input orderings.

These tests cover the capability CHAIN (S1 -> S3 -> S5) -- the part a memo
caches and the part most exposed to discovery order. They do NOT construct a
ScanResult; the workflow-level assembly (row order, the sources/candidates
sorts in _scan) is deterministic because _scan sorts every list before it
builds the artifact, and is exercised end-to-end by the temporal e2e
(test_assessment_workflow_e2e.test_scan_phase_flips_terminal_status_to_partial).
Asserting the serialized SignalOutput/MergeOutput is the same standard
E-47a applies to identity allocation: an equal-comparing model with a
differently-ordered list is not the same artifact to a memo or a bundle."""

from __future__ import annotations

import random

from sdlc.assessment.scan.merge import merge
from sdlc.assessment.scan.models import ScanSignalId
from sdlc.assessment.scan.signals import entrypoints, packages
from sdlc.measurement import Measurement

TREE = [
    "pyproject.toml",
    "src/payments/__init__.py",
    "src/payments/api.py",
    "src/orders/api.py",
    "src/utils/strings.py",
]
BLOBS = {
    "src/payments/api.py": (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/api/payments')\n"
        "def create():\n    ...\n"
    ),
    "src/orders/api.py": (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/api/orders')\n"
        "def list_orders():\n    ...\n"
    ),
    "src/utils/strings.py": "def slug(s):\n    return s\n",
    "src/payments/__init__.py": "",
}
LOC = {p: t.count("\n") + 1 for p, t in BLOBS.items()}
MEASURED = {ScanSignalId.S1: Measurement.measured(1.0), ScanSignalId.S3: Measurement.measured(1.0)}


def test_s1_is_byte_identical_across_input_orderings():
    reference = packages.evaluate(TREE, LOC).model_dump_json()
    for seed in range(5):
        shuffled = list(TREE)
        random.Random(seed).shuffle(shuffled)
        assert packages.evaluate(shuffled, LOC).model_dump_json() == reference


def test_s3_is_byte_identical_across_input_orderings():
    reference = entrypoints.evaluate(BLOBS).model_dump_json()
    for seed in range(5):
        items = list(BLOBS.items())
        random.Random(seed).shuffle(items)
        assert entrypoints.evaluate(dict(items)).model_dump_json() == reference


def test_the_whole_capability_chain_is_byte_identical():
    """S1 -> S3 -> S5 end to end, which is what the memo caches and what
    NFR-10 will be measured against."""

    def run(order_seed: int) -> str:
        paths = list(TREE)
        items = list(BLOBS.items())
        random.Random(order_seed).shuffle(paths)
        random.Random(order_seed).shuffle(items)
        s1 = packages.evaluate(paths, LOC)
        s3 = entrypoints.evaluate(dict(items))
        return merge(s1.sources + s3.sources, MEASURED).model_dump_json()

    assert run(1) == run(2) == run(3)


def test_merging_the_same_sources_twice_yields_one_artifact():
    s1 = packages.evaluate(TREE, LOC)
    s3 = entrypoints.evaluate(BLOBS)
    a = merge(s1.sources + s3.sources, MEASURED)
    b = merge(s3.sources + s1.sources, MEASURED)
    assert a.model_dump_json() == b.model_dump_json()


def test_every_pure_signal_module_is_order_independent():
    """NFR-10 over the whole set, not only the capability chain: each signal
    is a pure function of its inputs, so shuffling those inputs must not
    change a byte of the artifact."""
    import random

    from sdlc.assessment.scan.models import ScanUpstream
    from sdlc.assessment.scan.signals import (
        ci,
        config_infra,
        coverage,
        frontend,
        schema,
        security_static,
        sensitivity,
        testability,
        tests_inventory,
    )

    tree = {
        "package.json": '{"dependencies": {"next": "14.0.0"}}',
        "app/orders/page.tsx": "export default function P() {}\n",
        "migrations/0001.sql": "CREATE TABLE orders (id SERIAL, email TEXT);\n",
        "src/service.py": "import datetime\nx = datetime.datetime.now()\n",
        "tests/test_service.py": "import pytest\ndef test_x(): ...\n",
        ".env.production": "DEBUG=true\n",
        ".env.staging": "DEBUG=false\nSSL=true\n",
        ".github/workflows/ci.yml": "jobs:\n  test:\n    steps:\n      - run: pytest\n",
    }
    paths = sorted(tree)
    up = ScanUpstream(
        collected={
            s: Measurement.measured(1.0)
            for s in (ScanSignalId.S2, ScanSignalId.S3, ScanSignalId.QS1)
        }
    )

    cases = [
        ("S2", lambda t, p: schema.evaluate(t)),
        ("S4", lambda t, p: frontend.evaluate(t)),
        ("SS1", lambda t, p: security_static.evaluate(t, up)),
        ("SS3", lambda t, p: config_infra.evaluate(t)),
        ("SS4", lambda t, p: sensitivity.evaluate(t, up)),
        ("QS1", lambda t, p: tests_inventory.evaluate(p, t)),
        ("QS2", lambda t, p: coverage.evaluate(p, {}, up)),
        ("QS3", lambda t, p: testability.evaluate(t)),
        ("QS4", lambda t, p: ci.evaluate(p, t)),
    ]
    for name, run in cases:
        reference = run(tree, paths).model_dump_json()
        for seed in range(3):
            items = list(tree.items())
            shuffled_paths = list(paths)
            random.Random(seed).shuffle(items)
            random.Random(seed).shuffle(shuffled_paths)
            assert run(dict(items), shuffled_paths).model_dump_json() == reference, name
