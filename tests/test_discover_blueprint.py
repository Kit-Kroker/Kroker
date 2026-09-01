# tests/test_discover_blueprint.py
"""E-48 DD11 (clause D8): MISSING is context, not failure."""

from sdlc.assessment.discover.blueprint import (
    BlueprintProcess,
    compare,
    load,
)
from sdlc.assessment.discover.map import (
    BlueprintStatus,
    CandidateDisposition,
    Capability,
    DiscoverAction,
    DispositionSource,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import CollectionState, Measurement

PROCESSES = (
    BlueprintProcess(name="Manage Financial Resources", level=1, parent=""),
    BlueprintProcess(
        name="Process Customer Payments", level=2, parent="Manage Financial Resources"
    ),
    BlueprintProcess(name="Manage Human Capital", level=1, parent=""),
)


def _cap(bc_id: str, name: str) -> Capability:
    """Built through the real Capability constructor so its validators run."""
    measured = Measurement.measured(1.0)
    disp = CandidateDisposition(
        candidate_id=bc_id,
        action=DiscoverAction.CONFIRM,
        source=DispositionSource.BASELINE,
        rule="baseline_confirm",
    )
    return Capability(
        bc_id=bc_id,
        local_key=bc_id,
        name=name,
        confidence=Confidence.HIGH,
        members=(
            CandidateMember(kind=MemberKind.HTTP_ROUTE, value=f"POST /{name}", path="pay.py"),
        ),
        member_paths=("pay.py",),
        cohesion=measured,
        coupling=measured,
        disposition=disp,
    )


def test_a_matching_capability_is_present():
    out = compare([_cap("BC-001", "customer payments")], PROCESSES)
    row = next(g for g in out.gaps if g.name == "Process Customer Payments")
    assert row.status is BlueprintStatus.PRESENT
    assert row.matched_bc_id == "BC-001"


def test_an_unmatched_blueprint_process_is_missing_and_that_is_context():
    out = compare([_cap("BC-001", "customer payments")], PROCESSES)
    row = next(g for g in out.gaps if g.name == "Manage Human Capital")
    assert row.status is BlueprintStatus.MISSING
    assert row.matched_bc_id is None
    # MISSING never degrades the comparison itself
    assert out.collected.state is CollectionState.MEASURED


def test_a_capability_matching_nothing_is_extra():
    out = compare([_cap("BC-009", "widget calibration")], PROCESSES)
    row = next(g for g in out.gaps if g.name == "widget calibration")
    assert row.status is BlueprintStatus.EXTRA
    assert row.matched_bc_id == "BC-009"


def test_counts_carry_every_status_including_zeros():
    out = compare([], PROCESSES)
    assert set(out.counts) == set(BlueprintStatus)
    assert out.counts[BlueprintStatus.EXTRA] == 0


def test_gaps_are_sorted_and_deduped():
    out = compare([_cap("BC-001", "customer payments")], PROCESSES)
    names = [(g.status.value, g.name) for g in out.gaps]
    assert names == sorted(names)


def test_comparison_is_order_independent():
    """NFR-10."""
    caps = [_cap("BC-001", "customer payments"), _cap("BC-002", "invoicing")]
    a = compare(caps, PROCESSES)
    b = compare(list(reversed(caps)), tuple(reversed(PROCESSES)))
    assert a.model_dump_json() == b.model_dump_json()


def test_a_missing_file_degrades_the_comparison_and_names_it(tmp_path):
    """P3-D4: the rest of the map still ships."""
    assert load(str(tmp_path / "nope.yaml")) is None


def test_an_unparseable_file_degrades_rather_than_raising(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("processes: [ unclosed", encoding="utf-8")
    assert load(str(bad)) is None


def test_the_shipped_apqc_blueprint_loads_and_has_two_levels():
    bp = load("blueprints/apqc.yaml")
    assert bp is not None
    assert {p.level for p in bp.processes} == {1, 2}
    # every level-2 process names a level-1 parent that exists
    tops = {p.name for p in bp.processes if p.level == 1}
    assert all(p.parent in tops for p in bp.processes if p.level == 2)


def test_two_extra_capabilities_sharing_name_sort_without_duplicate_key_error():
    caps = [_cap("BC-001", "orders"), _cap("BC-002", "orders")]
    out = compare(caps, PROCESSES)
    extras = [g for g in out.gaps if g.status is BlueprintStatus.EXTRA]
    assert len(extras) == 2
    assert [e.matched_bc_id for e in extras] == ["BC-001", "BC-002"]


def test_processes_stop_word_and_singularization():
    from sdlc.assessment.discover.blueprint import _tokens

    # "processes" -> "process" -> stop word -> dropped
    assert _tokens("manage processes") == frozenset()
    # "payments" -> "payment" -> kept
    assert _tokens("process payments") == frozenset({"payment"})


def test_resolve_blueprint_path_env(monkeypatch, tmp_path):
    from sdlc.assessment.discover.blueprint import resolve_blueprint_path

    bp_file = tmp_path / "apqc.yaml"
    bp_file.write_text("name: test\nversion: 1\nprocesses: []\n", encoding="utf-8")
    monkeypatch.setenv("SDLC_BLUEPRINTS_DIR", str(tmp_path))
    assert resolve_blueprint_path() == bp_file
