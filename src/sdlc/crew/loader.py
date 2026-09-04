"""Boot-time validation of the crew/ asset tree (E-88 §5).

Mirrors src/sdlc/agents/loader.py deliberately: a broken crew must kill the
worker at startup, not forty minutes into a run. Every check here has a
failure it prevents, named in its message.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from ..agents.loader import model_family
from ..core.models import (
    HarnessKind,
)
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


def validate_crew(layout: CrewLayout, roles: dict[str, CrewRole], root: Path) -> None:
    missing = [n for n in layout.roles() if n not in roles]
    if missing:
        raise CrewConfigError(
            f"layout {layout.layout!r} names undefined role(s): {', '.join(missing)}"
        )

    writers = [n for n in layout.roles() if roles[n].writes]
    if len(writers) != 1:
        raise CrewConfigError(
            f"layout {layout.layout!r} must have exactly one role with "
            f"writes: true (the lead); found {writers or 'none'}"
        )
    if writers[0] != layout.lead:
        raise CrewConfigError(
            f"layout {layout.layout!r}: the writing role is {writers[0]!r} "
            f"but the lead is {layout.lead!r}"
        )

    for name in layout.roles():
        role = roles[name]
        if role.harness is HarnessKind.CREW:
            raise CrewConfigError(
                f"role {name!r} declares harness 'crew', which is a "
                f"composition mode and not a CLI: there is no subprocess to "
                f"build for it"
            )
        if not any(sep in role.model for sep in (":", "/")):
            raise CrewConfigError(
                f"role {name!r} model {role.model!r} names no provider: "
                f"model_family() splits on the first ':' or '/', so a string "
                f"with neither is its own family and ADR-6 would compare this "
                f"role to itself. Write the model in its CLI's own syntax, "
                f"e.g. 'anthropic:claude-opus-5' or "
                f"'zai-coding-plan/glm-5.3'"
            )
        skill = root / "skills" / role.skill / "SKILL.md"
        if not skill.is_file():
            raise CrewConfigError(
                f"role {name!r} names skill {role.skill!r} but {skill} does not exist"
            )

    # Round-relative, and it must STAY in the round directory: a path that
    # escapes is rejected rather than sanitised, per the untrusted-input rule.
    rel = Path(layout.deliverable.path)
    if rel.is_absolute() or ".." in rel.parts:
        raise CrewConfigError(
            f"layout {layout.layout!r}: deliverable {layout.deliverable.path!r}"
            f" must resolve inside the round directory"
        )


def check_crew_families(lead: str, roles: list[CrewRole]) -> None:
    """ADR-6 over a crew (spec §5, finding 5).

    Pure: no I/O, so the activity path and the client-side pre-flight run
    the identical rule and cannot drift. The rule is the factory's own --
    model FAMILY inequality, not string inequality, because two models from
    one provider are a correlated second opinion whatever they are called.

    Writing roles are exempt from being compared to each other because a
    layout has exactly one (validate_crew enforces that); every other role
    is a second opinion and must decorrelate from the lead.
    """
    by_name = {r.name: r for r in roles}
    if lead not in by_name:
        raise CrewConfigError(
            f"crew lead {lead!r} is not among the resolved roles {sorted(by_name)}"
        )
    lead_family = model_family(by_name[lead].model)
    for role in roles:
        if role.name == lead or role.writes:
            continue
        if model_family(role.model) == lead_family:
            raise CrewConfigError(
                f"ADR-6 violation: crew role {role.name!r} model "
                f"{role.model!r} shares model family {lead_family!r} with the "
                f"lead {lead!r} ({by_name[lead].model!r}) -- a second opinion "
                f"from the same weights is not a second opinion"
            )


def read_skill(skill: str, root: Path | None = None) -> str:
    """The skill text that IS the round protocol, rendered into the round
    brief (E-88 step 1). Resolves the tree exactly like load_layout, so the
    delivered text cannot come from anywhere the boot validation missed."""
    root = root or crew_dir()
    if root is None:
        raise CrewAssetsMissing("no crew/ directory found from the cwd upward")
    path = root / "skills" / skill / "SKILL.md"
    if not path.is_file():
        raise CrewConfigError(f"skill {skill!r} has no SKILL.md at {path}")
    return path.read_text(encoding="utf-8")


def load_layout(name: str, root: Path | None = None) -> tuple[CrewLayout, dict[str, CrewRole]]:
    root = root or crew_dir()
    if root is None:
        raise CrewAssetsMissing("no crew/ directory found from the cwd upward")
    layout = CrewLayout(**_read(root / "layouts" / f"{name}.yaml"))
    roles: dict[str, CrewRole] = {}
    for role_name in layout.roles():
        path = root / "roles" / f"{role_name}.yaml"
        if not path.is_file():
            raise CrewConfigError(
                f"layout {name!r} names role {role_name!r} but {path} does not exist"
            )
        roles[role_name] = CrewRole(name=role_name, **_read(path))
    validate_crew(layout, roles, root)
    return layout, roles


def resolve_crew_roles(
    layout: CrewLayout,
    roles: dict[str, CrewRole],
    lead_harness: HarnessKind | None,
    lead_model: str | None,
) -> list[CrewRole]:
    """Apply the run's overrides to the LEAD only (spec §5).

    Non-lead roles keep both halves from their own file, so a benchmark cell
    varies exactly one thing at a time.
    """
    if lead_harness is HarnessKind.CREW:
        raise ValueError("lead_harness 'crew' is a composition mode and not a CLI")
    out: list[CrewRole] = []
    for name in layout.roles():
        role = roles[name]
        if name != layout.lead:
            out.append(role)
            continue
        harness = lead_harness or role.harness
        if lead_harness is not None and lead_harness is not role.harness and not lead_model:
            raise ValueError(
                f"lead_harness {lead_harness.value!r} differs from role "
                f"{name!r}'s {role.harness.value!r}, but no model was given: "
                f"model strings are pass-through in each CLI's own syntax, so "
                f"reusing {role.model!r} would fail at runtime"
            )
        out.append(role.model_copy(update={"harness": harness, "model": lead_model or role.model}))
    return out


def validate_crew_clis(root: Path | None = None) -> None:
    """Every role in every shipped layout has its CLI on PATH (spec §5
    friction 1).

    Boot-time, not load-time: a source checkout running the unit suite has no
    reason to carry a coding CLI, so this is called from worker.py's main()
    rather than from load_layout.

    The honest limit: this proves the BINARY exists, not that it is logged in
    to the provider the role's model names. Auth cannot be checked offline,
    and a check that pretended to would be worse than none. What it does
    catch is the concrete failure the spec names -- a role pointing at a CLI
    this image does not carry.
    """
    root = root or crew_dir()
    if root is None or not (root / "layouts").is_dir():
        return  # no crew assets here; not a defect
    from ..harness.registry import HARNESSES

    missing: list[str] = []
    for path in sorted((root / "layouts").glob("*.yaml")):
        layout, roles = load_layout(path.stem, root)
        for name in layout.roles():
            cli = HARNESSES[roles[name].harness].cli
            if shutil.which(cli) is None:
                missing.append(
                    f"layout {layout.layout!r} role {name!r} needs "
                    f"{roles[name].harness.value!r}, whose CLI {cli!r} is not "
                    f"on PATH"
                )
    if missing:
        raise CrewConfigError(
            "crew roles name CLIs this environment does not carry, so the "
            "run would fail after other roles had already spent:\n  " + "\n  ".join(missing)
        )


def preflight_crew(layout: str, lead_harness: HarnessKind | None, lead_model: str | None) -> None:
    """Run the crew's ADR-6 check client-side, before the run starts.

    The same pure rule load_crew applies -- one implementation, so the two
    cannot become two policies that hold only while they agree. This site is
    the early warning; load_crew remains the guarantee, because it is the one
    that always sees the run's effective values and can never be bypassed.

    Silent when there is no crew tree, and silent when the layout does not
    exist: a non-crew run must not be blocked by crew assets it never asked
    for. A crew run with a broken tree still dies at load_crew.
    """
    try:
        cfg_layout, roles = load_layout(layout)
        resolved = resolve_crew_roles(cfg_layout, roles, lead_harness, lead_model)
    except CrewAssetsMissing:
        return
    check_crew_families(cfg_layout.lead, resolved)
