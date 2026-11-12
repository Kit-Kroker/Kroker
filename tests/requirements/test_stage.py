"""draft_requirements: the requirements stage's ONLY model-call site
(FR-113, plan Task 6). The workflow stays deterministic; the activity runs
the product drafter registry agent once over a read-only workspace and hands
the RAW draft plus its usage back. freeze() (verify.py) never runs here --
ids and the digest are assigned workflow-side, never in this file.
"""

from __future__ import annotations

import re

import pytest
from pydantic_ai.models.test import TestModel

from sdlc.core.models import RoleUsage
from sdlc.stages.requirements.deps import RequirementsDeps
from sdlc.stages.requirements.models import DraftOutput
from sdlc.stages.requirements.stage import DraftInput
from sdlc.stages.requirements.stage import _draft_requirements_impl as draft_requirements

_SOURCE_REF = re.compile(r"^[A-Za-z0-9_./-]+$")

_EMPTY_DRAFT = TestModel(call_tools=[], custom_output_args={"stories": []})


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch, tmp_path):
    """The greenfield scratch dir resolves under $SDLC_RUNS_ROOT -- keep every
    test's scratch out of the checkout (the constitution suite's convention)."""
    root = tmp_path / "runs"
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(root))
    return root


def _inp(
    *,
    mode: str = "greenfield",
    repo_path: str | None = None,
    run_id: str = "r1",
    max_requests: int | None = None,
    model: str = "test-model",
) -> DraftInput:
    deps = RequirementsDeps(run_id=run_id, mode=mode)
    if max_requests is not None:
        deps = deps.model_copy(update={"max_requests": max_requests})
    return DraftInput(
        idea_json='{"goal": "ship the requirements stage"}',
        repo_path=repo_path,
        deps=deps,
        model=model,
    )


class _Recorder:
    """Stands in for the registry agent (research's _Boom pattern, recording
    instead of raising): captures the prompt and run kwargs so the 004 D7a
    forwarding branch and the prompt's mode line can be asserted without a
    real model call."""

    def __init__(self) -> None:
        self.prompt: str | None = None
        self.kwargs: dict | None = None

    async def run(self, prompt: str, **kw):
        self.prompt = prompt
        self.kwargs = kw

        class _Result:
            output = DraftOutput()

        return _Result()


@pytest.mark.asyncio
async def test_greenfield_workspace_falls_back_to_scratch(_runs_root):
    """No repo to read, but the FileSystem capability fails a workspace-less
    run AT START -- so the activity must create the run's scratch dir and
    draft the idea over an empty tree (the run succeeding at all is the
    proof a workspace was attached)."""
    out = await draft_requirements(_inp(), _model=_EMPTY_DRAFT)
    assert (_runs_root / "r1" / "requirements").is_dir()
    assert out.draft.stories == []


