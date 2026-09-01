"""E-41a's advisory-source seam (spec D11).

THE DEFAULT COLLECTS NOTHING. Vulnerability data requires an advisory
database, which means sending a client repository's dependency list off-box;
that is a trust-boundary decision, not an implementation detail. The seam
mirrors MemoryConfig.backend defaulting to `fake` and ADR-19's
adapters-not-substrate rule: an offline no-op default plus one reference
implementation, opt-in per run.

Every failure path returns not_collected. NONE returns an empty advisory
list. A lookup that did not happen reading as zero vulnerabilities is the
malformed-SARIF hole E-40 closed on the absolute floor (FR-915), and
installing the same conflation in a new signal would be indefensible.

`OsvAdvisorySource` is an outbound call about a client repository and is
recorded as a declared, opt-in, off-by-default egress under FR-703.

Pure of temporalio, like the signal modules: the HTTP happens inside an
activity, never in workflow code.
"""

from __future__ import annotations

import json
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Sequence

from pydantic import BaseModel, Field

from ..measurement import Measurement
from .models import FindingSeverity


class Advisory(BaseModel):
    package: str  # the normalized distribution name queried
    constraint: str = ""  # the declaration as written, when the caller has it
    advisory_id: str  # e.g. "GHSA-xxxx-xxxx-xxxx" / "PYSEC-2024-1"
    severity: FindingSeverity  # critical | high | medium | low
    summary: str = ""


class AdvisoryResult(BaseModel):
    """`collected` is a Measurement, not len(advisories): "we did not look"
    and "we looked and found none" are different facts (D11/D16). When
    MEASURED, its value is the number of advisories returned."""

    collected: Measurement
    advisories: list[Advisory] = Field(default_factory=list)


class AdvisorySource(ABC):
    name: str

    @abstractmethod
    def lookup(self, ecosystem: str | None, packages: Sequence[str]) -> AdvisoryResult:
        """Advisories for `packages` in `ecosystem`. MUST NOT raise: an
        unreachable database is a not_collected report, not a failed signal."""


class NoneAdvisorySource(AdvisorySource):
    """The default. Collects nothing, and says so with a reason the report
    carries, so "no vulnerabilities listed" is never mistaken for "none
    exist"."""

    name = "none"

    def __init__(self, reason: str = "no advisory source configured") -> None:
        self._reason = reason

    def lookup(self, ecosystem: str | None, packages: Sequence[str]) -> AdvisoryResult:
        return AdvisoryResult(collected=Measurement.not_collected(self._reason))


OSV_URL = "https://api.osv.dev/v1/query"
OSV_TIMEOUT_S = 20
OSV_MAX_PACKAGES = 200

# GHSA supplies MODERATE where our TriageFinding vocabulary says medium.
_SEVERITY_WORDS: dict[str, FindingSeverity] = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MODERATE": "medium",
    "MEDIUM": "medium",
    "LOW": "low",
}


def _severity(vuln: dict) -> FindingSeverity:
    """The advisory's severity label, defaulting to `high`.

    The default is not a fabricated measurement: the vulnerability itself is
    measured -- OSV returned it -- and only its LABEL is missing. Defaulting
    down would under-report a known vulnerability, which is the wrong way to
    be wrong on a security signal.
    """
    # `or {}` not a .get default: OSV sends an explicit null here, and
    # None.get would raise inside the one function that must not.
    specific = vuln.get("database_specific") or {}
    word = str(specific.get("severity", "")).upper()
    return _SEVERITY_WORDS.get(word, "high")


class OsvAdvisorySource(AdvisorySource):
    """The one reference implementation (ADR-19: adapters, not substrate).

    Uses /v1/query per package rather than /v1/querybatch: batch returns only
    ids, so severity would need a second round-trip per hit, and a severity
    we did not fetch is exactly the value this seam refuses to invent.

    `max_packages` bounds the call count. Exceeding it reports not_collected
    rather than answering for a prefix of the list -- a partial lookup
    presented as a lookup is the D16 error.
    """

    name = "osv"

    def __init__(
        self,
        url: str = OSV_URL,
        timeout_s: int = OSV_TIMEOUT_S,
        max_packages: int = OSV_MAX_PACKAGES,
    ) -> None:
        self._url = url
        self._timeout_s = timeout_s
        self._max_packages = max_packages

    def lookup(self, ecosystem: str | None, packages: Sequence[str]) -> AdvisoryResult:
        if not ecosystem:
            return AdvisoryResult(
                collected=Measurement.not_collected(
                    "the resolved toolchain declares no OSV ecosystem"
                )
            )
        if len(packages) > self._max_packages:
            return AdvisoryResult(
                collected=Measurement.not_collected(
                    f"{len(packages)} packages exceeds the {self._max_packages} "
                    f"query cap; a partial lookup is not a lookup"
                )
            )
        if not packages:
            return AdvisoryResult(collected=Measurement.measured(0.0))

        found: list[Advisory] = []
        for name in packages:
            body = json.dumps({"package": {"name": name, "ecosystem": ecosystem}}).encode()
            try:
                req = urllib.request.Request(
                    self._url, data=body, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                    if resp.status != 200:
                        return AdvisoryResult(
                            collected=Measurement.not_collected(
                                f"OSV returned HTTP {resp.status} for {name!r}"
                            )
                        )
                    payload = json.loads(resp.read().decode())
            except Exception as exc:  # noqa: BLE001 -- docstring
                return AdvisoryResult(
                    collected=Measurement.not_collected(
                        f"OSV lookup failed for {name!r}: {type(exc).__name__}: {exc}"
                    )
                )
            for vuln in payload.get("vulns") or []:
                found.append(
                    Advisory(
                        package=name,
                        advisory_id=str(vuln.get("id", "")),
                        severity=_severity(vuln),
                        summary=str(vuln.get("summary", ""))[:300],
                    )
                )
        return AdvisoryResult(collected=Measurement.measured(float(len(found))), advisories=found)


ADVISORY_SOURCES: dict[str, type[AdvisorySource]] = {
    NoneAdvisorySource.name: NoneAdvisorySource,
    OsvAdvisorySource.name: OsvAdvisorySource,
}


def resolve_advisory_source(name: str) -> AdvisorySource:
    """The named source, or the collecting-nothing default.

    An operator typo must not fail a triage, but it must not vanish either:
    the fallback carries the unknown name in its reason, so the report says
    which source was asked for and never found.
    """
    cls = ADVISORY_SOURCES.get(name)
    if cls is None:
        return NoneAdvisorySource(f"unknown advisory source {name!r}; no lookup was performed")
    return cls()
