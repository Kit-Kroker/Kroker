"""Schedule configuration and asset models (spec A §2.2, 023a R10).

Owned by the horizontal schedules package. Since 023a the action is a
discriminated union on ``workflow``: the nightly Reflect asset keeps its
exact shape, and a maintenance-kick asset starts the loop's kicker. The
union is closed — an unknown workflow name is a validation error, not an
extension point.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

KNOWN_SCHEDULE_WORKFLOWS = {"ReflectWorkflow", "MaintenanceKickWorkflow"}


class ReflectAction(BaseModel):
    """The nightly memory-consolidation asset (E-12; E-25 adds the org
    promotion fields)."""

    workflow: Literal["ReflectWorkflow"] = "ReflectWorkflow"
    banks: list[str] = Field(min_length=1)
    backend: Literal["fake", "hindsight"] = "fake"
    base_url: str = "http://localhost:8888"
    # None keeps the job project-only. When set (the shipped asset: "org"),
    # gotchas recurring across `banks` promote into this bank, which then
    # reflects too (E-25) — org never rides `banks` itself.
    org_bank: str | None = None
    # ge=2 is the promotion floor, not a tuning knob: a threshold of 1 would
    # mirror a single project's gotchas into org, which is not cross-project
    # promotion. Both fields default so a pre-E-25 live Schedule whose
    # recorded args lack them still validates (org half off).
    promote_min_projects: int = Field(default=2, ge=2)


class MaintenanceKickAction(BaseModel):
    """The DAPER loop's schedule kicker (023a FR-003): starts
    MaintenanceKickWorkflow, which signals the project's loop. The
    project slug rule is the domain model's — reused, not restated."""

    workflow: Literal["MaintenanceKickWorkflow"] = "MaintenanceKickWorkflow"
    project: str

    @field_validator("project")
    @classmethod
    def _project_is_a_valid_slug(cls, v: str) -> str:
        from ..maintenance.models import MaintenanceKickInput

        MaintenanceKickInput(project=v)  # raises on a bad slug
        return v


#: Discriminated on `workflow`: one union, closed by the Literal fields.
ScheduleAction = Annotated[ReflectAction | MaintenanceKickAction, Field(discriminator="workflow")]


class ScheduleSpecAsset(BaseModel):
    cron: str
    timezone: str = "UTC"

    @field_validator("cron")
    @classmethod
    def _cron_shape(cls, v: str) -> str:
        if len(v.split()) != 5:
            raise ValueError(
                f"cron must have 5 whitespace-separated fields, got {len(v.split())}: {v!r}"
            )
        return v


class ScheduleAsset(BaseModel):
    """One schedules/<id>.yaml. `id` comes from the filename, not the body —
    the filename is the API."""

    id: str
    spec: ScheduleSpecAsset
    action: ScheduleAction

    @model_validator(mode="after")
    def _kick_assets_are_hourly_or_slower(self) -> ScheduleAsset:
        """FR-003's cadence bound: the kick runs the maintenance loop, whose
        cycle is dominated by a 40-minute build probe — a sub-hourly cadence
        would only queue overlapping nudges. Reflect assets keep any 5-field
        cron: their cadence rule is untouched."""
        if not isinstance(self.action, MaintenanceKickAction):
            return self
        minute = self.spec.cron.split()[0]
        if not (minute.isdigit() and 0 <= int(minute) <= 59):
            raise ValueError(
                f"maintenance-kick schedule {self.id!r} must run hourly or slower: "
                f"the cron minute field must be a single integer, got {minute!r} "
                f"in {self.spec.cron!r}"
            )
        return self
