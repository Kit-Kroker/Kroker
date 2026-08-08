"""The declared set of triage signals (FR-902).

One entry per signal, and `version` is what E-46 will fold into its
`(tree hash, signal version)` memo key -- bumping a signal's version
invalidates exactly that signal's cached result and nothing else.
"""
from __future__ import annotations

from pydantic import BaseModel

from .models import M_BUILDABLE, M_RUNNABLE, M_STRUCTURE, M_TESTS_PRESENT
from .signals import (
    baseline, build_probe, dependencies, misconfig, outliers, scaffold,
    secrets,
)


class SignalSpec(BaseModel):
    id: str
    version: int
    activity: str          # the @activity.defn name in triage/activities.py
    # E-42 D8a: the readiness dimensions this signal owes. Declared so a
    # skipped or failed signal reports not_collected for exactly these keys
    # rather than leaving the dimension unreported.
    readiness_keys: tuple[str, ...] = ()


SIGNALS: dict[str, SignalSpec] = {
    baseline.SIGNAL_ID: SignalSpec(
        id=baseline.SIGNAL_ID, version=baseline.VERSION,
        activity="triage_baseline",
        readiness_keys=(M_TESTS_PRESENT,)),
    secrets.SIGNAL_ID: SignalSpec(
        id=secrets.SIGNAL_ID, version=secrets.VERSION,
        activity="triage_secrets"),
    build_probe.SIGNAL_ID: SignalSpec(
        id=build_probe.SIGNAL_ID, version=build_probe.VERSION,
        activity="triage_build_probe",
        readiness_keys=(M_BUILDABLE, M_RUNNABLE)),
    dependencies.SIGNAL_ID: SignalSpec(
        id=dependencies.SIGNAL_ID, version=dependencies.VERSION,
        activity="triage_dependencies"),
    scaffold.SIGNAL_ID: SignalSpec(
        id=scaffold.SIGNAL_ID, version=scaffold.VERSION,
        activity="triage_scaffold",
        readiness_keys=(M_STRUCTURE,)),
    misconfig.SIGNAL_ID: SignalSpec(
        id=misconfig.SIGNAL_ID, version=misconfig.VERSION,
        activity="triage_misconfig"),
    outliers.SIGNAL_ID: SignalSpec(
        id=outliers.SIGNAL_ID, version=outliers.VERSION,
        activity="triage_outliers"),
}
