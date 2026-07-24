"""Containment policy (E-15/E-16, FR-703, ADR-17).

Pure: parsing and evaluation only. No subprocess, no CLI knowledge, no
Temporal. Everything CLI-specific lives in the adapters, everything
process-specific lives in hook.py — so the whole risk-classing decision is
unit-testable as a table.

Path resolution deliberately contains no __file__ walk, for the same reason
agents/loader.py does not: under `pip install .` the package lives in
site-packages, which has no relationship to where the policy asset lives.
Order: explicit arg -> $SDLC_CONTAINMENT_POLICY -> repo-root discovery.
"""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ..models import ContainmentLayer

POLICY_PATH_ENV = "SDLC_CONTAINMENT_POLICY"

# Two markers, not one: pyproject.toml alone matches any Python project we
# happen to be cwd'd into. Mirrors agents/loader.py:_ROOT_MARKERS.
_ROOT_MARKERS = ("pyproject.toml", "agents/registry.yaml")


class ContainmentError(ValueError):
    """A policy that violates a structural invariant, or cannot be found."""


class Predicate(str, Enum):
    """The complete predicate vocabulary. Adding a fifth is a code change
    plus a schema version bump — deliberately not an expression language."""
    PATH_OUTSIDE_WORKTREE = "path_outside_worktree"
    PATH_MATCHES = "path_matches"
    COMMAND_MATCHES = "command_matches"
    HOST_NOT_ALLOWLISTED = "host_not_allowlisted"


class Rule(BaseModel):
    id: str
    layer: ContainmentLayer      # MINIMUM capability required (spec §4a)
    tools: list[str]
    predicate: Predicate
    reason: str
    patterns: list[str] = Field(default_factory=list)
    allow_hosts: list[str] = Field(default_factory=list)


class Policy(BaseModel):
    version: int
    rules: list[Rule] = Field(default_factory=list)


def _discover_policy_file() -> Path | None:
    """Walk up from cwd for a checkout containing both markers. Dev and
    tests only — production sets $SDLC_CONTAINMENT_POLICY explicitly."""
    for d in (Path.cwd(), *Path.cwd().parents):
        if all((d / m).is_file() for m in _ROOT_MARKERS):
            return d / "policy" / "containment.yaml"
    return None


def _resolve_policy_path(path: str | os.PathLike | None = None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get(POLICY_PATH_ENV)
    if env:
        return Path(env)
    found = _discover_policy_file()
    if found is not None:
        return found
    raise ContainmentError(
        f"cannot locate the containment policy. Tried: an explicit path "
        f"argument; ${POLICY_PATH_ENV}; and walking up from {Path.cwd()} for "
        f"a directory containing both pyproject.toml and agents/registry.yaml.")


def load_policy(path: str | os.PathLike | None = None) -> Policy:
    """Parse and validate the policy asset. Raises ContainmentError on any
    structural problem — callers with containment enabled must fail closed."""
    p = _resolve_policy_path(path)
    if not p.is_file():
        raise ContainmentError(f"containment policy is not a file: {p}")

    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    version = raw.get("version")
    if version != 1:
        raise ContainmentError(
            f"unsupported containment policy version {version!r} in {p}; "
            f"expected 1")

    rules: list[Rule] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw.get("rules") or []):
        rid = (entry or {}).get("id", f"<rule {i}>")
        if rid in seen:
            raise ContainmentError(f"duplicate rule id {rid!r} in {p}")
        seen.add(rid)
        try:
            rules.append(Rule.model_validate(entry))
        except Exception as e:                    # noqa: BLE001 - re-typed
            raise ContainmentError(
                f"invalid rule {rid!r} in {p}: {e}") from e
    return Policy(version=version, rules=rules)
