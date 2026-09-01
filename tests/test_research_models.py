from sdlc.models import (
    ConsultedSource,
    GroundedFinding,
    InferredFinding,
    MemoryKind,
    PipelineConfig,
    ResearchBrief,
    ResearchConfig,
    RoleConfig,
)

# The SGR cascade, in the ONE order the spec commits to. This literal IS the
# design (spec §4); a reorder is a silent regression, so it gets a guard.
_BRIEF_ORDER = [
    "sub_questions",
    "sources_consulted",
    "grounded_findings",
    "inferred_findings",
    "contradictions",
    "gaps",
    "summary",
    "brief_ref",
    "confidence",
]


def test_research_brief_field_order_is_the_sgr_cascade():
    assert list(ResearchBrief.model_fields) == _BRIEF_ORDER


def test_grounded_finding_puts_quote_before_claim():
    """Quote-first forces commitment to a span in context, THEN a statement of
    what it supports — the ordering that makes manufactured citations less
    likely (spec §4)."""
    order = list(GroundedFinding.model_fields)
    assert order.index("quote") < order.index("claim")
    assert order[0] == "source_url"


def test_inferred_finding_puts_reasoning_before_claim():
    order = list(InferredFinding.model_fields)
    assert order.index("reasoning") < order.index("claim")


def test_consulted_source_puts_assessment_before_relevance_label():
    order = list(ConsultedSource.model_fields)
    assert order.index("assessment") < order.index("relevance")


def test_research_brief_is_constructible_empty_but_typed():
    brief = ResearchBrief(summary="", confidence=0.0)
    assert brief.grounded_findings == []
    assert brief.brief_ref is None


def test_memory_kind_has_research_finding():
    assert MemoryKind.RESEARCH_FINDING.value == "research_finding"


def test_role_config_accepts_kind_research_and_provider():
    rc = RoleConfig(kind="research", model="anthropic:glm-5.2", provider="fake")
    assert rc.kind == "research"
    assert rc.provider == "fake"


def test_pipeline_config_research_defaults_off_and_bounded():
    cfg = PipelineConfig()
    assert cfg.research_enabled is False
    assert isinstance(cfg.research, ResearchConfig)
    assert cfg.research.max_searches == 5
    assert cfg.research.max_fetches == 10
    assert cfg.research.max_cost_usd == 1.0
    assert cfg.research.max_requests == 40
