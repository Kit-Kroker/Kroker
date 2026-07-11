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


class RegistryError(ValueError):
    """A registry that violates a structural invariant (missing role, or an
    ADR-6 same-family developer/reviewer pairing)."""


def model_family(model: str) -> str:
    """Provider/family prefix of a Pydantic AI model id. Splits on the first
    ':' or '/': 'anthropic:glm-5.2' -> 'anthropic';
    'zai-coding-plan/glm-5.2' -> 'zai-coding-plan'. Case-insensitive."""
    return re.split(r"[:/]", model, maxsplit=1)[0].strip().lower()


def load_registry(path: str | os.PathLike | None = None) -> dict[str, RoleConfig]:
    """Parse the registry YAML into {role_name: RoleConfig}. Resolution order:
    explicit arg, then $SDLC_AGENTS_CONFIG, then the shipped default."""
    resolved = Path(path or os.environ.get(AGENTS_CONFIG_ENV)
                    or DEFAULT_AGENTS_CONFIG)
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    roles_raw = data.get("roles") or {}
    return {name: RoleConfig(**cfg) for name, cfg in roles_raw.items()}


def validate_registry(roles: dict[str, RoleConfig]) -> None:
    """Fail closed on any structural violation. The ADR-6 invariant is
    model-family inequality (NOT harness inequality); the harness clause only
    applies to the optional deep-review harness reviewer tier."""
    dev = roles.get("developer")
    rev = roles.get("reviewer")
    if dev is None or rev is None:
        raise RegistryError(
            "registry must define both developer and reviewer roles")
    if dev.model is None or rev.model is None:
        raise RegistryError("developer and reviewer roles must declare a model")
    if model_family(dev.model) == model_family(rev.model):
        raise RegistryError(
            f"ADR-6 violation: reviewer family '{model_family(rev.model)}' "
            f"equals developer family — anti-collusion review requires a "
            f"different model family than the developer's authoring model")
    if rev.kind == "harness" and rev.harness is not None \
            and rev.harness == dev.harness:
        raise RegistryError(
            "deep-review harness reviewer must use a different harness than "
            "the developer")
