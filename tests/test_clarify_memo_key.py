"""The clarify memo key must move when the fan-out's inputs move, and must
NOT move when the flag is off.

Without the first, editing a probe -- or retuning the cap -- serves a stale
clarification silently. Without the second, landing E-85 invalidates every
existing clarify memo even though the flag-off prompt did not change, which is
what "the default pipeline is byte-identical to today" rules out.

The unit under test is `_clarify_memo_extra`, the workflow's own helper, NOT
`content_key`. Asserting on hand-built key strings would pass unchanged if the
stage stopped appending the extra altogether; asserting on the helper the
stage actually calls is what makes the constraint executable. The content_key
tests at the bottom pin the one remaining thing the helper cannot: that a
non-empty extra really does move a key, i.e. that the term is load-bearing.
"""

from __future__ import annotations

import ast

import pytest
from test_factory_purity import FEATURE_PY, _load_class, _methods

from sdlc.assessment.scan.models import Confidence
from sdlc.clarify.prompts import probe_prompt_digest
from sdlc.context.models import CodebaseMap, MapModule
from sdlc.core.models import (
    PipelineConfig,
)
from sdlc.measurement import Measurement
from sdlc.memoization.cache import content_key
from sdlc.workflows.feature import _clarify_memo_extra


def _map(name: str = "cap001", tree: str = "t1") -> CodebaseMap:
    ok = Measurement.measured(1.0)
    return CodebaseMap(
        tree_hash=tree,
        commit_sha="c" * 40,
        modules=(MapModule(name=name, member_paths=("src/a.py",), confidence=Confidence.LOW),),
        modules_collected=ok,
        contracts_collected=ok,
        hot_spots_collected=ok,
        collected=ok,
    )


def _cfg(**kw) -> PipelineConfig:
    return PipelineConfig(clarify_probes_enabled=True, **kw)


# ---- flag off: nothing is appended, at all ----------------------------


@pytest.mark.parametrize("cmap", [None, _map()])
def test_the_flag_off_extra_is_empty_with_or_without_a_tree(cmap):
    """The binding guarantee. An empty string concatenates to the identity,
    so a flag-off run keys exactly as it did pre-E-85 and every memo written
    before E-85 landed still hits."""
    assert _clarify_memo_extra(PipelineConfig(), cmap) == ""


def test_the_default_config_is_flag_off():
    # If this ever flips, the assertion above stops meaning anything.
    assert PipelineConfig().clarify_probes_enabled is False


# ---- flag on: every input that changes the answer moves the key -------


def test_turning_the_flag_on_appends_the_probe_digest():
    extra = _clarify_memo_extra(_cfg(), _map())
    assert extra != ""
    assert probe_prompt_digest() in extra


def test_a_different_tree_moves_the_extra():
    assert _clarify_memo_extra(_cfg(), _map(name="cap001")) != _clarify_memo_extra(
        _cfg(), _map(name="cap999")
    )


def test_the_same_tree_and_prompts_hit_the_same_extra():
    assert _clarify_memo_extra(_cfg(), _map()) == _clarify_memo_extra(_cfg(), _map())


def test_a_different_cap_moves_the_extra():
    """Spec section 10 names the cap as the first knob the benchmark tunes.
    The cap decides which questions reach a human and which land on
    `dropped`, so a memo made under cap=3 is not the cap=8 artifact."""
    assert _clarify_memo_extra(_cfg(clarify_question_cap=3), _map()) != _clarify_memo_extra(
        _cfg(clarify_question_cap=8), _map()
    )


def test_greenfield_has_no_tree_but_still_keys_stably():
    """codebase_map is None for a greenfield run. The term must be a stable
    sentinel, not a crash and not an empty string that would collide with
    the flag-off key."""
    greenfield = _clarify_memo_extra(_cfg(), None)
    assert greenfield == _clarify_memo_extra(_cfg(), None)
    assert greenfield != ""
    assert greenfield != _clarify_memo_extra(_cfg(), _map())


# ---- the extra is load-bearing in the key it feeds --------------------


def _key(extra: str) -> str:
    return content_key(
        "clarify", '{"title": "x"}' + extra, "prompt-sha", "anthropic:glm-5.2", "none"
    )


def test_the_flag_off_key_equals_the_pre_e85_key():
    assert _key(_clarify_memo_extra(PipelineConfig(), _map())) == _key("")


def test_the_flag_on_key_differs_from_the_pre_e85_key():
    assert _key(_clarify_memo_extra(_cfg(), _map())) != _key("")


# ---- the stage actually USES the helper -------------------------------
# Everything above tests _clarify_memo_extra in isolation, which leaves one
# gap wide open: delete `+ _clarify_key_extra` from the stage's
# _cached_stage call and every assertion above still passes. Nothing else in
# the suite inspects that call. An AST assertion on the pipeline body closes
# it -- the same technique tests/test_memoization_wiring.py uses to pin the
# other _cached_stage invariants without booting Temporal.


@pytest.fixture(scope="module")
def pipeline_src() -> str:
    tree = ast.parse(FEATURE_PY.read_text(encoding="utf-8"), filename=str(FEATURE_PY))
    return ast.unparse(_methods(_load_class(tree, "FeatureWorkflow"))["_pipeline"])


def _clarify_cached_stage_call() -> ast.Call:
    """The `self._cached_stage(cfg, 'clarify', ...)` call in _pipeline."""
    tree = ast.parse(FEATURE_PY.read_text(encoding="utf-8"), filename=str(FEATURE_PY))
    body = _methods(_load_class(tree, "FeatureWorkflow"))["_pipeline"]
    for node in ast.walk(body):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_cached_stage"
            and len(node.args) >= 3
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "clarify"
        ):
            return node
    pytest.fail("no self._cached_stage(cfg, 'clarify', ...) call in _pipeline")


def test_the_clarify_stage_appends_the_extra_to_its_memo_input():
    """The load-bearing wiring assertion. Without the extra in the key, a
    probe-prompt edit, a changed tree or a retuned cap all serve a stale
    clarification with no error."""
    key_arg = ast.unparse(_clarify_cached_stage_call().args[2])
    assert "_clarify_key_extra" in key_arg, (
        "the clarify stage's memo input dropped the E-85 extra; probe "
        "edits, tree changes and cap changes would all serve stale memos"
    )


def test_the_clarify_memo_input_still_carries_its_pre_e85_terms():
    # The extra is APPENDED. If it ever replaced the base terms, flag-off
    # byte-identity would be gone.
    key_arg = ast.unparse(_clarify_cached_stage_call().args[2])
    assert "idea.model_dump_json()" in key_arg
    assert "brief_digest_val" in key_arg


def test_the_extra_comes_from_the_helper_these_tests_pin(pipeline_src):
    assert "_clarify_memo_extra(cfg, self._codebase_map)" in pipeline_src
