"""E-33: token->USD pricing. Verified against genai-prices' bundled tables —
offline, deterministic, no network."""

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
