# src/sdlc/assessment/discover/blueprint.py
"""FR-913 (E-48 DD11, clause D8): the discovered set against a reference
blueprint. MISSING is context, not failure.

Pure by design. The one impurity is `load`, which reads a repo-root YAML file
the FACTORY ships -- not the assessed repository -- so it executes nothing and
is not part of NFR-9's surface.

P3-D6: normalization is local rather than imported from scan/naming.py.
Importing it would be legal, but test_scan_rules_sha pins naming.py to six
signals' memo keys, so curating a blueprint would move six scan signal keys.
Blueprint matching is not a scan rule and must not be hashed as one.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Sequence
from pathlib import Path

import yaml
from pydantic import BaseModel

from ...measurement import Measurement
from .map import (
    BlueprintComparison,
    BlueprintGap,
    BlueprintStatus,
    Capability,
)

DEFAULT_BLUEPRINT = "blueprints/apqc.yaml"

# Words that carry no discriminating power in a process name. Deliberately
# short: an aggressive stop list makes everything match everything, and a
# false PRESENT hides a real gap, which is the direction that costs.
_STOP = frozenset(
    {
        "and",
        "the",
        "of",
        "for",
        "to",
        "a",
        "an",
        "manage",
        "develop",
        "deliver",
        "process",
        "maintain",
        "perform",
    }
)
_SPLIT = re.compile(r"[^a-z0-9]+")


def _singularize(word: str) -> str:
    """Local singularization, keeping blueprint matching independent of scan rules memo."""
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    for group in ("sses", "shes", "ches", "xes", "zes"):
        if len(word) > len(group) and word.endswith(group):
            return word[:-2]
    if len(word) > 2 and word.endswith("s") and not word.endswith("ss") and not word.endswith("us"):
        return word[:-1]
    return word


def _tokens(name: str) -> frozenset[str]:
    """Lowercase alphanumeric tokens, stop words removed, singularized.
    English-centric, and OQ-12 already records that limitation for S5's
    normalization; the same caveat applies here."""
    raw = (_singularize(t) for t in _SPLIT.split(name.lower()) if t)
    return frozenset(t for t in raw if t and t not in _STOP)


class BlueprintProcess(BaseModel):
    model_config = {"frozen": True}
    name: str
    level: int
    parent: str = ""


class Blueprint(BaseModel):
    model_config = {"frozen": True}
    name: str
    version: str
    processes: tuple[BlueprintProcess, ...]


def resolve_blueprint_path(path: str | Path | None = None) -> Path:
    """Resolve blueprint yaml path honoring SDLC_BLUEPRINTS_DIR, repo root fallback, and CWD."""
    if path:
        return Path(path)
    env_dir = os.environ.get("SDLC_BLUEPRINTS_DIR")
    if env_dir:
        candidate = Path(env_dir) / "apqc.yaml"
        if candidate.exists():
            return candidate
    repo_root = Path(__file__).resolve().parents[4]
    candidate = repo_root / "blueprints" / "apqc.yaml"
    if candidate.exists():
        return candidate
    return Path(DEFAULT_BLUEPRINT)


def load(path: str | Path | None = None) -> Blueprint | None:
    """The blueprint, or None when the file is absent or will not parse.

    Returns None rather than raising (P3-D4): the caller reports
    not_collected naming the file, and the rest of the map ships.
    """
    target = resolve_blueprint_path(path)
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return Blueprint(
            name=raw["name"],
            version=str(raw["version"]),
            processes=tuple(
                BlueprintProcess(name=p["name"], level=int(p["level"]), parent=p.get("parent", ""))
                for p in raw["processes"]
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _matches(cap_tokens: frozenset[str], proc_tokens: frozenset[str]) -> bool:
    """A match is a non-empty token intersection covering at least half the
    blueprint process's tokens. Half rather than all: "Process Customer
    Payments" should match a "customer payments" capability, and requiring
    every token would make the level-2 rows unmatchable in practice."""
    if not cap_tokens or not proc_tokens:
        return False
    shared = cap_tokens & proc_tokens
    return len(shared) * 2 >= len(proc_tokens)


def compare(
    capabilities: Iterable[Capability],
    processes: Sequence[BlueprintProcess],
    *,
    name: str = "",
    version: str = "",
) -> BlueprintComparison:
    """PRESENT / MISSING / EXTRA over the discovered set.

    A capability may satisfy more than one process (a level-1 row and its
    level-2 child); each process gets its own row, so the counts describe
    processes rather than capabilities.
    """
    caps = [(c, _tokens(c.name)) for c in capabilities]
    matched_bc_ids: set[str] = set()
    gaps: list[BlueprintGap] = []

    for proc in processes:
        proc_tokens = _tokens(proc.name)
        hit = next((c for c, toks in caps if _matches(toks, proc_tokens)), None)
        if hit is None:
            gaps.append(
                BlueprintGap(
                    name=proc.name,
                    status=BlueprintStatus.MISSING,
                    level=proc.level,
                    parent=proc.parent,
                )
            )
        else:
            matched_bc_ids.add(hit.bc_id)
            gaps.append(
                BlueprintGap(
                    name=proc.name,
                    status=BlueprintStatus.PRESENT,
                    level=proc.level,
                    parent=proc.parent,
                    matched_bc_id=hit.bc_id,
                )
            )

    for cap, _ in caps:
        if cap.bc_id not in matched_bc_ids:
            gaps.append(
                BlueprintGap(name=cap.name, status=BlueprintStatus.EXTRA, matched_bc_id=cap.bc_id)
            )

    ordered = tuple(sorted(gaps, key=lambda g: (g.status.value, g.name, g.matched_bc_id or "")))
    return BlueprintComparison(
        blueprint=name,
        version=version,
        gaps=ordered,
        counts={s: sum(1 for g in ordered if g.status is s) for s in BlueprintStatus},
        collected=Measurement.measured(float(len(ordered))),
    )


def not_compared(reason: str) -> BlueprintComparison:
    """P3-D4's degraded row, named for what it is."""
    return BlueprintComparison(collected=Measurement.not_collected(reason))
