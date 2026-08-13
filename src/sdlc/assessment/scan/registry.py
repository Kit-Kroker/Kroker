"""The declared set of scan signals (FR-912).

One entry per signal. `version` and `module` are what signal_key folds into
its memo key, and `consumes` does double duty -- both uses are DERIVATIONS,
never second declarations: the fan-out wave (wave_of) and the transitive
rules_sha (rules.py).

Pure of temporalio: `activity` is the activity's NAME, resolved by the
workflow, so this module stays importable without a Temporal runtime -- the
same discipline triage/registry.py keeps.
"""
from __future__ import annotations

from pydantic import BaseModel, model_validator

from .models import (
    CATEGORIES, SCAN_ORDER, ScanSignalId, SignalFamily, SignalSource,
    family_of,
)

_SIG = "sdlc.assessment.scan.signals"


class ScanSignalSpec(BaseModel):
    id: ScanSignalId
    family: SignalFamily
    version: int
    source: SignalSource
    module: str                              # dotted path, hashed by rules_sha
    activity: str = ""                       # @activity.defn name, or ""
    in_workflow: bool = False                # pure derivation, no activity
    inherits: tuple[str, ...] = ()           # "triage:<signal>"
    rule_modules: tuple[str, ...] = ()       # shared modules, hashed too
    consumes: tuple[ScanSignalId, ...] = ()  # upstream signals
    categories: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _source_fields_agree(self) -> "ScanSignalSpec":
        if self.source is SignalSource.COMPUTED and self.inherits:
            raise ValueError(
                f"{self.id.value}: source=computed declares inherits "
                f"{self.inherits} -- a computed signal inherits nothing (D2)")
        if self.source is not SignalSource.COMPUTED and not self.inherits:
            raise ValueError(
                f"{self.id.value}: source={self.source.value} declares no "
                f"inherits -- an inherited fact must name its producer (D2)")
        if self.source is SignalSource.INHERITED and self.activity:
            raise ValueError(
                f"{self.id.value}: source=inherited declares activity "
                f"{self.activity!r} -- it computes nothing, so it runs no "
                f"activity")
        if not self.activity and not self.in_workflow \
                and self.source is not SignalSource.INHERITED:
            raise ValueError(
                f"{self.id.value}: declares no activity and is not "
                f"in_workflow -- nothing would ever run it")
        if self.activity and self.in_workflow:
            raise ValueError(
                f"{self.id.value}: declares both an activity and "
                f"in_workflow -- exactly one runs a signal")
        return self

    @model_validator(mode="after")
    def _agrees_with_the_artifact(self) -> "ScanSignalSpec":
        if self.family is not family_of(self.id):
            raise ValueError(f"{self.id.value}: family contradicts its id")
        if self.categories != CATEGORIES[self.id]:
            raise ValueError(
                f"{self.id.value}: categories {self.categories} disagree with "
                f"CATEGORIES {CATEGORIES[self.id]} -- models.py is the one "
                f"declaration")
        return self


def _spec(sid: ScanSignalId, version: int, source: SignalSource, *,
          module: str, activity: str = "", in_workflow: bool = False,
          inherits: tuple[str, ...] = (),
          rule_modules: tuple[str, ...] = (),
          consumes: tuple[ScanSignalId, ...] = ()) -> ScanSignalSpec:
    return ScanSignalSpec(
        id=sid, family=family_of(sid), version=version, source=source,
        module=module, activity=activity, in_workflow=in_workflow,
        inherits=inherits, rule_modules=rule_modules, consumes=consumes,
        categories=CATEGORIES[sid])


_NAMING = f"{_SIG.rsplit('.', 1)[0]}.naming"     # scan.naming, shared by S3+S5
# scan.sources, shared by S1+S3: both select blobs with SOURCE_EXTENSIONS, so
# both must hash it or editing the tuple silently serves a stale S3 (D10).
_SOURCES = f"{_SIG.rsplit('.', 1)[0]}.sources"
# scan.testpaths, shared by S2 (exclude fixture schemas), QS1 (find tests),
# QS2 (exclude tests from significant files) and QS3 (exclude tests from
# testability findings). All four hash it, or editing a glob would move four
# signals' output while their keys stood still (P3-D9, D10).
_TESTPATHS = f"{_SIG.rsplit('.', 1)[0]}.testpaths"
# scan.configpaths, shared by SS3 (config rules) and E-47b's attribution
# module. SS3 hashes it, or editing a pattern would move SS3's output while
# its key stood still (D10).
_CONFIGPATHS = f"{_SIG.rsplit('.', 1)[0]}.configpaths"

