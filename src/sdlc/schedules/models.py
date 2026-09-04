"""Schedule configuration and asset models (spec A §2.2).

Owned by the horizontal schedules package.
"""

from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

KNOWN_SCHEDULE_WORKFLOWS = {"ReflectWorkflow"}


class ScheduleAction(BaseModel):
    """The start-workflow action of a schedule asset. Temporal Schedules can
    only start workflows, never activities — hence ReflectWorkflow."""

    workflow: str
    banks: list[str] = Field(min_length=1)
    backend: Literal["fake", "hindsight"] = "fake"
    base_url: str = "http://localhost:8888"

    @field_validator("workflow")
    @classmethod
    def _known_workflow(cls, v: str) -> str:
        if v not in KNOWN_SCHEDULE_WORKFLOWS:
            raise ValueError(f"unknown workflow {v!r}; known: {sorted(KNOWN_SCHEDULE_WORKFLOWS)}")
        return v


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
