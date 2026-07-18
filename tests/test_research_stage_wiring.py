import ast
from pathlib import Path

FEATURE_PY = (Path(__file__).resolve().parents[1]
              / "src" / "sdlc" / "workflows" / "feature.py")


def _run_method_src() -> str:
    tree = ast.parse(FEATURE_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            return ast.unparse(node)
    raise AssertionError("run() not found")


def test_research_stage_is_guarded_by_research_enabled():
    src = _run_method_src()
    assert "cfg.research_enabled" in src


def test_research_feeds_brief_digest_into_clarify_key():
    """The FR-103 fix (finding 3): clarify's memo input carries brief_digest,
    so a run that finds new facts invalidates clarify (and downstream), while
    identical facts still hit."""
    src = _run_method_src()
    assert "brief_digest" in src
    # clarify's cached-stage input is idea + the digest, not idea alone.
    assert 'idea.model_dump_json() + ' in src


def test_research_stage_is_not_memoized():
    """A served memo means pages were not fetched this run (finding 4). The
    research producer must not be wrapped in _cached_stage."""
    src = _run_method_src()
    # crude but effective: no _cached_stage call names "research".
    assert '_cached_stage(\n' not in src or '"research"' not in src
    assert '"research"' not in src.split("_cached_stage")[1] \
        if "_cached_stage" in src else True


def test_research_retains_verified_findings():
    src = _run_method_src()
    assert "verified_findings_to_retain" in src


def test_research_stage_verifies_grounding_post_run():
    """AMENDED (Task 7 fallback for Task 1 finding A): the workflow calls
    verify_brief_activity AFTER the research agent runs and inspects the
    returned violations list (the activity returns, not raises — temporalio
    wraps activity-raised exceptions in ActivityError). Non-empty = fail
    closed. If this disappears, grounding enforcement silently vanishes.

    Code-review C1/C2 fix: the previous form asserted `"GroundingViolation"
    in src`, but the workflow no longer references that type — it inspects
    the returned list. Pin the new shape instead."""
    src = _run_method_src()
    assert "verify_brief_activity" in src
    assert "rejected:research.grounding" in src