SCAN_SIGNALS: dict[ScanSignalId, ScanSignalSpec] = {
    ScanSignalId.S1: _spec(
        ScanSignalId.S1, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.packages", activity="scan_packages",
        rule_modules=(_NAMING, _SOURCES)),
    ScanSignalId.S2: _spec(
        ScanSignalId.S2, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.schema", activity="scan_schema",
        rule_modules=(_NAMING, _SOURCES, _TESTPATHS)),
    ScanSignalId.S3: _spec(
        ScanSignalId.S3, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.entrypoints", activity="scan_entrypoints",
        rule_modules=(_NAMING, _SOURCES)),
    ScanSignalId.S4: _spec(
        ScanSignalId.S4, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.frontend", activity="scan_frontend",
        rule_modules=(_NAMING,)),
    ScanSignalId.S5: _spec(
        ScanSignalId.S5, 1, SignalSource.COMPUTED,
        module="sdlc.assessment.scan.merge", in_workflow=True,
        rule_modules=(_NAMING,),
        consumes=(ScanSignalId.S1, ScanSignalId.S2, ScanSignalId.S3,
                  ScanSignalId.S4)),
    ScanSignalId.SS1: _spec(
        ScanSignalId.SS1, 1, SignalSource.EXTENDED,
        module=f"{_SIG}.security_static", activity="scan_security_static",
        inherits=("triage:misconfig", "triage:secrets"),
        rule_modules=(_SOURCES,),
        consumes=(ScanSignalId.S3,)),
    ScanSignalId.SS2: _spec(
        ScanSignalId.SS2, 1, SignalSource.INHERITED,
        module="sdlc.assessment.scan.inherit",
        inherits=("triage:dependencies",)),
    ScanSignalId.SS3: _spec(
        ScanSignalId.SS3, 1, SignalSource.EXTENDED,
        module=f"{_SIG}.config_infra", activity="scan_config_infra",
        inherits=("triage:misconfig",),
        rule_modules=(_CONFIGPATHS,)),
    ScanSignalId.SS4: _spec(
        ScanSignalId.SS4, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.sensitivity", activity="scan_sensitivity",
        rule_modules=(_NAMING,),
        # P3-D3: accessed_by cites S3, so S3 is DECLARED. _upstream_for
        # filters on this tuple and rules_sha walks it, so an undeclared read
        # would also be an unhashed input -- the D10 hazard exactly.
        consumes=(ScanSignalId.S2, ScanSignalId.S3)),
    ScanSignalId.QS1: _spec(
        ScanSignalId.QS1, 1, SignalSource.EXTENDED,
        module=f"{_SIG}.tests_inventory", activity="scan_tests_inventory",
        inherits=("triage:baseline",),
        rule_modules=(_SOURCES, _TESTPATHS)),
    ScanSignalId.QS2: _spec(
        ScanSignalId.QS2, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.coverage", activity="scan_coverage",
        rule_modules=(_SOURCES, _TESTPATHS),
        consumes=(ScanSignalId.QS1,)),
    ScanSignalId.QS3: _spec(
        ScanSignalId.QS3, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.testability", activity="scan_testability",
        rule_modules=(_SOURCES, _TESTPATHS)),
    ScanSignalId.QS4: _spec(
        ScanSignalId.QS4, 1, SignalSource.EXTENDED,
        module=f"{_SIG}.ci", activity="scan_ci",
        inherits=("triage:baseline",)),
}

# S5 is in_workflow, so its `consumes` drives rules_sha but not a wave.
MAX_WAVE = 2


def wave_of(signal_id: ScanSignalId) -> int:
    """DERIVED from `consumes`, never assigned: adding a dependent signal is a
    registry edit, not a workflow edit, and the two cannot disagree."""
    return 1 if not SCAN_SIGNALS[signal_id].consumes else 2


def _build_waves() -> tuple[tuple[ScanSignalId, ...], ...]:
    """Activity-bearing signals grouped by wave, in SCAN_ORDER within each."""
    waves: list[tuple[ScanSignalId, ...]] = []
    for wave in range(1, MAX_WAVE + 1):
        waves.append(tuple(
            s for s in SCAN_ORDER
            if SCAN_SIGNALS[s].activity and wave_of(s) == wave))
    return tuple(waves)


WAVES: tuple[tuple[ScanSignalId, ...], ...] = _build_waves()


def _assert_registry_is_sound() -> None:
    """Boot assertions. A drifted registry fails at import, not at the first
    assessment -- the discipline validate_registry applies to agents.yaml.
    """
    missing = set(SCAN_ORDER) - set(SCAN_SIGNALS)
    if missing:
        raise RuntimeError(
            f"SCAN_SIGNALS is missing {sorted(s.value for s in missing)} -- "
            f"the registry must cover SCAN_ORDER exactly")
    for sid, spec in SCAN_SIGNALS.items():
        for upstream in spec.consumes:
            if upstream is sid:
                raise RuntimeError(f"{sid.value} consumes itself")
            if SCAN_SIGNALS[upstream].consumes and spec.activity:
                raise RuntimeError(
                    f"{sid.value} consumes {upstream.value}, which itself "
                    f"consumes -- only {MAX_WAVE} waves are supported, so a "
                    f"three-deep chain would be silently truncated")
    covered = {s for wave in WAVES for s in wave}
    expected = {s for s, spec in SCAN_SIGNALS.items() if spec.activity}
    if covered != expected:
        raise RuntimeError(
            f"WAVES cover {sorted(s.value for s in covered)} but "
            f"{sorted(s.value for s in expected)} declare an activity")


_assert_registry_is_sound()
