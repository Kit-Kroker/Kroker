"""The architect step's ResearchDeps (plan D7 deps tests; tasks.md T003):
the configured run ceiling and request limit must reach the architect's
research tool through the deps, while the default-config serialized payload
stays byte-identical (FR-006, FR-007, FR-010).

Everything here is a base symbol: the module collects and runs on the base
commit, where test 1 fails on behaviour (the deps carry the ResearchDeps
default 4.0 instead of the configured ceiling -- the SC-001 evidence for N2),
test 2 fails on the missing max_requests attribute, and test 3 passes (PIN)."""

from types import SimpleNamespace

import pytest

from sdlc.core.models import PipelineConfig, ResearchConfig, RoleUsage
from sdlc.stages.architecture.models import ArchitectureSpec
from sdlc.stages.architecture.step import ArchitecturePrep, produce
from sdlc.stages.clarify.models import ClarifiedRequirements

_CANNED_SPEC = ArchitectureSpec(overview="canned", decisions=[])

# The payload `architect_deps` serializes to today, measured in kroker-dev on
# the base commit (run_id is _workflow_id()'s fallback outside a Temporal
# runtime, deterministic under pytest). No max_requests key, ceiling 4.0.
# research_model is omitted while None by the deps' own serializer.
DEFAULT_DEPS_PAYLOAD = {
    "run_id": "direct-execution",
    "provider": "fake",
    "max_searches": 5,
    "max_fetches": 10,
    "max_cost_usd": 1.0,
    "memory_backend": "fake",
    "memory_base_url": "http://localhost:8888",
    "memory_bank": "project:default",
    "memory_watermark": None,
    "scope": "architect",
    "max_run_cost_usd": 4.0,
    "budget": {"searches": 0, "fetches": 0, "cost_usd": 0.0},
}


class _RecordingCtx:
    """Duck-typed StageContext: run_role records its kwargs (the deps keyword
    among them); cached_stage just awaits the closure."""

    def __init__(self):
        self.run_role_kwargs = None

    async def run_role(self, *args, **kwargs):
        self.run_role_kwargs = kwargs

        class _Result:
            output = _CANNED_SPEC

        return _Result()

    async def cached_stage(self, cfg, stage, key, output_type, fn, *, prompt_digest=""):
        return await fn(), False


def _prep() -> ArchitecturePrep:
    return ArchitecturePrep(
        started=None,
        resolved_model="claude-3-5-sonnet",
        spend=RoleUsage(role="architect", model="claude-3-5-sonnet"),
        mode_val="greenfield",
        snapshot=SimpleNamespace(items=[]),
        map_block="",
        map_key="",
        salt="digest",
    )


def _reqs() -> ClarifiedRequirements:
    return ClarifiedRequirements(
        summary="Add a greeting endpoint.",
        functional_requirements=["GET /hello returns 200"],
        non_functional_requirements=["p95 < 100ms"],
        out_of_scope=["auth"],
        open_questions=[],
    )


async def _produce_deps(cfg: PipelineConfig):
    """Drive produce down its codebase_map=None early-return path and give
    back the deps it handed the architect role."""
    ctx = _RecordingCtx()
    await produce(ctx, _prep(), cfg=cfg, requirements=_reqs(), codebase_map=None)
    return ctx.run_role_kwargs["deps"]


@pytest.mark.asyncio
async def test_architect_deps_carry_the_configured_run_ceiling():
    """Plan D7 deps test 1 (RED N2; the SC-001 evidence for N2): the ceiling
    cfg.research.max_run_cost_usd must reach the architect's ResearchDeps.
    On base architect_deps is built without the ceiling, so the deps carry
    the ResearchDeps default 4.0 and this fails on that behaviour."""
    cfg = PipelineConfig(research=ResearchConfig(max_run_cost_usd=1.5))

    deps = await _produce_deps(cfg)

    assert deps.max_run_cost_usd == 1.5


@pytest.mark.asyncio
async def test_architect_deps_carry_the_configured_request_limit_with_a_floor_of_one():
    """Plan D7 deps test 2 (RED N3): cfg.research.max_requests reaches the
    deps, clamped to a floor of 1 (ResearchConfig itself accepts 0, but a
    request limit of 0 would stop the inner run before its first request).
    On base deps has no max_requests attribute (AttributeError)."""
    cfg = PipelineConfig(research=ResearchConfig(max_requests=7))
    deps = await _produce_deps(cfg)
    assert deps.max_requests == 7

    cfg = PipelineConfig(research=ResearchConfig(max_requests=0))
    deps = await _produce_deps(cfg)
    assert deps.max_requests == 1


@pytest.mark.asyncio
async def test_default_config_deps_payload_is_unchanged(monkeypatch):
    """Plan D7 deps test 3 (PIN): with the default config the serialized deps
    equal today's payload exactly -- no max_requests key, ceiling 4.0 -- so
    default-config activity inputs stay byte-identical (FR-010). Must pass on
    the base commit and keep passing after D3, where the new field is omitted
    from serialization while it equals its default."""
    # memory_backend and memory_base_url default from SDLC_MEMORY_* env vars
    # (core/models.py), and the suite has a known .env leak channel
    # (test_prompt_gate_mutations.py loads dotenv with override=True), so pin
    # the constants, not the ambient environment (same shield as
    # test_memory_models.py).
    for var in ("SDLC_MEMORY_BACKEND", "SDLC_MEMORY_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    deps = await _produce_deps(PipelineConfig())

    assert deps.model_dump() == DEFAULT_DEPS_PAYLOAD
