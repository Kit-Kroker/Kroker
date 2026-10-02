"""E-33: token->USD pricing. Verified against genai-prices' bundled tables —
offline, deterministic, no network."""

import pytest

from sdlc.pricing import PriceUsageInput, compute_price, price_usage


def test_known_anthropic_model_prices_positive():
    usd = compute_price(
        PriceUsageInput(model="anthropic:claude-opus-4-8", input_tokens=1000, output_tokens=100)
    )
    assert usd is not None and usd > 0


def test_provider_hint_falls_back_unhinted():
    # The registry routes glm through an anthropic-compatible endpoint;
    # genai-prices knows the model only under its real provider. The
    # unhinted retry must find it.
    usd = compute_price(
        PriceUsageInput(model="anthropic:glm-5.2", input_tokens=1000, output_tokens=100)
    )
    assert usd is not None and usd > 0


def test_slash_form_model_string_parses():
    usd = compute_price(
        PriceUsageInput(model="zai-coding-plan/glm-5.2", input_tokens=1000, output_tokens=100)
    )
    assert usd is not None and usd > 0


def test_unknown_model_returns_none_never_raises():
    assert compute_price(PriceUsageInput(model="totally-unknown-xyz", input_tokens=10)) is None


def test_price_usage_is_a_temporal_activity():
    assert getattr(price_usage, "__temporal_activity_definition", None) is not None


# --- 005 US3: the route change re-prices the registry proposers (FR-008) ----
#
# Pins of the genai-prices data behind compute_price (research.md R10,
# genai-prices 0.1.9 per uv.lock): the registry's proposers move from
# `anthropic:glm-5.2` (hinted miss under anthropic, unhinted retry finds the
# zhipuai row) to `zai:glm-5.3` (provider hint HITS the zai row). These are
# GREEN on arrival — a red here is a real pricing-path defect: report it,
# do not work around it. Rates are USD per 1M tokens.

_ZHIPUAI_FALLBACK = (1.103, 3.862)


def _per_1m_rates(model: str) -> tuple[float, float]:
    """(input, output) USD per 1M tokens as compute_price sees them."""
    usd_in = compute_price(PriceUsageInput(model=model, input_tokens=1_000_000))
    usd_out = compute_price(PriceUsageInput(model=model, output_tokens=1_000_000))
    assert usd_in is not None, f"{model}: priced as unknown (None) — pricing-path defect"
    assert usd_out is not None, f"{model}: priced as unknown (None) — pricing-path defect"
    return usd_in, usd_out


def test_zai_glm_5_3_prices_on_the_native_zai_row():
    """US3/FR-008: the new registry proposers price on the native zai row,
    via the provider hint (R10) — not the zhipuai fallback."""
    usd_in, usd_out = _per_1m_rates("zai:glm-5.3")
    assert usd_in == pytest.approx(1.400, abs=1e-9)
    assert usd_out == pytest.approx(4.400, abs=1e-9)


def test_anthropic_glm_5_2_still_prices_on_the_zhipuai_fallback_row():
    """The old registry string keeps its fallback pricing: harness strings
    and the rollback override still price through the unhinted zhipuai row
    (R10)."""
    usd_in, usd_out = _per_1m_rates("anthropic:glm-5.2")
    assert usd_in == pytest.approx(_ZHIPUAI_FALLBACK[0], abs=1e-9)
    assert usd_out == pytest.approx(_ZHIPUAI_FALLBACK[1], abs=1e-9)


def test_slash_form_zai_coding_plan_still_falls_back_to_zhipuai():
    """The harness-grammar slash form has no row of its own; the unhinted
    retry still lands on zhipuai (R10)."""
    usd_in, usd_out = _per_1m_rates("zai-coding-plan/glm-5.2")
    assert usd_in == pytest.approx(_ZHIPUAI_FALLBACK[0], abs=1e-9)
    assert usd_out == pytest.approx(_ZHIPUAI_FALLBACK[1], abs=1e-9)
