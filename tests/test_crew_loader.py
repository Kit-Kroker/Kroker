# tests/test_crew_loader.py
"""E-88 §5: a broken crew must kill the worker at startup, not forty minutes
and one billed agent into a run. Every check here has a failure it prevents."""
from __future__ import annotations

import pytest
import yaml

from sdlc.crew.loader import CrewConfigError, load_layout

LAYOUT = {
    "layout": "code", "lead": "coder", "crew": ["coder"],
    "rounds": {"max": 1},
    "deliverable": {"path": "notes.md", "schema": "notes-v1"},
    "limits": {"wall_clock_s": 3000, "turn_timeout_s": 1800,
               "cost_usd": 25.0},
}
ROLE = {"harness": "opencode", "model": "zai-coding-plan/glm-5.3",
        "writes": True, "skill": "coder"}


def _tree(root, layout=None, roles=None, skills=("coder",)):
    (root / "layouts").mkdir(parents=True, exist_ok=True)
    (root / "roles").mkdir(parents=True, exist_ok=True)
    (root / "layouts" / "code.yaml").write_text(
        yaml.safe_dump(layout or LAYOUT), encoding="utf-8")
    for name, body in (roles or {"coder": ROLE}).items():
        (root / "roles" / f"{name}.yaml").write_text(
            yaml.safe_dump(body), encoding="utf-8")
    for s in skills:
        d = root / "skills" / s
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text("# skill", encoding="utf-8")
    return root


def test_loads_a_valid_tree(tmp_path):
    root = _tree(tmp_path / "crew")
    layout, roles = load_layout("code", root=root)
    assert layout.lead == "coder"
    assert roles["coder"].model == "zai-coding-plan/glm-5.3"


def test_rejects_a_crew_with_no_writer(tmp_path):
    """Nobody would touch the repository and the diff would always be empty."""
    root = _tree(tmp_path / "crew", roles={"coder": {**ROLE, "writes": False}})
    with pytest.raises(CrewConfigError, match="exactly one"):
        load_layout("code", root=root)


def test_rejects_two_writers(tmp_path):
    """Two writers make the diff unattributable (spec §1)."""
    layout = {**LAYOUT, "crew": ["coder", "second"]}
    root = _tree(tmp_path / "crew", layout=layout,
                 roles={"coder": ROLE, "second": {**ROLE, "skill": "second"}},
                 skills=("coder", "second"))
    with pytest.raises(CrewConfigError, match="exactly one"):
        load_layout("code", root=root)


def test_rejects_a_role_naming_crew_as_its_own_harness(tmp_path):
    """`crew` is a composition mode, not a CLI: a role selecting it would
    recurse and has no subprocess to build."""
    root = _tree(tmp_path / "crew", roles={"coder": {**ROLE,
                                                     "harness": "crew"}})
    with pytest.raises(CrewConfigError, match="not a CLI"):
        load_layout("code", root=root)


def test_rejects_a_missing_skill_file(tmp_path):
    root = _tree(tmp_path / "crew", skills=())
    with pytest.raises(CrewConfigError, match="SKILL.md"):
        load_layout("code", root=root)


def test_rejects_a_deliverable_escaping_the_round_directory(tmp_path):
    layout = {**LAYOUT,
              "deliverable": {"path": "../../../etc/passwd",
                              "schema": "notes-v1"}}
    root = _tree(tmp_path / "crew", layout=layout)
    with pytest.raises(CrewConfigError, match="round directory"):
        load_layout("code", root=root)


def test_rejects_a_role_the_layout_never_defines(tmp_path):
    layout = {**LAYOUT, "crew": ["coder", "ghost"]}
    root = _tree(tmp_path / "crew", layout=layout)
    with pytest.raises(CrewConfigError, match="ghost"):
        load_layout("code", root=root)


def test_rejects_a_model_with_no_provider_separator(tmp_path):
    """model_family() splits on the first ':' or '/'; a string with neither
    IS its own family, so ADR-6's comparison silently compares a model to
    itself. The separator is what makes the crew's decorrelation check mean
    anything, so it is required here rather than assumed."""
    role = dict(ROLE, model="glm-5.3")
    root = _tree(tmp_path, roles={"coder": role})
    with pytest.raises(CrewConfigError, match="provider"):
        load_layout("code", root)


def test_crew_cli_check_names_the_role_and_the_missing_binary(tmp_path,
                                                              monkeypatch):
    """spec §5 friction 1: pointing a role at a CLI this image does not carry
    fails at RUNTIME today, after the other roles have already spent. The
    worker must die at startup instead, naming which role is wrong."""
    from sdlc.crew import loader as crew_loader
    root = _tree(tmp_path)
    monkeypatch.setattr(crew_loader.shutil, "which", lambda _: None)
    with pytest.raises(CrewConfigError) as e:
        crew_loader.validate_crew_clis(root)
    assert "coder" in str(e.value)
    assert "opencode" in str(e.value)


def test_crew_cli_check_passes_when_every_binary_is_present(tmp_path,
                                                            monkeypatch):
    from sdlc.crew import loader as crew_loader
    root = _tree(tmp_path)
    monkeypatch.setattr(crew_loader.shutil, "which", lambda n: f"/usr/bin/{n}")
    crew_loader.validate_crew_clis(root)


def test_crew_cli_check_is_a_noop_without_a_crew_tree(tmp_path):
    """A source checkout running the unit suite carries no crew assets, and
    that is not a defect -- the same reasoning CrewAssetsMissing exists for."""
    from sdlc.crew import loader as crew_loader
    crew_loader.validate_crew_clis(tmp_path / "nothing-here")


