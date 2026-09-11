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
