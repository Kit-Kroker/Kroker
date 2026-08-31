"""Boot-time validation of the crew/ asset tree (E-88 §5).

Mirrors src/sdlc/agents/loader.py deliberately: a broken crew must kill the
worker at startup, not forty minutes into a run. Every check here has a
failure it prevents, named in its message.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..models import HarnessKind
from .config import CrewLayout, CrewRole


class CrewConfigError(ValueError):
    """A crew role or layout is unusable. Raised at boot."""


class CrewAssetsMissing(CrewConfigError):
    """There is no crew/ tree here at all.

    Its own class because it is the one crew failure that is not a defect: a
    source checkout running the unit suite has no reason to carry crew
    assets. Every OTHER config failure means the assets exist and are wrong.
    """


def crew_dir() -> Path | None:
    for parent in [Path.cwd(), *Path.cwd().parents]:
        cand = parent / "crew"
        if (cand / "layouts").is_dir():
            return cand
    return None


def _read(path: Path) -> dict:
    if not path.is_file():
        raise CrewAssetsMissing(f"crew asset not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CrewConfigError(f"{path} must contain a YAML mapping")
    return data


def validate_crew(layout: CrewLayout, roles: dict[str, CrewRole],
                  root: Path) -> None:
    missing = [n for n in layout.roles() if n not in roles]
    if missing:
        raise CrewConfigError(
            f"layout {layout.layout!r} names undefined role(s): "
            f"{', '.join(missing)}")

    writers = [n for n in layout.roles() if roles[n].writes]
    if len(writers) != 1:
        raise CrewConfigError(
            f"layout {layout.layout!r} must have exactly one role with "
            f"writes: true (the lead); found {writers or 'none'}")
    if writers[0] != layout.lead:
        raise CrewConfigError(
            f"layout {layout.layout!r}: the writing role is {writers[0]!r} "
            f"but the lead is {layout.lead!r}")

    for name in layout.roles():
        role = roles[name]
        if role.harness is HarnessKind.CREW:
            raise CrewConfigError(
                f"role {name!r} declares harness 'crew', which is a "
                f"composition mode and not a CLI: there is no subprocess to "
                f"build for it")
        skill = root / "skills" / role.skill / "SKILL.md"
        if not skill.is_file():
            raise CrewConfigError(
                f"role {name!r} names skill {role.skill!r} but "
                f"{skill} does not exist")

    # Round-relative, and it must STAY in the round directory: a path that
    # escapes is rejected rather than sanitised, per the untrusted-input rule.
    rel = Path(layout.deliverable.path)
    if rel.is_absolute() or ".." in rel.parts:
        raise CrewConfigError(
            f"layout {layout.layout!r}: deliverable {layout.deliverable.path!r}"
            f" must resolve inside the round directory")


def load_layout(name: str,
                root: Path | None = None) -> tuple[CrewLayout, dict[str, CrewRole]]:
    root = root or crew_dir()
    if root is None:
        raise CrewAssetsMissing("no crew/ directory found from the cwd upward")
    layout = CrewLayout(**_read(root / "layouts" / f"{name}.yaml"))
    roles: dict[str, CrewRole] = {}
    for role_name in layout.roles():
        path = root / "roles" / f"{role_name}.yaml"
        if not path.is_file():
            raise CrewConfigError(
                f"layout {name!r} names role {role_name!r} but {path} "
                f"does not exist")
        roles[role_name] = CrewRole(name=role_name, **_read(path))
    validate_crew(layout, roles, root)
    return layout, roles


def resolve_crew_roles(layout: CrewLayout, roles: dict[str, CrewRole],
                       lead_harness: HarnessKind | None,
                       lead_model: str | None) -> list[CrewRole]:
    """Apply the run's overrides to the LEAD only (spec §5).

    Non-lead roles keep both halves from their own file, so a benchmark cell
    varies exactly one thing at a time.
    """
    if lead_harness is HarnessKind.CREW:
        raise ValueError(
            "lead_harness 'crew' is a composition mode and not a CLI")
    out: list[CrewRole] = []
    for name in layout.roles():
        role = roles[name]
        if name != layout.lead:
            out.append(role)
            continue
        harness = lead_harness or role.harness
        if lead_harness is not None and lead_harness is not role.harness \
                and not lead_model:
            raise ValueError(
                f"lead_harness {lead_harness.value!r} differs from role "
                f"{name!r}'s {role.harness.value!r}, but no model was given: "
                f"model strings are pass-through in each CLI's own syntax, so "
                f"reusing {role.model!r} would fail at runtime")
        out.append(role.model_copy(update={
            "harness": harness, "model": lead_model or role.model}))
    return out
