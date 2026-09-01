"""S1 -- directory groupings at depth 1-3, classified by name.

BrownKit: domain-suggestive names contribute HIGH, generic and framework/layer
names LOW. The classification is carried as the RULE that fired, not as a
boolean, because E-48's "delivery channels and deployment boundaries are not
capabilities" guardrail needs the distinction (SourceCandidate's docstring).
"""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_PACKAGES,
    Confidence,
    MemberKind,
    ScanSignalId,
)
from sdlc.assessment.scan.signals import packages
from sdlc.measurement import CollectionState

TREE = [
    "README.md",
    "pyproject.toml",
    "src/payments/__init__.py",
    "src/payments/api.py",
    "src/payments/settle.py",
    "src/utils/strings.py",
    "src/controllers/health.py",
    "src/catcafe/booking.py",
]
LOC = {p: 20 for p in TREE if p.endswith(".py")}


def _by_id(out):
    return {c.local_id: c for c in out.sources}


def test_a_domain_term_contributes_high():
    out = packages.evaluate(TREE, LOC)
    pay = _by_id(out)["S1-src--payments"]
    assert pay.rule == "s1_domain_term"
    assert pay.confidence_contribution is Confidence.HIGH


def test_a_generic_name_contributes_low_under_its_own_rule():
    out = packages.evaluate(TREE, LOC)
    utils = _by_id(out)["S1-src--utils"]
    assert utils.rule == "s1_generic_name"
    assert utils.confidence_contribution is Confidence.LOW


def test_a_layer_name_is_a_different_rule_from_a_generic_one():
    """E-48's guardrail needs 'this is a technical layer' distinguishable
    from 'this is a vague bucket'."""
    out = packages.evaluate(TREE, LOC)
    assert _by_id(out)["S1-src--controllers"].rule == "s1_layer_name"
    assert _by_id(out)["S1-src--utils"].rule == "s1_generic_name"


def test_an_unlisted_specific_name_is_neither_vouched_for_nor_dismissed():
    """'catcafe' is not in DOMAIN_TERMS, but it is not generic either.
    Calling it a domain term would be a fabrication; calling it generic would
    lose a real candidate. MEDIUM under its own rule."""
    out = packages.evaluate(TREE, LOC)
    cc = _by_id(out)["S1-src--catcafe"]
    assert cc.rule == "s1_unclassified_name"
    assert cc.confidence_contribution is Confidence.MEDIUM


def test_the_local_id_carries_the_path_not_just_the_leaf():
    """Two directories can share a basename (api/models, web/models); the id
    must not collide, and the slug's '--' keeps signal_of's split on the
    FIRST hyphen unambiguous."""
    out = packages.evaluate(TREE, LOC)
    assert "S1-src--payments" in _by_id(out)
    assert "S1-src" in _by_id(out)


def test_members_are_the_package_and_the_files_directly_in_it():
    out = packages.evaluate(TREE, LOC)
    pay = _by_id(out)["S1-src--payments"]
    kinds = {m.kind for m in pay.members}
    assert MemberKind.PACKAGE_PATH in kinds
    assert MemberKind.FILE_PATH in kinds
    values = {m.value for m in pay.members}
    assert "src/payments" in values
    assert "src/payments/api.py" in values
    # NOT a file from another package
    assert "src/utils/strings.py" not in values


def test_a_parent_directory_carries_only_its_own_files():
    """src/ groups recursively for its metrics but must not carry every
    descendant as a member -- an 800-file candidate is not evidence."""
    out = packages.evaluate(TREE, LOC)
    src = _by_id(out)["S1-src"]  # noqa: E501 -- depth-1 slug has no separator
    files = [m for m in src.members if m.kind is MemberKind.FILE_PATH]
    assert files == []  # src/ directly contains no source
    assert src.metrics["file_count"].value == 6.0  # recursive


def test_loc_estimate_is_not_collected_when_a_blob_was_skipped():
    """FR-915: a partial sum must not pass as a complete one."""
    out = packages.evaluate(TREE, LOC, skipped=["src/payments/settle.py"])
    pay = _by_id(out)["S1-src--payments"]
    assert pay.metrics["loc_estimate"].state is CollectionState.NOT_COLLECTED
    assert "settle.py" in pay.metrics["loc_estimate"].reason
    # the count is still knowable
    assert pay.metrics["file_count"].state is CollectionState.MEASURED


def test_depth_is_bounded_at_three():
    tree = ["a/b/c/d/deep.py"]
    out = packages.evaluate(tree, {"a/b/c/d/deep.py": 5})
    depths = {len(c.local_id.removeprefix("S1-").split("--")) for c in out.sources}
    assert max(depths) <= 3


def test_a_repo_with_no_source_is_a_measured_zero_not_a_gap():
    """We looked and there is none -- scaffold.py's precedent for structure."""
    out = packages.evaluate(["README.md", "LICENSE"], {})
    assert out.row.collected.state is CollectionState.MEASURED
    assert out.row.collected.value == 0.0
    assert out.sources == []


def test_the_row_reports_its_category_and_nothing_else():
    out = packages.evaluate(TREE, LOC)
    assert set(out.row.categories) == {C_PACKAGES}
    assert out.row.signal is ScanSignalId.S1


def test_output_is_order_independent():
    """NFR-10: the same tree in a different order is the same artifact."""
    a = packages.evaluate(TREE, LOC)
    b = packages.evaluate(list(reversed(TREE)), LOC)
    assert a.model_dump_json() == b.model_dump_json()
