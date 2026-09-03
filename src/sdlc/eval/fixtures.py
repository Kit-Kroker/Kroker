"""Fixtures for the prompt eval loop: a proposer's frozen input, CONSTRUCTED
from a golden case rather than captured from a run's history.

Construction beats capture because production and the generator call the same
builder (``sdlc.prompts``), so a fixture cannot silently drift from what the
pipeline actually sends -- divergence becomes a code change. The old
Temporal-history capture path (``fixtures_from_events`` / ``run_capture``)
was retired with E-82; it never ran against a live history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ..core.models import (
    IdeaBrief,
    ProjectMode,
)
from ..prompts import clarify_prompt, planner_prompt, qa_prompt

# The six pure prompt-in/artifact-out proposers.
SUPPORTED_ROLES: frozenset[str] = frozenset(
    {"clarify", "planner", "qa", "reviewer", "analyst", "merge_verdict"}
)

# architect + research pass deps to .run(); a prompt-string fixture cannot
# reconstruct a live deps object, so they are refused.
DEPS_ROLES: frozenset[str] = frozenset({"architect", "research"})


class FixtureError(Exception):
    """A fixture could not be built (unknown case/role, missing seed)."""


class EvalFixture(BaseModel):
    role: str
    case: str
    prompt: str
    model: str
    source_run_id: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def _load_case(case_id: str, cases_root: Path) -> dict:
    p = cases_root / case_id / "case.yaml"
    if not p.is_file():
        raise FixtureError(f"no case.yaml at {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _role_model(role: str, agents_dir: Path) -> str:
    p = agents_dir / role / "agent.yaml"
    if not p.is_file():
        raise FixtureError(f"no agent.yaml at {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    model = data.get("model")
    if not model:
        raise FixtureError(f"no model declared in {p}")
    return model


def _idea_brief(spec: dict) -> IdeaBrief:
    """Mirrors BenchmarkWorkflow's construction (workflow.py:157-158) so a
    fixture's idea is identical to a benchmark cell's."""
    return IdeaBrief(
        title=spec["case_id"],
        description=spec["description"],
        mode=ProjectMode(spec.get("mode", "greenfield")),
        repo_url=spec.get("repo_url"),
    )


def _read_seed(case_id: str, cases_root: Path, name: str) -> str:
    p = cases_root / case_id / "seeds" / name
    if not p.is_file():
        raise FixtureError(
            f"role needs a frozen seed at {p}. Author it (see the E-82 design "
            f"doc section 4.2 for the per-role seed contents) before "
            f"evaluating this (role, case) pair."
        )
    return p.read_text(encoding="utf-8")


def _seeded_prompt(role: str, case_id: str, cases_root: Path) -> str:
    """Downstream roles need an upstream artifact that case.yaml cannot
    supply. Re-deriving it would rebuild the pipeline, so it is committed
    frozen under benchmarks/cases/<case>/seeds/."""
    import json

    if role == "planner":
        arch = json.loads(_read_seed(case_id, cases_root, "architecture.json"))
        return planner_prompt(json.dumps(arch, separators=(",", ":")), [], None)
    if role == "qa":
        assertions = json.loads(_read_seed(case_id, cases_root, "assertions.json"))["assertions"]
        qa_raw = _read_seed(case_id, cases_root, "qa_raw.json").strip()
        diff = json.loads(_read_seed(case_id, cases_root, "diff.json"))
        return qa_prompt(assertions, qa_raw, diff["stat"], diff["patch"])
    raise FixtureError(
        f"role '{role}' has no seed recipe; add one alongside planner/qa in "
        f"_seeded_prompt (the E-82 design doc section 4.2 lists the contents)"
    )


def validate_role(role: str) -> None:
    """Refuse a role the eval loop cannot handle.

    Called by run_gate BEFORE any git or filesystem work: an unknown role
    would otherwise surface as a raw FileNotFoundError from
    `git show HEAD:agents/<role>/instructions.md` rather than a clean,
    actionable message.
    """
    if role in DEPS_ROLES:
        raise FixtureError(
            f"role '{role}' carries deps; a prompt-string fixture cannot "
            f"reconstruct a live deps object"
        )
    if role not in SUPPORTED_ROLES:
        raise FixtureError(
            f"unknown role '{role}'; supported: {', '.join(sorted(SUPPORTED_ROLES))}"
        )


def build_fixture(role: str, case_id: str, cases_root: Path, agents_dir: Path) -> EvalFixture:
    """Construct a role's frozen input from a golden case, deterministically.

    Memory items are empty by construction: a fixture must not depend on a
    live memory backend, and an empty snapshot is what an unattended cell
    sees anyway.
    """
    validate_role(role)
    spec = _load_case(case_id, cases_root)
    model = _role_model(role, agents_dir)

    if role == "clarify":
        prompt = clarify_prompt(_idea_brief(spec).model_dump_json(), [])
    else:
        prompt = _seeded_prompt(role, case_id, cases_root)

    return EvalFixture(role=role, case=case_id, prompt=prompt, model=model, source_run_id="_built")


def write_fixtures(fixtures: list[EvalFixture], agents_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for fx in fixtures:
        d = agents_dir / fx.role / "fixtures"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{fx.case}.json"
        p.write_text(fx.model_dump_json(indent=2), encoding="utf-8")
        paths.append(p)
    return paths


def load_fixture(path: Path) -> EvalFixture:
    return EvalFixture.model_validate_json(path.read_text(encoding="utf-8"))
