"""Token->USD pricing (E-33). Activity-only by design: dollars drive the
budget gate, so the conversion must be replay-deterministic — the lookup
runs in an activity whose result lands in Temporal history, never inline
in workflow code (a genai-prices data update must not change replayed
math under an open workflow)."""
from __future__ import annotations

from pydantic import BaseModel
from temporalio import activity


class PriceUsageInput(BaseModel):
    model: str                      # registry form: "anthropic:claude-opus-4-8"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def compute_price(inp: PriceUsageInput) -> float | None:
    """Pure lookup. None = unknown model/provider — NEVER raises: a missing
    price must not fail a stage; the tokens still record (spec §3).

    The registry's model strings carry a routing provider ("anthropic:" for
    an anthropic-compatible endpoint), which may not be the pricing
    provider — so a hinted miss retries unhinted (glm via zhipuai)."""
    import genai_prices

    usage = genai_prices.Usage(
        input_tokens=inp.input_tokens,
        output_tokens=inp.output_tokens,
        cache_read_tokens=inp.cache_read_tokens,
        cache_write_tokens=inp.cache_write_tokens)
    provider: str | None = None
    ref = inp.model
    for sep in (":", "/"):
        if sep in ref:
            provider, ref = ref.split(sep, 1)
            break
    for prov in dict.fromkeys((provider, None)):   # hinted, then unhinted
        try:
            calc = genai_prices.calc_price(usage, model_ref=ref,
                                           provider_id=prov)
            return float(calc.total_price)
        except Exception:
            continue
    return None


@activity.defn
async def price_usage(inp: PriceUsageInput) -> float | None:
    return compute_price(inp)
