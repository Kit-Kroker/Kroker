"""NFR-10's deterministic half: the same tree yields a byte-identical
ScanResult. Asserted on the SERIALIZED artifact, as E-47a asserts for
identity allocation -- an equal-comparing model with a differently-ordered
list is not the same artifact to a memo or a bundle."""
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
    "src/payments/api.py": ("from fastapi import APIRouter\n"
                            "router = APIRouter()\n"
                            "@router.post('/api/payments')\n"
                            "def create():\n    ...\n"),
    "src/orders/api.py": ("from fastapi import APIRouter\n"
                          "router = APIRouter()\n"
                          "@router.get('/api/orders')\n"
                          "def list_orders():\n    ...\n"),
    "src/utils/strings.py": "def slug(s):\n    return s\n",
    "src/payments/__init__.py": "",
}
LOC = {p: t.count("\n") + 1 for p, t in BLOBS.items()}
MEASURED = {ScanSignalId.S1: Measurement.measured(1.0),
            ScanSignalId.S3: Measurement.measured(1.0)}


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
