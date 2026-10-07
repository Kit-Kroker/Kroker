"""012 (data-model §2.2, contract §2.7): run provenance and prompt hashes.

`resolve_provenance` is the activity the benchmark parent runs once at
start: git in the Kroker source root; else ``KROKER_COMMIT`` (+ optional
``KROKER_TREE_DIRTY``); else explicitly unknown. The result rides
``BenchmarkConfig`` into every cell so every record of a run carries the
same values even if the worker restarts (research R-7).

`prompt_sha_for` is pure import-time data over the shipped registry: the
sha256 of a prompted role's ``instructions.md`` (the same bytes
``PROMPT_SHAS`` hashes), or an explicit ``none:<reason>`` sentinel — a 012
writer never records an empty prompt hash.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from typing import TYPE_CHECKING

from temporalio import activity

# Via the loader, never agents.roles: roles pulls the clarify stage (and
# with it benchmarks.record_builder), which would make this module a cycle
# once the record builder imports prompt_sha_for. The loader reads the
# same agents/ tree roles.REGISTRY is built from.
from ..agents.loader import RoleConfig, load_registry

UNKNOWN_COMMIT = "unknown"

if TYPE_CHECKING:
    # The real binding is the module __getattr__ below (lazy on first
    # access): importing this module must stay cheap — the promptfoo
    # provider's import chain reaches it through record_builder, and its
    # 8-second worker-readiness budget has no room for a full registry
    # load per import (tests/test_promptfoo_provider.py pins that).
    PROMPTED_ROLES: frozenset[str]

# The Kroker checkout this module ships in; a parameter so tests (and only
# tests) can point resolution at a temp repository.
_DEFAULT_SOURCE_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Provenance:
    """`kroker_commit` is a commit id or the literal ``unknown`` — never
    empty, so "could not be determined" stays distinguishable from "not
    recorded" (pre-012 records read None)."""

    kroker_commit: str
    tree_dirty: bool | None


def _git(args: list[str], cwd: str) -> CompletedProcess | None:
    """git or None: a missing binary or an unusable repository is a fall-
    through to the environment branch, never an exception (contract §2.7:
    resolution never raises)."""
    import subprocess

    try:
        # -c safe.directory=*: same dubious-ownership bypass as vcs.git._git,
        # inline so this leaf stays importable without the vcs package.
        return subprocess.run(
            ["git", "-c", "safe.directory=*", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, OSError):
        return None


def _tree_dirty_from_env() -> bool | None:
    raw = os.environ.get("KROKER_TREE_DIRTY")
    if raw is None:
        return None
    lowered = raw.strip().lower()
    if lowered in ("1", "true"):
        return True
    if lowered in ("0", "false"):
        return False
    return None


@activity.defn
async def resolve_provenance(source_root: str | None = None) -> Provenance:
    """Order (contract §2.7): git in the source root; else the
    ``KROKER_COMMIT``/``KROKER_TREE_DIRTY`` environment; else
    ``unknown`` / ``None``. Never raises."""
    root = str(Path(source_root) if source_root is not None else _DEFAULT_SOURCE_ROOT)

    head = _git(["rev-parse", "HEAD"], root)
    if head is not None and head.returncode == 0 and head.stdout.strip():
        status = _git(["status", "--porcelain"], root)
        dirty = bool(status is not None and status.returncode == 0 and status.stdout.strip())
        return Provenance(kroker_commit=head.stdout.strip(), tree_dirty=dirty)

    env_commit = os.environ.get("KROKER_COMMIT")
    if env_commit:
        return Provenance(kroker_commit=env_commit, tree_dirty=_tree_dirty_from_env())

    return Provenance(kroker_commit=UNKNOWN_COMMIT, tree_dirty=None)


# The shipped registry and the prompted-role set, built from the registry
# on FIRST ACCESS (Names §2.2: registry-derived data, never hand-
# maintained) and cached — importing this module must stay cheap, see the
# TYPE_CHECKING note above.
_REGISTRY: dict[str, RoleConfig] | None = None
_PROMPTED_ROLES: frozenset[str] | None = None


def _load_registry_cached() -> dict[str, RoleConfig]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = load_registry()
    return _REGISTRY


def __getattr__(name: str) -> object:
    # 012 orchestrator ruling: PROMPTED_ROLES is the REGISTRY-instruction
    # set (prompt_sha_for branches on registry presence — devops_planner,
    # discover, merge_verdict and risk ship prompts even though no record
    # writer uses them today), while the 10-role record-writer inventory
    # is pinned separately as the CELL_STAGE_ORDER check (T002).
    if name == "PROMPTED_ROLES":
        global _PROMPTED_ROLES
        if _PROMPTED_ROLES is None:
            _PROMPTED_ROLES = frozenset(
                role
                for role, cfg in _load_registry_cached().items()
                if cfg.instructions is not None
            )
        return _PROMPTED_ROLES
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def prompt_sha_for(role: str, model: str) -> str:
    """Contract §2.5: 64 hex characters (sha256 of the role's
    ``instructions.md``) for a prompted role on a non-deterministic model;
    ``none:deterministic`` whatever the role when the model is the literal
    ``deterministic``; ``none:no-registry-prompt`` for any other role.
    Never an empty string from a 012 writer."""
    if model == "deterministic":
        return "none:deterministic"
    cfg = _load_registry_cached().get(role)
    if cfg is None or cfg.instructions is None:
        return "none:no-registry-prompt"
    return hashlib.sha256(cfg.instructions.encode()).hexdigest()
