"""Schedule assets (E-12). schedules/<id>.yaml is the source of truth; the
filename is the schedule id. Deliberately mirrors agents/loader.py's
fail-closed shape — a malformed asset raises here, during `schedules apply`,
rather than silently at 3am.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import ScheduleAsset

SCHEDULES_DIR_ENV = "SDLC_SCHEDULES_DIR"
# repo_root/schedules — loader.py is src/sdlc/schedules/loader.py, so three
# parents up from the file dir is the repo root.
DEFAULT_SCHEDULES_DIR = Path(__file__).resolve().parents[3] / "schedules"


class ScheduleError(ValueError):
    """A schedule asset that violates a structural invariant (bad cron,
    unknown workflow, empty bank list)."""


def load_schedules(path: str | os.PathLike | None = None) -> list[ScheduleAsset]:
    """Parse every *.yaml in the schedules dir into ScheduleAssets, sorted by
    id. Resolution order: explicit arg, then $SDLC_SCHEDULES_DIR, then the
    shipped default. A missing or empty directory yields []; a malformed asset
    raises ScheduleError."""
    resolved = Path(path or os.environ.get(SCHEDULES_DIR_ENV) or DEFAULT_SCHEDULES_DIR)
    if not resolved.is_dir():
        return []
    assets: list[ScheduleAsset] = []
    for f in sorted(resolved.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            assets.append(ScheduleAsset(id=f.stem, **data))
        except (ValidationError, yaml.YAMLError, TypeError) as e:
            raise ScheduleError(f"{f.name}: {e}") from e
    return assets
