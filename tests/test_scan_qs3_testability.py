"""QS3: what stops a test being written. BrownKit's three-valued severity
(blocks | impedes | smell) answers a different question than
critical/high/medium/low, which is why the record does not reuse
TriageFinding's scale."""
from __future__ import annotations

from sdlc.assessment.scan.models import testability_identity
from sdlc.assessment.scan.signals import testability
from sdlc.measurement import CollectionState

BLOBS = {
    "src/scheduler.py": (
        "import datetime\n"
        "import random\n"
        "\n"
        "CACHE = {}\n"
        "\n"
        "def next_run():\n"
        "    now = datetime.datetime.now()\n"
        "    jitter = random.random()\n"
        "    return now, jitter\n"),
    "src/client.py": (
        "import requests\n"
        "\n"
        "def fetch(url):\n"
        "    return requests.get(url).json()\n"),
    "tests/test_scheduler.py": (
        "import datetime\n"
        "def test_next_run():\n"
        "    assert datetime.datetime.now()\n"),
}


def test_a_clock_read_in_production_code_is_a_finding():
    out = testability.evaluate(BLOBS)
    patterns = {(f.path, f.pattern) for f in out.testability}
    assert ("src/scheduler.py", "static-clock-access") in patterns


def test_test_files_are_not_scanned():
    """A clock read inside a test is the test's own business."""
    out = testability.evaluate(BLOBS)
    assert all(not f.path.startswith("tests/") for f in out.testability)


def test_one_finding_per_path_and_pattern_with_the_count_in_the_detail():
    """P3-D10: a per-line finding turns a common habit into thousands of rows
    and makes every key move when a line moves."""
    blobs = {"src/a.py": "import datetime\n" + (
        "x = datetime.datetime.now()\n" * 5)}
    out = testability.evaluate(blobs)
    clock = [f for f in out.testability if f.pattern == "static-clock-access"]
    assert len(clock) == 1
    assert "5" in clock[0].detail
    assert clock[0].line == 2          # the FIRST occurrence


def test_identity_is_stable_when_a_line_moves():
    a = testability.evaluate({"src/a.py":
                              "import datetime\nx = datetime.datetime.now()\n"})
    b = testability.evaluate({"src/a.py":
                              "import datetime\n\n\nx = datetime.datetime.now()\n"})
    assert testability_identity(a.testability[0]) == \
        testability_identity(b.testability[0])


def test_every_finding_carries_a_seam_and_a_verbatim_quote():
    out = testability.evaluate(BLOBS)
    assert out.testability
    for finding in out.testability:
        assert finding.recommended_seam
        assert finding.evidence
        assert finding.severity in {"blocks", "impedes", "smell"}


def test_a_clean_module_is_a_measured_zero_not_a_gap():
    """We read every source blob in the tree; finding nothing is an answer."""
    out = testability.evaluate({"src/pure.py": "def add(a, b):\n    return a + b\n"})
    assert out.row.collected.state is CollectionState.MEASURED
    assert out.row.collected.value == 0.0
    assert out.testability == []


def test_output_is_byte_identical_across_input_orderings():
    reference = testability.evaluate(BLOBS).model_dump_json()
    reordered = dict(reversed(list(BLOBS.items())))
    assert testability.evaluate(reordered).model_dump_json() == reference
