import inspect

from sdlc.stages import clarify, research
from sdlc.workflows import feature


def _pipeline_src() -> str:
    return inspect.getsource(feature.FeatureWorkflow._pipeline)


def _step_src() -> str:
    return inspect.getsource(research.step)


def test_research_stage_is_guarded_by_research_enabled():
    src = _pipeline_src()
    assert "cfg.research_enabled" in src
    assert "research.step" in src


def test_research_feeds_brief_digest_into_clarify_key():
    """The FR-103 fix (finding 3): clarify's memo input carries brief_digest,
    so a run that finds new facts invalidates clarify (and downstream), while
    identical facts still hit."""
    src = _pipeline_src()
    assert "brief_digest" in src
    # clarify's cached-stage input is idea + the digest, not idea alone. The
    # key assembly lives in the clarify slice since Task 13 (spec A).
    step = inspect.getsource(clarify.step)
    assert "idea.model_dump_json() + " in step


def test_research_stage_is_not_memoized():
    """A served memo means pages were not fetched this run (finding 4). The
    research producer must not be wrapped in _cached_stage."""
    src = _pipeline_src()
    # crude but effective: no _cached_stage call names "research".
    assert not any('"research"' in args.split(")")[0] for args in src.split("_cached_stage(")[1:])
    assert "_cached_stage" not in _step_src()


def test_research_retains_verified_findings():
    src = _step_src()
    assert "verified_findings_to_retain" in src


def test_research_stage_verifies_grounding_post_run():
    """AMENDED (Task 7 fallback for Task 1 finding A): the workflow calls
    verify_brief_activity AFTER the research agent runs and inspects the
    returned violations list (the activity returns, not raises — temporalio
    wraps activity-raised exceptions in ActivityError). Non-empty = fail
    closed. If this disappears, grounding enforcement silently vanishes."""
    src = _step_src()
    assert "verify_brief_activity" in src
    assert "rejected:research.grounding" in src


def test_research_stage_degrades_on_model_call_failure():
    """Spec §8 tier 1: a plan/synthesize model-call failure (ActivityError
    after its retries exhaust) must degrade the STAGE to a
    _degraded_research_brief, never crash the FeatureWorkflow
    (bench-todo-api-greenfield-1785485669: an uncaught UsageLimitExceeded
    once killed the whole run, not just research). The fan-out + synthesis
    sit inside a broad try/except that substitutes the degraded brief;
    sub-question failures degrade individually inside the activity."""
    src = _step_src()
    assert "_fan_out_research" in src
    assert "except Exception as exc:" in src
    assert "_degraded_research_brief(exc)" in src
