"""The incident machine's pure step (023a T014, FR-006/007/008, R5–R7).

One call IS one cycle's Detect classification:

* cycle 1 records the baseline over the three detect signals and opens
  nothing (SC-001) — a repo's inherited sins are its normal, not incidents;
* later cycles classify with ``compute_delta`` (never a set difference),
  open an incident only for identities new relative to the baseline AND
  the open incidents, attach recurrences, and resolve on a collected
  disappearance;
* not-collected streaks, the per-cycle cap, the ``prev`` cap and
  signal-version re-baselining live here too.

Pure by design (AGENTS.md in this directory): stdlib + triage types +
models only; no I/O, no Temporal. Deterministic: every loop iterates a
sorted key, so the output is byte-identical across input orderings.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..measurement import CollectionState
from ..triage.delta import FindingState, compute_delta
from ..triage.models import RepoTriage, SignalResult, TriageFinding, finding_identity
from .models import (
    DETECT_SIGNALS,
    MAX_PREV_FINDINGS,
    TERMINAL_INCIDENT_STATES,
    Baseline,
    Incident,
    IncidentState,
    MaintenanceConfig,
    MaintenanceState,
)


class CycleEvents(BaseModel):
    """What one cycle did, for the workflow's prompts and notifications."""

    model_config = ConfigDict(extra="forbid")

    baseline_recorded: bool = False
    opened: list[int] = []  # incident numbers opened this cycle
    deferred: list[str] = []  # identities deferred by the per-cycle cap
    resolved_externally: list[int] = []  # incident numbers resolved by hand
    rebaselined_signals: list[str] = []  # signal ids whose version changed
    not_collected_escalations: list[str] = []  # signals that hit the streak
    truncated: bool = False  # prev/curr exceeded MAX_PREV_FINDINGS


def _filtered(triage: RepoTriage) -> RepoTriage:
    """Keep only the detect signals (R5), in a canonical order: the other
    four run but are ignored in 023a, and sorting (signals by id, findings
    by identity) makes the carried `prev` byte-identical regardless of the
    report's list order."""
    kept = sorted(
        (
            s.model_copy(update={"findings": sorted(s.findings, key=finding_identity)})
            for s in triage.signals
            if s.signal in DETECT_SIGNALS
        ),
        key=lambda s: s.signal,
    )
    return triage.model_copy(update={"signals": kept})


def _configured_off(cfg: MaintenanceConfig, signal: str) -> bool:
    """A signal disabled by configuration reads *not configured*, never
    *fault* (spec edge case): its streak never moves."""
    from ..triage.signals import build_probe, dependencies

    if signal == build_probe.SIGNAL_ID:
        return not cfg.build_probe
    if signal == dependencies.SIGNAL_ID:
        return cfg.advisory_source == "none"
    return False


def _signal_by(triage: RepoTriage, signal: str) -> SignalResult | None:
    for s in triage.signals:
        if s.signal == signal:
            return s
    return None


def _findings(triage: RepoTriage) -> int:
    return sum(len(s.findings) for s in triage.signals)


