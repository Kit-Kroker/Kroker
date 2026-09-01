"""E-47b: known mutations against a synthetic tree, each with a labelled
expected outcome. Generates ground truth instead of hand-labelling it, which
is what E-47a's refactor corpus does for identity."""

from __future__ import annotations

from sdlc.assessment.discover.attribution import attribute
from sdlc.assessment.discover.models import FileBucket

BASE = {
    "src/payments/api.py": "from . import service\nimport requests\n",
    "src/payments/service.py": "from . import repo\n",
    "src/payments/repo.py": "x = 1\n",
    "src/shared/util.py": "y = 1\n",
    "setup.py": "setup()\n",
    "tests/test_api.py": "from src.payments.api import x\n",
}
MEMBERS = {"BC-001": ["src/payments/api.py", "src/payments/service.py"]}


def _bucket(report, path):
    return next(f.bucket for f in report.files if f.path == path)


def test_baseline_attributes_the_import_chain():
    report = attribute(BASE, [], MEMBERS, [])
    assert _bucket(report, "src/payments/repo.py") is FileBucket.ATTACHED
    assert _bucket(report, "setup.py") is FileBucket.INFRASTRUCTURE
    assert _bucket(report, "tests/test_api.py") is FileBucket.ATTACHED
    # src/shared/util.py is imported by nothing at all.
    assert _bucket(report, "src/shared/util.py") is FileBucket.DEAD


def test_mutation_deleting_the_only_import_makes_a_file_dead():
    tree = dict(BASE)
    tree["src/payments/service.py"] = "pass\n"  # no longer imports repo
    report = attribute(tree, [], MEMBERS, [])
    assert _bucket(report, "src/payments/repo.py") is FileBucket.DEAD


def test_mutation_moving_a_file_leaves_coverage_unchanged():
    before = attribute(BASE, [], MEMBERS, []).coverage.value
    tree = dict(BASE)
    tree["src/payments/storage.py"] = tree.pop("src/payments/repo.py")
    tree["src/payments/service.py"] = "from . import storage\n"
    after = attribute(tree, [], MEMBERS, []).coverage.value
    assert before == after


def test_known_false_positive_a_dynamic_reference_reads_as_dead():
    """D6 accepts that dynamic references are invisible to a regex table.
    Pinned as a test, not a docstring caveat: an increment that adds dynamic-
    form detection will fail here, which is exactly the notification it wants.
    """
    tree = dict(BASE)
    tree["src/payments/service.py"] = (
        "import importlib\nrepo = importlib.import_module('src.payments.repo')\n"
    )
    report = attribute(tree, [], MEMBERS, [])
    assert _bucket(report, "src/payments/repo.py") is FileBucket.DEAD


def test_mutation_claiming_an_orphan_raises_coverage():
    before = attribute(BASE, [], MEMBERS, []).coverage.value
    wider = dict(MEMBERS)
    wider["BC-002"] = ["src/shared/util.py"]
    after = attribute(BASE, [], wider, []).coverage.value
    assert after > before
    assert after == 1.0
