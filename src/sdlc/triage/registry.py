"""The declared set of triage signals (FR-902).

One entry per signal, and `version` is what E-46 will fold into its
`(tree hash, signal version)` memo key -- bumping a signal's version
invalidates exactly that signal's cached result and nothing else.
"""
from __future__ import annotations

from pydantic import BaseModel

from .signals import (
    baseline, build_probe, dependencies, misconfig, scaffold, secrets,
)


class SignalSpec(BaseModel):
    id: str
    version: int
    activity: str          # the @activity.defn name in triage/activities.py


SIGNALS: dict[str, SignalSpec] = {
    baseline.SIGNAL_ID: SignalSpec(
        id=baseline.SIGNAL_ID, version=baseline.VERSION,
        activity="triage_baseline"),
    secrets.SIGNAL_ID: SignalSpec(
        id=secrets.SIGNAL_ID, version=secrets.VERSION,
        activity="triage_secrets"),
    build_probe.SIGNAL_ID: SignalSpec(
        id=build_probe.SIGNAL_ID, version=build_probe.VERSION,
        activity="triage_build_probe"),
    dependencies.SIGNAL_ID: SignalSpec(
        id=dependencies.SIGNAL_ID, version=dependencies.VERSION,
        activity="triage_dependencies"),
    scaffold.SIGNAL_ID: SignalSpec(
        id=scaffold.SIGNAL_ID, version=scaffold.VERSION,
        activity="triage_scaffold"),
    misconfig.SIGNAL_ID: SignalSpec(
        id=misconfig.SIGNAL_ID, version=misconfig.VERSION,
        activity="triage_misconfig"),
}
