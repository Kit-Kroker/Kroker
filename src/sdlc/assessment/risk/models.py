"""FR-916 (E-49): the UnifiedRiskMap contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as
assessment/models.py, triage/models.py and discover/map.py must not: a
dependency here would appear as a reviewable import.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from ...measurement import CollectionState, Measurement

MAX_DRIVERS = 3


class Factor(BaseModel):
    """One input to a composite, with its own Measurement.

    The Measurement is per-factor rather than per-composite because that is
    what makes `partial` derivable (RD3): a composite whose factors each
    carry their own collection state cannot claim a partiality its factors
    contradict.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    key: str
    value: Measurement
    weight: float = 1.0

    @property
    def collected(self) -> bool:
        return self.value.state is CollectionState.MEASURED


class Driver(BaseModel):
    """FR-916's driver as a typed reference to a factor that exists (RD9).

    The source schema guards drivers with a minimum string length, because a
    model-authored driver is prose and length is the only property prose
    admits. Here the composite is computed, so a driver names a factor key
    and carries its contribution -- a generic label is unrepresentable rather
    than merely improbable.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    factor_key: str
    value: float
    contribution: float


class Composite(BaseModel):
    """A score over factors, or the reason it is not one.

    `is_partial` is a PROPERTY, never a field: CollectionState has three
    members and adding a fourth would change a type CoverageReport,
    SecurityReport, triage, scan and discover all share, for one consumer's
    need (RD3). Partiality is a fact about the factors, so it is read from
    them.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    value: Measurement
    factors: tuple[Factor, ...] = ()
    drivers: tuple[Driver, ...] = ()

    @property
    def collected_factors(self) -> tuple[Factor, ...]:
        return tuple(f for f in self.factors if f.collected)

    @property
    def is_partial(self) -> bool:
        """Some collected, some not. All-or-nothing is not partial."""
        got = len(self.collected_factors)
        return 0 < got < len(self.factors)

    @model_validator(mode="after")
    def _factors_are_sorted(self) -> "Composite":
        keys = [f.key for f in self.factors]
        if keys != sorted(keys):
            raise ValueError(
                f"factors must be sorted by key, got {keys} -- a producer "
                f"emitting discovery order is an NFR-10 determinism bug, and "
                f"repairing it here would hide that bug")
        return self

    @model_validator(mode="after")
    def _measured_means_every_factor_collected(self) -> "Composite":
        if self.value.state is CollectionState.MEASURED:
            missing = [f.key for f in self.factors if not f.collected]
            if missing:
                raise ValueError(
                    f"composite is MEASURED but factor(s) {missing} did not "
                    f"collect -- a number over a subset of its specified "
                    f"factors is the conflation FR-915 exists to prevent")
        return self

    @model_validator(mode="after")
    def _drivers_need_a_collected_factor(self) -> "Composite":
        """RD9's third case: no factor collected means no drivers."""
        if self.drivers and not self.collected_factors:
            raise ValueError(
                "drivers were supplied but no collected factor exists -- "
                "_unmeasured_carries_no_payload")
        if len(self.drivers) > MAX_DRIVERS:
            raise ValueError(
                f"at most three drivers (FR-916), got {len(self.drivers)}")
        keys = {f.key for f in self.factors}
        for d in self.drivers:
            if d.factor_key not in keys:
                raise ValueError(
                    f"driver names no factor: {d.factor_key!r} is not among "
                    f"{sorted(keys)}")
        return self
