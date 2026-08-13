"""E-47b D3/D4/D5: the denominator, the numerator, and bucket precedence."""
from __future__ import annotations

import random

from sdlc.assessment.discover.attribution import attribute
from sdlc.assessment.discover.models import FileBucket
from sdlc.measurement import CollectionState

MEMBERS = {"BC-001": ["src/payments/api.py"]}


def _bucket(report, path):
    return next(f.bucket for f in report.files if f.path == path)


def test_a_member_file_is_a_member():
    report = attribute({"src/payments/api.py": "x = 1\n"}, [], MEMBERS, [])
    assert _bucket(report, "src/payments/api.py") is FileBucket.MEMBER
    assert report.files[0].capabilities == ("BC-001",)


def test_non_source_extensions_are_outside_the_denominator():
    report = attribute(
        {"src/payments/api.py": "x = 1\n", "README.md": "# hi\n",
         "Dockerfile": "FROM python\n"},
        [], MEMBERS, [])
    assert [f.path for f in report.files] == ["src/payments/api.py"]
    assert report.coverage.value == 1.0


def test_build_tooling_in_the_denominator_is_infrastructure():
    report = attribute(
        {"src/payments/api.py": "x = 1\n", "setup.py": "setup()\n",
         "webpack.config.js": "module.exports = {}\n"},
        [], MEMBERS, [])
    assert _bucket(report, "setup.py") is FileBucket.INFRASTRUCTURE
    assert _bucket(report, "webpack.config.js") is FileBucket.INFRASTRUCTURE
    assert report.coverage.value == 1.0     # D4: all accounted for


def test_member_beats_infrastructure():
    """Precedence rule 1 beats rule 2 -- a capability that claims setup.py
    owns it."""
    report = attribute({"setup.py": "setup()\n"},
                       [], {"BC-001": ["setup.py"]}, [])
    assert _bucket(report, "setup.py") is FileBucket.MEMBER


def test_a_file_a_member_imports_is_attached():
    report = attribute(
        {"src/payments/api.py": "from . import helper\n",
         "src/payments/helper.py": "x = 1\n"},
        [], MEMBERS, [])
    attached = next(f for f in report.files
                    if f.path == "src/payments/helper.py")
    assert attached.bucket is FileBucket.ATTACHED
    assert attached.capabilities == ("BC-001",)


def test_a_test_importing_a_member_is_attached():
    report = attribute(
        {"src/payments/api.py": "x = 1\n",
         "tests/test_api.py": "from src.payments.api import x\n"},
        [], MEMBERS, [])
    assert _bucket(report, "tests/test_api.py") is FileBucket.ATTACHED


def test_infrastructure_beats_attached():
    report = attribute(
        {"src/payments/api.py": "from . import helper\n",
         "src/payments/helper.py": "x = 1\n",
         "setup.py": "from src.payments import api\n"},
        [], MEMBERS, [])
    assert _bucket(report, "setup.py") is FileBucket.INFRASTRUCTURE


def test_a_skipped_blob_is_unclassified_and_stays_in_the_denominator():
    report = attribute({"src/payments/api.py": "x = 1\n"},
                       ["src/broken.py"], MEMBERS, [])
    assert _bucket(report, "src/broken.py") is FileBucket.UNCLASSIFIED
    assert report.skipped == ("src/broken.py",)
    assert report.coverage.value == 0.5


def test_the_ratio_counts_accounted_for_over_the_whole_denominator():
    report = attribute(
        {"src/payments/api.py": "x = 1\n",     # member
         "setup.py": "setup()\n",              # infrastructure
         "src/orphan_a.py": "x = 1\n",         # dead
         "src/orphan_b.py": "x = 1\n"},        # dead
        [], MEMBERS, [])
    assert report.coverage.value == 0.5
    assert report.counts[FileBucket.MEMBER] == 1
    assert report.counts[FileBucket.INFRASTRUCTURE] == 1
    assert report.counts[FileBucket.DEAD] == 2
    assert report.meets_floor is False


def test_an_all_infrastructure_tree_is_fully_accounted_for():
    report = attribute({"setup.py": "setup()\n", "noxfile.py": "x = 1\n"},
                       [], {"BC-001": ["setup.py"]}, [])
    assert report.coverage.value == 1.0
    assert report.meets_floor is True


def test_attribution_is_byte_identical_across_input_orderings():
    """P-D2: NFR-10's standard, asserted where the module lives."""
    tree = {
        "src/payments/api.py": "from . import helper\n",
        "src/payments/helper.py": "x = 1\n",
        "setup.py": "setup()\n",
        "src/orphan.py": "x = 1\n",
        "tests/test_api.py": "from src.payments.api import x\n",
    }
    reference = attribute(tree, [], MEMBERS, []).model_dump_json()
    for seed in range(3):
        items = list(tree.items())
        random.Random(seed).shuffle(items)
        assert attribute(dict(items), [], MEMBERS,
                         []).model_dump_json() == reference
