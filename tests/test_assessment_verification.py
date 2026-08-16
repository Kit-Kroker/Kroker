# tests/test_assessment_verification.py
"""RD6: one fail-closed grounding invariant, at two row types."""
from __future__ import annotations

from pydantic import BaseModel

from sdlc.assessment.scan.models import EvidenceRef
from sdlc.assessment.verification import (
    CITATION_GUARD_MAX_UNRESOLVED, cited_paths_of, guard_reason, verify_rows,
)


class Row(BaseModel):
    """A row type neither discover nor risk owns -- the protocol is
    structural, so a third consumer must work without touching the module."""
    rid: str
    evidence: tuple[EvidenceRef, ...] = ()
    quote: str = ""


def _v(rows, blobs):
    return verify_rows(rows, blobs, id_of=lambda r: r.rid)


def test_a_resolved_reference_survives():
    rows = [Row(rid="a", evidence=(EvidenceRef(path="x.py", lines="1"),))]
    out = _v(rows, {"x.py": "one line"})
    assert [r.rid for r in out.survivors] == ["a"]
    assert out.refusals == {}
    assert out.unresolved_references == 0


def test_an_unresolved_path_refuses_the_row():
    rows = [Row(rid="a", evidence=(EvidenceRef(path="ghost.py", lines=""),))]
    out = _v(rows, {"ghost.py": None})
    assert out.survivors == ()
    assert out.refusals["a"][0] == "dropped_ref_unresolved"
    assert out.unresolved_references == 1


def test_an_empty_file_is_resolved_not_missing():
    """None is unresolved; "" is a resolved EMPTY file. Truthiness would
    collapse them."""
    rows = [Row(rid="a", evidence=(EvidenceRef(path="empty.py", lines=""),))]
    assert [r.rid for r in _v(rows, {"empty.py": ""}).survivors] == ["a"]


def test_a_quote_that_does_not_byte_verify_refuses_the_row():
    rows = [Row(rid="a", evidence=(EvidenceRef(path="x.py", lines="1"),),
                quote="def nope(): pass")]
    out = _v(rows, {"x.py": "def yes(): pass"})
    assert out.refusals["a"][0] == "dropped_quote_unverified"


def test_the_rate_counts_references_not_rows():
    rows = [Row(rid="a", evidence=(EvidenceRef(path="g1.py", lines=""),
                                   EvidenceRef(path="g2.py", lines="")))]
    out = _v(rows, {"g1.py": None, "g2.py": None})
    assert (out.total_references, out.unresolved_references) == (2, 2)


def test_zero_references_is_a_zero_rate_never_a_division():
    assert _v([Row(rid="a")], {}).fabrication_rate == 0.0


def test_cited_paths_are_sorted_and_deduped():
    rows = [Row(rid="a", evidence=(EvidenceRef(path="b.py", lines=""),
                                   EvidenceRef(path="a.py", lines=""))),
            Row(rid="b", evidence=(EvidenceRef(path="a.py", lines=""),))]
    assert cited_paths_of(rows) == ("a.py", "b.py")


def test_the_guard_is_silent_at_or_below_the_threshold():
    rows = [Row(rid=str(i), evidence=(EvidenceRef(path="x.py", lines=""),))
            for i in range(10)]
    out = _v(rows, {"x.py": "body"})
    assert guard_reason(out) == ""
    assert CITATION_GUARD_MAX_UNRESOLVED == 0.10


def test_the_guard_names_its_two_terms_when_it_trips():
    rows = [Row(rid="a", evidence=(EvidenceRef(path="ghost.py", lines=""),))]
    reason = guard_reason(_v(rows, {"ghost.py": None}))
    assert "1/1" in reason and "0.10 guard" in reason


def test_verify_rows_is_order_independent():
    """NFR-10: the refusal set and the totals do not depend on input order."""
    import random
    rows = [Row(rid="a", evidence=(EvidenceRef(path="x.py", lines=""),)),
            Row(rid="b", evidence=(EvidenceRef(path="ghost.py", lines=""),)),
            Row(rid="c", evidence=(EvidenceRef(path="x.py", lines="1"),))]
    blobs = {"x.py": "body", "ghost.py": None}
    first = None
    for _ in range(5):
        random.shuffle(rows)
        out = _v(rows, blobs)
        got = (sorted(r.rid for r in out.survivors),
               sorted(out.refusals), out.total_references,
               out.unresolved_references)
        first = first if first is not None else got
        assert got == first
