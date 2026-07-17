"""Agent registry (FR-201) + the ADR-6 anti-collusion validator (FR-204).

The registry is a directory of role folders (agents/<role>/), one per role,
where the directory name IS the role name. Loading it and running
validate_registry() at worker boot is what gives the model-family inequality
invariant teeth — a same-family dev/reviewer config cannot boot a worker.

Resolution deliberately contains no __file__: the registry's location has no
relationship to where this package is installed. Under `pip install .` the
package lands in site-packages, which is why the old
parents[3]/config/agents.yaml walk resolved to a path that never existed in
the image. Order: explicit arg -> $SDLC_AGENTS_DIR -> repo-root discovery.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from ..models import RoleConfig

AGENTS_DIR_ENV = "SDLC_AGENTS_DIR"
# Renamed from SDLC_AGENTS_CONFIG: the value's meaning changed from a single
# YAML file to a directory. Accepting the old name silently would let a stale
# value resolve a file where a directory is expected and fail somewhere less
# obvious than boot.
LEGACY_AGENTS_ENV = "SDLC_AGENTS_CONFIG"

# Marker files that identify a repo checkout. Two, not one: `pyproject.toml`
# alone matches any Python project we happen to be cwd'd into.
_ROOT_MARKERS = ("pyproject.toml", "agents/registry.yaml")

# Harness-execution roles. Keys fixed by DevTask.role
# (Literal["dev","test","devops"], models.py:144). PipelineConfig.roles
# mirrors exactly this set — see _validate_pipeline_mirror.
HARNESS_ROLES = frozenset({"dev", "test", "devops"})

# Proposer roles, one per agent in agents/roles.py. 'devops_planner' PLANS
# devops tasks; the 'devops' harness role above RUNS them.
PROPOSER_ROLES = frozenset({
    "clarify", "architect", "planner", "qa", "reviewer", "analyst",
    "merge_verdict", "devops_planner",
})

REQUIRED_ROLES = HARNESS_ROLES | PROPOSER_ROLES

# Roles the pipeline can run WITHOUT, but which are still known directories.
# Empty today, named deliberately: a fail-closed unknown-directory check would
# otherwise reject an optional role's folder outright, forcing the next spec to
# weaken this check instead of extending it. The research role is its first
# entry (2026-07-17-research-agent-grounded-briefs-design.md).
OPTIONAL_ROLES: frozenset[str] = frozenset()

# REQUIRED_ROLES gates PRESENCE (a missing one fails boot).
# KNOWN_ROLES gates RECOGNITION (an unknown directory fails boot).
KNOWN_ROLES = REQUIRED_ROLES | OPTIONAL_ROLES


class RegistryError(ValueError):
    """A registry that violates a structural invariant (missing role, or an
    ADR-6 same-family developer/reviewer pairing)."""


def model_family(model: str) -> str:
    """Provider/family prefix of a Pydantic AI model id. Splits on the first
    ':' or '/': 'anthropic:glm-5.2' -> 'anthropic';
    'zai-coding-plan/glm-5.2' -> 'zai-coding-plan'. Case-insensitive."""
    return re.split(r"[:/]", model, maxsplit=1)[0].strip().lower()


def _discover_agents_dir() -> Path | None:
    """Walk up from cwd for a checkout containing BOTH marker files. Dev and
    tests only — production sets $SDLC_AGENTS_DIR explicitly."""
    for d in (Path.cwd(), *Path.cwd().parents):
        if all((d / m).is_file() for m in _ROOT_MARKERS):
            return d / "agents"
    return None


def _resolve_agents_dir(path: str | os.PathLike | None = None) -> Path:
    if os.environ.get(LEGACY_AGENTS_ENV):
        raise RegistryError(
            f"{LEGACY_AGENTS_ENV} was renamed to {AGENTS_DIR_ENV} and now names "
            f"a DIRECTORY (the registry is agents/<role>/, not one YAML file). "
            f"Unset {LEGACY_AGENTS_ENV} and set {AGENTS_DIR_ENV}.")
    if path is not None:
        return Path(path)
    env = os.environ.get(AGENTS_DIR_ENV)
    if env:
        return Path(env)
    found = _discover_agents_dir()
    if found is not None:
        return found
    raise RegistryError(
        f"cannot locate the agents registry. Tried: an explicit path argument; "
        f"${AGENTS_DIR_ENV}; and walking up from {Path.cwd()} for a directory "
        f"containing both pyproject.toml and agents/registry.yaml.")


def _parse(path: str | os.PathLike | None = None) -> dict[str, RoleConfig]:
    """Walk the registry directory into {role_name: RoleConfig}, UNVALIDATED.
    Private: callers go through load_registry, which validates."""
    root = _resolve_agents_dir(path)
    if not root.is_dir():
        raise RegistryError(f"agents registry is not a directory: {root}")

    reg = root / "registry.yaml"
    if not reg.is_file():
        raise RegistryError(
            f"missing {reg}: every registry declares its version")
    version = (yaml.safe_load(reg.read_text(encoding="utf-8")) or {}).get("version")
    if version != 1:
        raise RegistryError(
            f"unsupported registry version {version!r} in {reg}; expected 1")

    roles: dict[str, RoleConfig] = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        roles[d.name] = _parse_role(d.name, d)
    return roles


def _parse_role(name: str, d: Path) -> RoleConfig:
    if name not in KNOWN_ROLES:
        raise RegistryError(
            f"unknown role directory '{name}' in {d.parent}: the directory name "
            f"is the role name, so this is a typo, not an extension point. "
            f"Known roles: {', '.join(sorted(KNOWN_ROLES))}")
    f = d / "agent.yaml"
    if not f.is_file():
        raise RegistryError(f"role '{name}': missing {f}")
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    declared = data.pop("role", None)
    if declared is not None and declared != name:
        raise RegistryError(
            f"role directory '{name}' contains an agent.yaml declaring role "
            f"'{declared}': the filename is the API and must agree with its "
            f"contents")
    cfg = RoleConfig(**data)
    instructions_file = d / "instructions.md"
    needs_prompt = cfg.kind != "harness"
    if needs_prompt:
        if not instructions_file.is_file():
            raise RegistryError(f"role '{name}': missing {instructions_file}")
        # read_text applies universal newlines, so a CRLF checkout still
        # hashes as LF (tests/test_prompt_migration.py pins this).
        text = instructions_file.read_text(encoding="utf-8")
        if not text.strip():
            raise RegistryError(
                f"role '{name}': {instructions_file} is empty — an empty system "
                f"prompt is a boot-time bug, not a runtime surprise")
        cfg = cfg.model_copy(update={"instructions": text})
    elif instructions_file.exists():
        raise RegistryError(
            f"role '{name}' is kind=harness and carries {instructions_file}, "
            f"which would never be read: silent dead config")
    return cfg


def load_registry(path: str | os.PathLike | None = None) -> dict[str, RoleConfig]:
    """Parse AND validate. No unvalidated registry escapes this module, so
    roles.py's import-time call fails with a RegistryError explaining the
    problem rather than a KeyError from whichever role it indexed first."""
    roles = _parse(path)
    validate_registry(roles)
    return roles


def validate_registry(roles: dict[str, RoleConfig]) -> None:
    """Fail closed on any structural violation.

    Checks run in this order deliberately: a missing role is reported as
    itself, before any downstream check trips over its absence.

    The ADR-6 invariant is model-family inequality between the reviewer and
    'dev' — the role feature.py:434 resolves to actually write code. (It is
    NOT harness inequality; that clause applies only to the optional
    deep-review harness reviewer tier.)
    """
    missing = sorted(REQUIRED_ROLES - set(roles))
    if missing:
        raise RegistryError(
            f"registry is missing required role(s): {', '.join(missing)}")
    for name in ("dev", "reviewer"):
        if roles[name].model is None:
            raise RegistryError(f"role '{name}' must declare a model")
    dev, rev = roles["dev"], roles["reviewer"]
    if model_family(dev.model) == model_family(rev.model):
        raise RegistryError(
            f"ADR-6 violation: reviewer family '{model_family(rev.model)}' "
            f"equals the family of 'dev' — anti-collusion review requires a "
            f"different model family than the developer's authoring model")
    if rev.kind == "harness" and rev.harness is not None \
            and rev.harness == dev.harness:
        raise RegistryError(
            "deep-review harness reviewer must use a different harness than "
            "the developer")
    _validate_pipeline_mirror(roles)


def _validate_pipeline_mirror(roles: dict[str, RoleConfig]) -> None:
    """the agents/ registry is authoritative; PipelineConfig.roles is a
    purity-mandated mirror of its harness roles (see the note on
    PipelineConfig.roles). Drift between them is what let ADR-6 validate a role
    that never ran, so it fails the worker at boot."""
    from ..models import PipelineConfig      # local: avoid an import cycle at
                                             # module scope via models -> ...
    default_roles = PipelineConfig().roles
    if set(default_roles) != HARNESS_ROLES:
        raise RegistryError(
            f"PipelineConfig.roles must mirror exactly the harness roles "
            f"{sorted(HARNESS_ROLES)}; it has {sorted(default_roles)}")
    for name in sorted(HARNESS_ROLES):
        reg, dflt = roles[name], default_roles[name]
        if (reg.kind, reg.harness, reg.model) != \
                (dflt.kind, dflt.harness, dflt.model):
            raise RegistryError(
                f"PipelineConfig.roles['{name}'] does not mirror the agents/ "
                f"registry: "
                f"registry has (kind={reg.kind}, harness={reg.harness}, "
                f"model={reg.model}); PipelineConfig default has "
                f"(kind={dflt.kind}, harness={dflt.harness}, "
                f"model={dflt.model})")
