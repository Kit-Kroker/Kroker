"""Pure helpers for the CLI --role-model override (E-37, US-4). Kept out of
cli.py so the parse/validate/build logic is unit-testable without argparse."""

from __future__ import annotations

from .agents.loader import (
    HARNESS_ROLES,
    KNOWN_ROLES,
    load_registry,
    validate_run_roles,
)
from .core.models import (
    HarnessKind,
    RoleConfig,
)
from .crew.loader import preflight_crew


def parse_role_models(pairs: list[str]) -> dict[str, str]:
    """Parse ['role=model', ...] into {role: model}. Raises ValueError on a
    missing '=' or an unknown role name."""
    out: dict[str, str] = {}
    for p in pairs:
        if "=" not in p:
            raise ValueError(f"--role-model expects role=model, got {p!r}")
        role, model = p.split("=", 1)
        role, model = role.strip(), model.strip()
        if role not in KNOWN_ROLES:
            raise ValueError(f"unknown role {role!r}; known roles: {sorted(KNOWN_ROLES)}")
        if not model:
            raise ValueError(f"--role-model {role!r} has an empty model")
        out[role] = model
    return out


def build_role_overrides(overrides: dict[str, str]) -> dict[str, RoleConfig]:
    """Validate ADR-6 for the registry-resolved role→model map with these
    overrides applied, then build cfg.roles entries. Harness roles keep the
    registry's default harness; other roles are kind='proposer'."""
    reg = load_registry()
    resolved = {r: rc.model for r, rc in reg.items() if rc.model is not None}
    resolved.update(overrides)
    validate_run_roles(resolved)  # raises RegistryError on ADR-6 breach
    roles: dict[str, RoleConfig] = {}
    for role, model in overrides.items():
        if role in HARNESS_ROLES:
            roles[role] = RoleConfig(harness=reg[role].harness, model=model)
        else:
            roles[role] = RoleConfig(kind="proposer", model=model)
    # E-88 §5: a crew's roles enter the same decorrelation rule. The dev
    # role's harness decides whether there is a crew at all; the layout name
    # comes from the registry entry, defaulting to the shipped one.
    dev = roles.get("dev") or reg.get("dev")
    if dev is not None and dev.harness is HarnessKind.CREW:
        preflight_crew(dev.layout or "code", dev.lead_harness, dev.model)
    return roles
