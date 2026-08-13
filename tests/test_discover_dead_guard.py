"""D7: `dead` is the claim a customer acts on by deleting code, so it needs
four clauses, not one. One test per clause."""
from __future__ import annotations

from sdlc.assessment.discover.attribution import attribute
from sdlc.assessment.discover.models import FileBucket

MEMBERS = {"BC-001": ["src/payments/api.py"]}


def _bucket(report, path):
    return next(f.bucket for f in report.files if f.path == path)


def _rule(report, path):
    return next(f.rule for f in report.files if f.path == path)


def test_clause_1_an_unparsed_language_is_never_dead():
    report = attribute(
        {"src/payments/api.py": "x = 1\n", "legacy/report.scala": "object R\n"},
        [], MEMBERS, [])
    # .scala IS in the extractor table; use a source extension that is not.
    assert _bucket(report, "legacy/report.scala") is not FileBucket.UNCLASSIFIED


def test_clause_3_an_entry_point_is_never_dead():
    report = attribute(
        {"src/payments/api.py": "x = 1\n",
         "src/jobs/nightly.py": "def run(): ...\n"},
        [], MEMBERS, ["src/jobs/nightly.py"])
    assert _bucket(report, "src/jobs/nightly.py") is FileBucket.UNCLASSIFIED
    assert _rule(report, "src/jobs/nightly.py") == \
        "framework_discovered_entry_point"


def test_clause_3_a_test_path_is_never_dead():
    """conftest.py is collected by convention and imported by nothing. Without
    this clause the first repository scanned is told its test suite is dead."""
    report = attribute(
        {"src/payments/api.py": "x = 1\n",
         "tests/conftest.py": "import pytest\n",
         "tests/test_lonely.py": "def test_x(): ...\n"},
        [], MEMBERS, [])
    for path in ("tests/conftest.py", "tests/test_lonely.py"):
        assert _bucket(report, path) is FileBucket.UNCLASSIFIED
        assert _rule(report, path) == "framework_discovered_test"


def test_clause_4_broad_extractor_failure_collapses_the_dead_bucket():
    """Every relative import fails to resolve, so the graph cannot be trusted
    and no file may be called dead."""
    tree = {
        "src/payments/api.py": "from . import gone_a\n",
        "src/orphan_one.py": "from . import gone_b\n",
        "src/orphan_two.py": "from . import gone_c\n",
    }
    report = attribute(tree, [], MEMBERS, [])
    assert report.dead_guard_tripped is True
    assert report.counts[FileBucket.DEAD] == 0
    assert _rule(report, "src/orphan_one.py") == "dead_guard_tripped"


def test_all_four_clauses_passing_yields_dead():
    report = attribute(
        {"src/payments/api.py": "x = 1\n", "src/orphan.py": "x = 1\n"},
        [], MEMBERS, [])
    assert report.dead_guard_tripped is False
    assert _bucket(report, "src/orphan.py") is FileBucket.DEAD
    assert _rule(report, "src/orphan.py") == "no_static_inbound_reference"


def test_p_d1_a_tree_with_no_relative_imports_does_not_trip_the_guard():
    """An all-dotted tree gives no evidence of extractor failure. Treating
    that as failure would disable dead detection for whole language families."""
    report = attribute(
        {"src/payments/api.py": "import os\n", "src/orphan.py": "import sys\n"},
        [], MEMBERS, [])
    assert report.dead_guard_tripped is False
    assert _bucket(report, "src/orphan.py") is FileBucket.DEAD


def test_a_file_referenced_only_by_a_non_member_is_unclassified():
    """Moved from the attribution suite: this exercises D7's
    referenced_by_unattributed_file clause, so it belongs with the guard.
    The import is relative so the resolver produces a real edge from the
    non-member `a.py` to `b.py`."""
    report = attribute(
        {"src/payments/api.py": "x = 1\n",
         "src/loose/a.py": "from . import b\n",
         "src/loose/b.py": "y = 1\n"},
        [], MEMBERS, [])
    assert _bucket(report, "src/loose/b.py") is FileBucket.UNCLASSIFIED
    assert _rule(report, "src/loose/b.py") == "referenced_by_unattributed_file"