@pytest.mark.asyncio
async def test_brownfield_uses_repo_path_not_scratch(tmp_path, _runs_root):
    """An existing repo_path IS the workspace; the scratch dir is never
    created (greenfield-only fallback)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    out = await draft_requirements(
        _inp(mode="brownfield", repo_path=str(repo)), _model=_EMPTY_DRAFT
    )
    assert not (_runs_root / "r1").exists()
    assert out.draft.stories == []


@pytest.mark.asyncio
async def test_usage_handed_back():
    """E-33: an activity that calls a model must hand its usage back or the
    spend is silently lost. The ROLE name is the registry's ("product" --
    STAGE_ROLES reconciles 'requirements' the stage to it), cost_usd stays
    None -- dollars are priced workflow-side (replay-safe)."""
    out = await draft_requirements(_inp(), _model=_EMPTY_DRAFT)
    assert out.usage.role == "product"
    assert out.usage.model == "test-model"
    assert out.usage.calls == 1
    assert out.usage.input_tokens > 0  # TestModel reports real token counts
    assert out.usage.cost_usd is None


@pytest.mark.asyncio
async def test_source_ref_is_path_only():
    """Every source_ref the pipeline returns is a path string (or None) --
    nothing in the pipeline smuggles file CONTENTS into the draft."""
    out = await draft_requirements(
        _inp(),
        _model=TestModel(
            call_tools=[],
            custom_output_args={
                "stories": [
                    {
                        "narrative": "As a user, I want a requirements stage",
                        "functional": ["The stage drafts user stories"],
                        "success_criteria": ["A run ends with a Requirements artifact"],
                        "source_ref": "src/sdlc/stages/requirements/models.py",
                    },
                    {
                        "narrative": "As a developer, I want stories grounded in the repo",
                        "functional": ["Brownfield stories cite a repo file"],
                        "success_criteria": ["Every brownfield story has a source_ref"],
                        "source_ref": "AGENTS.md",
                    },
                ]
            },
        ),
    )
    refs = [s.source_ref for s in out.draft.stories]
    assert len(refs) == 2
    for ref in refs:
        assert ref is None or _SOURCE_REF.match(ref), f"source_ref is not path-only: {ref!r}"


@pytest.mark.asyncio
async def test_max_requests_bound():
    """A TestModel whose output fails validation forces a second request; the
    request_limit stops the run BEFORE it. UsageLimitExceeded degrades to an
    EMPTY draft -- never a raise (a retry hits the same exhausted bound and
    burns attempts for a guaranteed failure) -- and the completed first
    request's spend still comes back."""
    always_invalid = TestModel(
        call_tools=[],
        # functional/success_criteria missing: DraftStory validation fails,
        # so every attempt re-prompts -- exactly what request_limit=1 stops.
        custom_output_args={"stories": [{"narrative": "As a user, I want a thing"}]},
    )
    out = await draft_requirements(_inp(max_requests=1), _model=always_invalid)
    assert out.draft.stories == []
    assert out.usage.input_tokens > 0  # the first request's spend survives the abort
    assert out.usage.calls == 1
    assert out.usage.role == "product"


@pytest.mark.asyncio
async def test_zero_request_bound_reports_zero_spend():
    """max_requests=0 stops the run before its first request: the degrade
    reports a zero-spend RoleUsage (calls=0), so pricing never charges a
    call that made no request."""
    out = await draft_requirements(_inp(max_requests=0), _model=_EMPTY_DRAFT)
    assert out.draft.stories == []
    assert out.usage == RoleUsage(role="product", model="test-model")


@pytest.mark.asyncio
async def test_brownfield_mode_without_repo_never_prompts_for_source_refs(tmp_path):
    """The prompt's mode line derives from the RESOLVED WORKSPACE, not
    deps.mode: a brownfield mode over a missing repo_path must not instruct
    the model to cite files it cannot read (hallucinated refs pass the
    path-only shape)."""
    rec = _Recorder()
    # Non-directory repo_path: same as missing -- the scratch branch runs.
    await draft_requirements(_inp(mode="brownfield", repo_path=str(tmp_path / "nope")), _agent=rec)
    assert "Mode: greenfield" in (rec.prompt or "")
    assert "repo-relative file path" not in (rec.prompt or "")

    # Positive control: the same brownfield mode WITH an existing repo dir
    # keeps the repo-grounded instruction.
    repo = tmp_path / "repo"
    repo.mkdir()
    await draft_requirements(_inp(mode="brownfield", repo_path=str(repo)), _agent=rec)
    assert "Mode: brownfield" in (rec.prompt or "")
    assert "repo-relative file path" in (rec.prompt or "")


@pytest.mark.asyncio
async def test_model_forwarded_only_when_it_differs_from_the_registry_model():
    """004 D7a: `model=` is forwarded only on an override -- an equal model
    omits the kwarg entirely, so no-override calls are byte-identical (E1)."""
    from sdlc.agents.roles import REGISTRY

    registry_model = REGISTRY["product"].model
    assert registry_model is not None

    rec = _Recorder()
    await draft_requirements(_inp(model=registry_model), _agent=rec)
    assert "model" not in (rec.kwargs or {}), "equal model must not be forwarded"

    await draft_requirements(_inp(model="run-override"), _agent=rec)
    assert (rec.kwargs or {}).get("model") == "run-override"
