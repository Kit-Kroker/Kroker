"""Read the role registry as plain YAML for the generated registry page.

Deliberately does NOT import src/sdlc/agents/loader.py: the loader drags
the runtime dependency set into the docs build, and the product/harness
boundary forbids product runtime machinery as dev tooling (spec §3.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class RoleRow:
    name: str
    kind: str | None
    harness: str | None
    model: str | None
    has_instructions: bool


@dataclass(frozen=True)
class CrewRow:
    name: str
    harness: str | None
    model: str | None
    writes: bool


class RegistryGap(Exception):
    def __init__(self, role: str) -> None:
        super().__init__(f"role dir agents/{role} has no agent.yaml")
        self.role = role


def read_roles(agents_dir: Path) -> list[RoleRow]:
    rows: list[RoleRow] = []
    for d in sorted(p for p in agents_dir.iterdir() if p.is_dir()):
        yml = d / "agent.yaml"
        if not yml.is_file():
            raise RegistryGap(d.name)
        data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
        rows.append(
            RoleRow(
                name=d.name,
                kind=data.get("kind"),
                harness=data.get("harness"),
                model=data.get("model"),
                has_instructions=(d / "instructions.md").is_file(),
            )
        )
    return rows


def read_crew(roles_dir: Path) -> list[CrewRow]:
    rows: list[CrewRow] = []
    for yml in sorted(roles_dir.glob("*.yaml")):
        data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
        rows.append(
            CrewRow(
                name=yml.stem,
                harness=data.get("harness"),
                model=data.get("model"),
                writes=bool(data.get("writes")),
            )
        )
    return rows


REGISTRY_PAGE = "generated/agent-registry.md"


def _cell(v: str | None) -> str:
    return v if v else "—"


def render_registry(roles: list[RoleRow], crew: list[CrewRow]) -> str:
    lines = [
        "# Agent registry",
        "",
        f"{len(roles)} roles under `agents/`, read as plain YAML from"
        " `agents/<role>/agent.yaml`. `instructions.md` presence is reported,"
        " not its content (product prompts stay off the site).",
        "",
        "| Role | Kind | Harness | Model | instructions.md |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in roles:
        lines.append(
            f"| {r.name} | {_cell(r.kind)} | {_cell(r.harness)} "
            f"| {_cell(r.model)} | {'yes' if r.has_instructions else 'no'} |"
        )
    lines += [
        "",
        "## Crew roles (E-88)",
        "",
        "Crew roles live in `crew/roles/*.yaml`, not in `agents/registry.yaml`"
        " (ARCHITECTURE §4: one writer; ADR-6 family rule for non-lead roles).",
        "",
        "| Role | Harness | Model | Writes |",
        "| --- | --- | --- | --- |",
    ]
    for c in crew:
        lines.append(
            f"| {c.name} | {_cell(c.harness)} | {_cell(c.model)} | {'yes' if c.writes else 'no'} |"
        )
    lines.append("")
    return "\n".join(lines)
