"""Agent registry (FR-201) + the ADR-6 anti-collusion validator (FR-204).

The registry is a versioned YAML asset (config/agents.yaml). Loading it and
running validate_registry() at worker boot is what gives the model-family
inequality invariant teeth — a same-family developer/reviewer config cannot
boot a worker.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from ..models import RoleConfig

AGENTS_CONFIG_ENV = "SDLC_AGENTS_CONFIG"
# repo_root/config/agents.yaml — loader.py is src/sdlc/agents/loader.py, so
# three parents up from the file dir is the repo root.
DEFAULT_AGENTS_CONFIG = Path(__file__).resolve().parents[3] / "config" / "agents.yaml"

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


class RegistryError(ValueError):
    """A registry that violates a structural invariant (missing role, or an
    ADR-6 same-family developer/reviewer pairing)."""


def model_family(model: str) -> str:
    """Provider/family prefix of a Pydantic AI model id. Splits on the first
    ':' or '/': 'anthropic:glm-5.2' -> 'anthropic';
    'zai-coding-plan/glm-5.2' -> 'zai-coding-plan'. Case-insensitive."""
    return re.split(r"[:/]", model, maxsplit=1)[0].strip().lower()


def _parse(path: str | os.PathLike | None = None) -> dict[str, RoleConfig]:
    """Parse the registry YAML into {role_name: RoleConfig}, UNVALIDATED.
    Resolution order: explicit arg, then $SDLC_AGENTS_CONFIG, then the shipped
    default. Private: callers must go through load_registry, which validates."""
    resolved = Path(path or os.environ.get(AGENTS_CONFIG_ENV)
                    or DEFAULT_AGENTS_CONFIG)
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    roles_raw = data.get("roles") or {}
    return {name: RoleConfig(**cfg) for name, cfg in roles_raw.items()}


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
    """agents.yaml is authoritative; PipelineConfig.roles is a purity-mandated
    mirror of its harness roles (see the note on PipelineConfig.roles). Drift
    between them is what let ADR-6 validate a role that never ran, so it fails
    the worker at boot."""
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
                f"PipelineConfig.roles['{name}'] does not mirror agents.yaml: "
                f"registry has (kind={reg.kind}, harness={reg.harness}, "
                f"model={reg.model}); PipelineConfig default has "
                f"(kind={dflt.kind}, harness={dflt.harness}, "
                f"model={dflt.model})")
