"""D3: identity is (signal, rule, path, key) and never `line`, which drifts
the moment a fix lands above the finding."""
from sdlc.triage.models import (
    FixClass, TriageFinding, dedupe_by_identity, evidence_key,
    finding_identity,
)


def _f(**kw):
    base = dict(signal="deps", rule="unpinned_dependency", severity="medium",
                detail="d", fix_class=FixClass.MECHANICAL)
    base.update(kw)
    return TriageFinding(**base)


def test_key_defaults_to_empty():
    assert _f().key == ""


def test_identity_excludes_line():
    a = _f(path="requirements.txt", line=3, key="flask")
    b = _f(path="requirements.txt", line=41, key="flask")
    assert finding_identity(a) == finding_identity(b)


def test_identity_separates_two_findings_of_one_rule_in_one_file():
    a = _f(path="requirements.txt", key="flask")
    b = _f(path="requirements.txt", key="requests")
    assert finding_identity(a) != finding_identity(b)


def test_identity_separates_rules_and_paths_and_signals():
    base = _f(path="requirements.txt", key="flask")
    assert finding_identity(base) != finding_identity(_f(
        path="pyproject.toml", key="flask"))
    assert finding_identity(base) != finding_identity(_f(
        path="requirements.txt", rule="unused_dependency", key="flask"))
    assert finding_identity(base) != finding_identity(_f(
        path="requirements.txt", signal="other", key="flask"))


def test_evidence_key_is_stable_short_and_hides_the_text():
    secret = "AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'"
    k = evidence_key(secret)
    assert k == evidence_key(secret)
    assert len(k) == 12
    assert "AKIA" not in k


def test_evidence_key_separates_different_text():
    assert evidence_key("a = 1") != evidence_key("b = 2")


def test_evidence_key_survives_undecodable_bytes():
    """Signals read blobs that are not guaranteed to be clean UTF-8."""
    assert len(evidence_key("caf\udce9 = 1")) == 12


def test_dedupe_keeps_the_first_of_each_identity():
    a = _f(path="s.py", key="k", line=1)
    b = _f(path="s.py", key="k", line=9)
    c = _f(path="s.py", key="other", line=4)
    out = dedupe_by_identity([a, b, c])
    assert [f.line for f in out] == [1, 4]


def test_dedupe_preserves_order_and_returns_a_new_list():
    src = [_f(path="a", key="1"), _f(path="b", key="2")]
    out = dedupe_by_identity(src)
    assert out == src and out is not src