def step(state: MaintenanceState, curr: RepoTriage) -> tuple[MaintenanceState, CycleEvents]:
    """Classify one cycle's detect. ``state.cycle`` is the number of the
    cycle being processed; the carried state returns it incremented, so
    chained calls advance the counter by construction.
    """
    cfg = state.config
    cycle = state.cycle
    events = CycleEvents()
    cur = _filtered(curr)
    prev = _filtered(state.prev) if state.prev is not None else None

    # --- the prev guard (R6): never guess on a partial picture ----------
    if max(_findings(cur), _findings(prev) if prev else 0) > MAX_PREV_FINDINGS:
        events.truncated = True
        return state.model_copy(update={"prev": cur, "cycle": cycle + 1}), events

    # --- cycle 1: the baseline (SC-001) ----------------------------------
    if state.baseline is None or prev is None:
        baseline = Baseline(
            identities=frozenset(finding_identity(f) for s in cur.signals for f in s.findings),
            signal_versions={
                s.signal: s.version for s in sorted(cur.signals, key=lambda s: s.signal)
            },
            recorded_cycle=cycle,
            commit_sha=cur.commit_sha,
        )
        events.baseline_recorded = True
        return (
            state.model_copy(update={"baseline": baseline, "prev": cur, "cycle": cycle + 1}),
            events,
        )

    baseline = state.baseline
    incidents = [inc.model_copy() for inc in state.incidents]  # copy-on-write
    by_key: dict[str, Incident] = {
        inc.key: inc for inc in incidents if inc.state not in TERMINAL_INCIDENT_STATES
    }
    next_no = state.next_incident_no

    # --- signal-version changes: re-baseline that signal -----------------
    # compute_delta reports those findings UNVERIFIABLE (neither opens nor
    # resolves); the re-baseline accepts the new version's state as normal.
    cur_versions = {s.signal: s.version for s in cur.signals}
    prev_versions = {s.signal: s.version for s in prev.signals}
    rebaselined_identities: set[str] = set()
    for sig in sorted(cur_versions):
        if sig not in DETECT_SIGNALS or sig not in prev_versions:
            continue
        if cur_versions[sig] != prev_versions[sig]:
            events.rebaselined_signals.append(sig)
            cur_sig = _signal_by(cur, sig)
            rebaselined_identities.update(
                finding_identity(f) for f in (cur_sig.findings if cur_sig else [])
            )
    if events.rebaselined_signals:
        baseline = baseline.model_copy(
            update={
                "signal_versions": {
                    **baseline.signal_versions,
                    **{k: cur_versions[k] for k in sorted(cur_versions)},
                },
                "identities": baseline.identities | rebaselined_identities,
            }
        )

    # --- delta classification (R6/R7) ------------------------------------
    opened_this_cycle = 0
    for d in sorted(compute_delta(prev, cur), key=lambda d: d.identity):
        if d.state is FindingState.UNVERIFIABLE:
            continue  # never opens, never resolves (FR-007)
        inc = by_key.get(d.identity)

        if d.state is FindingState.NEW:
            if d.identity in baseline.identities:
                continue  # inherited from the baseline: not new (FR-007)
            if inc is not None:
                # Already carries a non-terminal incident (e.g. deferred by a
                # previous cap): attach, do not double-open.
                inc.last_seen_cycle = cycle
                inc.seen_count += 1
                if cfg.execute:
                    inc.consecutive_seen = 1  # a NEW is a fresh sighting (R9)
                if inc.state is IncidentState.DEFERRED:
                    inc.state = IncidentState.OPEN
                    inc.note = ""
                continue
            deferred = opened_this_cycle >= cfg.max_new_incidents_per_cycle
            finding = f_from_identity(cur, d.identity)
            incidents.append(
                Incident(
                    no=next_no,
                    key=d.identity,
                    kind="finding",
                    finding=finding,
                    commit_sha=cur.commit_sha,
                    first_seen_cycle=cycle,
                    last_seen_cycle=cycle,
                    seen_count=1,
                    state=IncidentState.DEFERRED if deferred else IncidentState.OPEN,
                    note=f"deferred: per-cycle cap of {cfg.max_new_incidents_per_cycle}"
                    if deferred
                    else "",
                )
            )
            by_key[d.identity] = incidents[-1]
            if deferred:
                events.deferred.append(d.identity)
            else:
                events.opened.append(next_no)
                opened_this_cycle += 1
            next_no += 1

        elif d.state is FindingState.PERSISTED:
            if inc is None:
                continue  # around but neither baselined nor incidented
            inc.last_seen_cycle = cycle
            inc.seen_count += 1
            if cfg.execute:
                # R9: the incident stays current with the fault, and the
                # Execute guard (R6) reads consecutive reproduction. Both
                # are execute-only: an execute-off loop is byte-identical
                # to 023a.
                cur_f = f_from_identity(cur, d.identity)
                if cur_f is not None:
                    inc.finding = cur_f
                inc.commit_sha = cur.commit_sha
                inc.consecutive_seen += 1
            if inc.state is IncidentState.DEFERRED:
                inc.state = IncidentState.OPEN  # picked up next cycle
                inc.note = ""

        elif d.state is FindingState.RESOLVED:
            # compute_delta yields RESOLVED only when the signal collected
            # on BOTH sides — an absence caused by not-collected arrives as
            # UNVERIFIABLE and never reaches here.
            if inc is None:
                continue
            if inc.state in (
                IncidentState.EXECUTING,
                IncidentState.VERIFYING,
                IncidentState.VERIFIED,
            ):
                # 023b R8 guard: an in-flight or verified repair is Report's
                # to close (via the ancestry check) — Detect never pre-empts.
                continue
            inc.state = IncidentState.RESOLVED_EXTERNALLY
            inc.last_seen_cycle = cycle
            events.resolved_externally.append(inc.no)

    # --- not-collected streaks (FR-006, spec edge) -------------------------
    streak = dict(state.not_collected_streak)
    esc_key = "not_collected::"
    for sig in sorted(DETECT_SIGNALS):
        if _configured_off(cfg, sig):
            streak.pop(sig, None)  # not configured, not a fault
            continue
        cur_s = _signal_by(cur, sig)
        if cur_s is None:
            continue  # absent from the report: no explicit measurement
        if cur_s.collected.state is CollectionState.MEASURED:
            streak.pop(sig, None)
            continue
        streak[sig] = streak.get(sig, 0) + 1
        if cfg.execute:
            # R9: a not-collected cycle for the identity's signal resets its
            # consecutive-reproduction count -- reproduction must be
            # CONSECUTIVE (R6), and a blind cycle breaks the chain.
            for inc in incidents:
                if inc.state in TERMINAL_INCIDENT_STATES or inc.finding is None:
                    continue
                if inc.finding.signal == sig:
                    inc.consecutive_seen = 0
        key = f"{sig}:{esc_key}"
        if streak[sig] >= 2 and key not in by_key:
            incidents.append(
                Incident(
                    no=next_no,
                    key=key,
                    kind="detect_escalation",
                    finding=None,
                    commit_sha=cur.commit_sha,
                    first_seen_cycle=cycle,
                    last_seen_cycle=cycle,
                    seen_count=1,
                    state=IncidentState.OPEN,
                    note=f"{sig} did not collect {streak[sig]} cycles running",
                )
            )
            by_key[key] = incidents[-1]
            events.not_collected_escalations.append(sig)
            next_no += 1

    carried = state.model_copy(
        update={
            "baseline": baseline,
            "prev": cur,
            "incidents": incidents,
            "not_collected_streak": streak,
            "next_incident_no": next_no,
            "cycle": cycle + 1,
        }
    )
    return carried, events


def f_from_identity(triage: RepoTriage, identity: str) -> TriageFinding | None:
    """The finding behind an identity, for the incident record."""
    for s in triage.signals:
        for f in s.findings:
            if finding_identity(f) == identity:
                return f
    return None
