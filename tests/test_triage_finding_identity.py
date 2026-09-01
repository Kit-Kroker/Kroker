"""D3: identity is (signal, rule, path, key) and never `line`, which drifts
the moment a fix lands above the finding."""

from sdlc.triage.models import (
    FixClass,
    TriageFinding,
    dedupe_by_identity,
    evidence_key,
    finding_identity,
)


def _f(**kw):
    base = dict(
        signal="deps",
        rule="unpinned_dependency",
        severity="medium",
        detail="d",
        fix_class=FixClass.MECHANICAL,
    )
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
    assert finding_identity(base) != finding_identity(_f(path="pyproject.toml", key="flask"))
    assert finding_identity(base) != finding_identity(
        _f(path="requirements.txt", rule="unused_dependency", key="flask")
    )
    assert finding_identity(base) != finding_identity(
        _f(path="requirements.txt", signal="other", key="flask")
    )


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


import pytest

from sdlc.measurement import Measurement
from sdlc.triage.models import SignalResult
from sdlc.triage.signals import dependencies, misconfig, outliers, secrets


def test_signal_result_rejects_duplicate_identities():
    """D3: the silent-collapse hazard is caught in the signal that caused it,
    not inherited by the delta."""
    dup = [_f(path="requirements.txt", key=""), _f(path="requirements.txt", key="")]
    with pytest.raises(ValueError, match="duplicate finding identity"):
        SignalResult(signal="deps", version=1, collected=Measurement.measured(2.0), findings=dup)


def test_signal_result_accepts_distinct_identities():
    ok = [_f(path="requirements.txt", key="flask"), _f(path="requirements.txt", key="requests")]
    r = SignalResult(signal="deps", version=1, collected=Measurement.measured(2.0), findings=ok)
    assert len(r.findings) == 2


def test_secrets_separates_two_credentials_in_one_file():
    text = "AWS_A = 'AKIAIOSFODNN7EXAMPLE'\nAWS_B = 'AKIAJJJJJJJJJJJJJJJJ'\n"
    out = secrets.scan_text("app.py", text)
    aws = [f for f in out if f.rule == "aws_access_key_id"]
    assert len(aws) == 2
    assert len({finding_identity(f) for f in aws}) == 2


def test_secrets_collapses_the_same_credential_twice_in_one_file():
    line = "AWS_A = 'AKIAIOSFODNN7EXAMPLE'\n"
    out = secrets.scan_text("app.py", line + line)
    aws = [f for f in out if f.rule == "aws_access_key_id"]
    assert len(aws) == 1
    assert aws[0].line == 1  # the first occurrence is kept


def test_misconfig_separates_two_distinct_rule_hits_in_one_file():
    blobs = {"settings.py": "DEBUG = True\napp.run(debug=True)\n"}
    out = misconfig.evaluate(blobs)
    debug = [f for f in out.findings if f.rule == "debug_enabled"]
    assert len(debug) == 2
    assert len({finding_identity(f) for f in debug}) == 2


def test_dependencies_keys_by_package_name():
    from sdlc.triage.advisories import AdvisoryResult
    from sdlc.triage.signals.dependencies import Declared

    declared = [
        Declared(name="flask", constraint=">=2", manifest="req.txt", line=1, raw="flask>=2"),
        Declared(name="requests", constraint=">=1", manifest="req.txt", line=2, raw="requests>=1"),
    ]
    out = dependencies.evaluate(
        declared,
        lockfile_present=False,
        imported={"flask", "requests"},
        advisories=AdvisoryResult(advisories=[], collected=Measurement.measured(0.0)),
    )
    unpinned = [f for f in out.findings if f.rule == "unpinned_dependency"]
    assert {f.key for f in unpinned} == {"flask", "requests"}


@pytest.mark.parametrize(
    "mod,expected", [(secrets, 3), (misconfig, 2), (dependencies, 2), (outliers, 2)]
)
def test_version_bumped(mod, expected):
    """The SIGNALS registry contract: changing what a signal emits bumps its
    version, so E-46's memo key invalidates exactly that signal."""
    assert mod.VERSION == expected
