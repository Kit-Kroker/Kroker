# src/sdlc/board/models.py
"""Board entities. The mutable graph SQLite holds; artifact BODIES live in
the claim-check store and are referenced by uri+sha256, never inlined here."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ArtifactStatus(str, Enum):
    PROPOSED = "proposed"
    CURRENT = "current"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"
    QUARANTINED = "quarantined"


class Authority(str, Enum):
    """Who moved a status. Only AUTHORITATIVE writes touch
    BoardTask.authoritative_status, which is what scoring reads."""
    AUTHORITATIVE = "authoritative"      # workflow activities
    OBSERVATIONAL = "observational"      # agents


class ArtifactVersion(BaseModel):
    id: int
    project: str
    key: str
    n: int
    run_id: str
    sha256: str
    uri: str
    supersedes: int | None = None
    created_at: datetime


class BoardArtifact(BaseModel):
    project: str
    key: str
    status: ArtifactStatus
    current_version: int | None = None


class BoardTask(BaseModel):
    project: str
    plan_version: int
    task_id: str
    run_id: str
    status: TaskStatus
    authoritative_status: TaskStatus
    row_version: int
    fix_attempts: int = 0
    error: str | None = None
    branch: str | None = None
    updated_at: datetime

    @property
    def diverged(self) -> bool:
        """An agent moved status somewhere the workflow has not confirmed."""
        return self.status != self.authoritative_status


class TaskEvidence(BaseModel):
    id: int
    project: str
    plan_version: int
    task_id: str
    run_id: str
    kind: str                 # qa | review | deep_review
    sha256: str
    uri: str
    created_at: datetime


class BoardEvent(BaseModel):
    id: int
    project: str
    subject: str              # "artifact:<key>" | "task:<plan_version>:<id>"
    actor: str                # "workflow:<run_id>" | "agent:<name>"
    authority: Authority
    from_status: str | None = None
    to_status: str | None = None
    at: datetime
    detail: str = ""


class BoardStats(BaseModel):
    """Board-owned counters only. Quality/cost/speed rollup stays in
    benchmarks/ — duplicating it here would produce two scores that disagree."""
    project: str
    tasks_by_status: dict[str, int] = Field(default_factory=dict)
    total_fix_attempts: int = 0
    tasks_with_error: int = 0
    diverged_tasks: int = 0
    event_count: int = 0
