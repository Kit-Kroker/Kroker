"""The maintainer registry role contracts (023a T009, RED).

Authorship note: BOTH QA seats were quota-blocked when this task came up
(2026-11-14 21:45, resets 23:50), so this file is executor-written under the
orchestration protocol's degradation ruling ("proceed where the plan already
answers"): every assertion below is a transcription of T009's task text and
research.md R8, not a new decision. The reviewer still gates the diff.

Subject: the optional ``maintainer`` proposer (T010 implements
``agents/maintainer/`` plus wiring in ``sdlc.agents.roles`` and
``sdlc.agents.loader``). Nothing exists yet — that is the RED. The module
imports resolve, so each test fails on its own missing attribute rather
than one collection error.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sdlc.agents import loader, roles
from sdlc.maintenance.models import RepairProposal
from tests.conftest import write_registry_dir


def test_t_maintainer_ships_and_is_not_none() -> None:
    t_maintainer = roles.t_maintainer
    assert t_maintainer is not None


def test_t_maintainer_is_in_all_temporal_agents() -> None:
    assert roles.t_maintainer in roles.ALL_TEMPORAL_AGENTS


def test_maintainer_output_type_is_repair_proposal() -> None:
    # The proposal IS the plan's evidence: the agent is pinned to the
    # schema, so an off-schema answer is a failed call, not prose.
    assert roles.t_maintainer.output_type is RepairProposal


def test_registry_entry_is_a_proposer_with_model_and_instructions() -> None:
    cfg = loader.load_registry()["maintainer"]
    assert cfg.kind == "proposer"
    assert cfg.model is not None
    assert cfg.instructions


def test_output_retries_covers_maintainer() -> None:
    assert isinstance(roles.OUTPUT_RETRIES.get("maintainer"), int)


def test_maintainer_is_a_known_optional_role() -> None:
    assert "maintainer" in loader.OPTIONAL_ROLES
    assert "maintainer" in loader.KNOWN_ROLES


def test_agent_yaml_declares_kind_proposer() -> None:
    import yaml

    data = yaml.safe_load((Path("agents/maintainer/agent.yaml")).read_text())
    assert data["kind"] == "proposer"


def test_adr6_judge_set_is_unchanged_and_excludes_maintainer() -> None:
    # R8: the maintainer judges no one's output, so ADR-6's judge set is
    # exactly what it was. Pin the tuple; a maintainer here would mean the
    # role was wired as a judge by mistake.
    assert loader.JUDGE_ROLES == ("reviewer", "deep_review", "qa", "merge_verdict")


def test_registry_without_the_maintainer_folder_still_loads() -> None:
    # Optional role: absence is legal (the loop degrades to no proposer).
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = write_registry_dir(Path(td))
        m = root / "maintainer"
        if m.exists():
            shutil.rmtree(m)
        parsed = loader.load_registry(root)  # type: ignore[arg-type]
    assert "maintainer" not in parsed
    assert "planner" in parsed


# =========================================================================== #
# ## post-hoc QA audit (qa-chaos, 2026-11-15)
#
# Gaps found against T009's brief: the brief demanded a tmp-registry test
# WITH the maintainer folder present ("load_registry returns it with
# instructions loaded") — only the absence case had been written — and the
# STAGE_ROLES/STAGE_MODELS keyset sanity assertion.
# =========================================================================== #


def test_a_tmp_registry_with_the_maintainer_folder_loads_it_with_instructions() -> None:
    # The mirror of the absence case: the production folder dropped into a
    # tmp registry must load as a proposer with its instructions attached.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = write_registry_dir(Path(td))
        # The harness registry already materialises a maintainer slot (T010
        # grew write_registry_dir); overwrite it with the production files.
        shutil.copytree(Path("agents/maintainer"), root / "maintainer", dirs_exist_ok=True)
        parsed = loader.load_registry(root)  # type: ignore[arg-type]
    cfg = parsed["maintainer"]
    assert cfg.kind == "proposer"
    assert cfg.model is not None
    assert cfg.instructions


def test_stage_roles_and_stage_models_keysets_stay_identical() -> None:
    # Wiring sanity the T009 brief asked for alongside the new role; mirrors
    # tests/test_stage_models.py so a maintainer wiring mistake cannot hide
    # behind that file alone.
    assert set(roles.STAGE_ROLES) == set(roles.STAGE_MODELS)
    assert roles.STAGE_ROLES.get("maintenance") == "maintainer"
