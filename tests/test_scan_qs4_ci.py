"""QS4's computed half: what the pipeline does, and which environments the
repository declares on each side. ci_present is triage's baseline, inherited
and folded in by the workflow (D2/D7)."""
from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_CI_PRESENT, C_CI_STAGES, C_ENV_DRIFT, TestLevel,
)
from sdlc.assessment.scan.signals import ci
from sdlc.measurement import CollectionState

WORKFLOW = """
name: ci
on: [push]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: ruff check .
  test:
    runs-on: ubuntu-latest
    steps:
      - run: pytest -q
  e2e:
    runs-on: ubuntu-latest
    steps:
      - run: npx playwright test
  deploy:
    environment: production
    steps:
      - run: ./deploy.sh
"""

PATHS = [".github/workflows/ci.yml", ".env.production", ".env.staging",
         "src/app.py"]
BLOBS = {".github/workflows/ci.yml": WORKFLOW}


def test_every_job_becomes_a_stage_in_file_order():
    out = ci.evaluate(PATHS, BLOBS)
    assert [s.stage for s in out.ci] == ["lint", "test", "e2e", "deploy"]
    assert [s.order for s in out.ci] == [0, 1, 2, 3]


def test_a_job_that_runs_tests_declares_the_level_it_runs():
    out = ci.evaluate(PATHS, BLOBS)
    by_stage = {s.stage: s for s in out.ci}
    assert by_stage["test"].runs_tests is True
    assert by_stage["test"].test_levels == [TestLevel.UNIT]
    assert by_stage["e2e"].test_levels == [TestLevel.E2E]
    assert by_stage["lint"].runs_tests is False
    assert by_stage["lint"].test_levels == []


def test_a_deploy_job_names_its_environment():
    out = ci.evaluate(PATHS, BLOBS)
    deploy = next(s for s in out.ci if s.stage == "deploy")
    assert deploy.deploys_to == "production"


def test_blocking_is_not_collected_on_every_stage():
    """A required check is a branch-protection setting, not a tracked file."""
    out = ci.evaluate(PATHS, BLOBS)
    assert all(s.blocking.state is CollectionState.NOT_COLLECTED
               for s in out.ci)


def test_drift_is_computed_between_ci_and_config():
    """P3-D7: staging has a config file and no CI deploy job; production has
    both."""
    out = ci.evaluate(PATHS, BLOBS)
    by_name = {e.name: e for e in out.environments}
    assert by_name["production"].in_ci is True
    assert by_name["production"].in_config is True
    assert by_name["production"].drifted is False
    assert by_name["staging"].in_ci is False
    assert by_name["staging"].in_config is True
    assert by_name["staging"].drifted is True
    assert out.row.categories[C_ENV_DRIFT].value == 1.0


def test_drift_needs_a_ci_file_to_compare_against():
    """P3-D11: with no CI side there is nothing to compare, and E-56's
    declared scope is what would answer it instead."""
    out = ci.evaluate([".env.staging"], {})
    category = out.row.categories[C_ENV_DRIFT]
    assert category.state is CollectionState.NOT_COLLECTED
    assert "E-56" in category.reason


def test_an_unparseable_workflow_does_not_pass_a_partial_stage_list_as_complete():
    """A refused CI file may carry stages we cannot see, so measured(N) from
    the parseable files would assert an incomplete count as the whole -- the
    FR-915 conflation. The category names the refused file; env_drift is a
    gap for the same reason (the CI side is unreadable)."""
    blobs = {".github/workflows/ci.yml": WORKFLOW,
             ".github/workflows/broken.yml": "jobs: [unbalanced\n"}
    out = ci.evaluate(PATHS + [".github/workflows/broken.yml"], blobs)
    assert out.row.categories[C_CI_STAGES].state is CollectionState.NOT_COLLECTED
    assert "broken.yml" in out.row.categories[C_CI_STAGES].reason
    assert out.row.categories[C_ENV_DRIFT].state is CollectionState.NOT_COLLECTED
    assert out.ci == []
    assert out.environments == []


def test_a_yaml_bomb_is_refused_rather_than_expanded():
    """P3-D8: safe_load does not execute code, but anchors still expand, and
    CI files come from an untrusted repository (NFR-9)."""
    bomb = "a: &a [x,x,x,x,x,x,x,x,x]\n" + "".join(
        f"{chr(98 + i)}: &{chr(98 + i)} ["
        + ",".join([f"*{chr(97 + i)}"] * 9) + "]\n"
        for i in range(8))
    # 72 alias references, over MAX_ALIASES. Asserted on the guard itself:
    # the evaluate() assertion below would also pass if the document merely
    # parsed to something with no jobs, which is not what this test is about.
    assert ci._safe_yaml(bomb) is None
    out = ci.evaluate([".github/workflows/bomb.yml"],
                      {".github/workflows/bomb.yml": bomb})
    assert out.ci == []
    assert out.row.categories[C_CI_STAGES].state is CollectionState.NOT_COLLECTED


def test_a_gitlab_pipeline_is_parsed_too():
    blobs = {".gitlab-ci.yml": (
        "stages: [build, test]\n"
        "unit:\n"
        "  stage: test\n"
        "  script:\n"
        "    - pytest -q\n")}
    out = ci.evaluate([".gitlab-ci.yml"], blobs)
    assert [s.stage for s in out.ci] == ["unit"]
    assert out.ci[0].runs_tests is True


def test_the_inherited_category_is_declared_as_pending():
    out = ci.evaluate(PATHS, BLOBS)
    pending = out.row.categories[C_CI_PRESENT]
    assert pending.state is CollectionState.NOT_COLLECTED
    assert "D7" in pending.reason
