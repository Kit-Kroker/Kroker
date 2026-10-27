"""Tests for exponential backoff delay policy and error classification in the single-retry seam.

Covering:
- Pure functions for transient error classification and retry delay calculation.
- Ladder (5s, 30s, 120s) with upward-only jitter [0, 0.2] capped at 120s.
- Retry-After parsing (delta-seconds, HTTP-date) and cap (fail-fast if > 120s).
- Attempt count bound: exactly 3 retries (4 calls total) on 429/5xx before exhaustion.
- Fail-fast on other 4xx (400, 401, 403, 404, etc.) without retrying.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sdlc.agents.retry_policy import (
    DEFAULT_CAP,
    DEFAULT_LADDER,
    extract_status_and_retry_after,
    is_transient,
    parse_retry_after,
    retry_delay,
)


class TestConstants:
    """Characterization pins for default policy constants."""

    def test_default_constants(self) -> None:
        assert DEFAULT_LADDER == (5.0, 30.0, 120.0)
        assert DEFAULT_CAP == 120.0


class TestErrorClassification:
    """Classification of provider errors into transient vs fail-fast."""

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_transient_http_statuses(self, status: int) -> None:
        assert is_transient(status, timed_out=False) is True

    def test_read_or_connect_timeout_is_transient(self) -> None:
        assert is_transient(None, timed_out=True) is True
        assert is_transient(500, timed_out=True) is True

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
    def test_non_transient_4xx_fail_fast(self, status: int) -> None:
        assert is_transient(status, timed_out=False) is False

    @pytest.mark.parametrize("status", [501, 505])
    def test_non_transient_5xx_fail_fast(self, status: int) -> None:
        assert is_transient(status, timed_out=False) is False

    def test_unknown_or_none_without_timeout_is_not_transient(self) -> None:
        assert is_transient(None, timed_out=False) is False
        assert is_transient(200, timed_out=False) is False


class TestParseRetryAfter:
    """Parsing Retry-After header values (seconds or HTTP-date)."""

    def test_parse_integer_seconds(self) -> None:
        assert parse_retry_after("45") == 45.0
        assert parse_retry_after("0") == 0.0
        assert parse_retry_after(60) == 60.0
        assert parse_retry_after(12.5) == 12.5

    def test_negative_seconds_returns_none(self) -> None:
        assert parse_retry_after("-5") is None
        assert parse_retry_after(-1) is None

    def test_none_or_empty_returns_none(self) -> None:
        assert parse_retry_after(None) is None
        assert parse_retry_after("") is None
        assert parse_retry_after("   ") is None

    def test_invalid_string_returns_none(self) -> None:
        assert parse_retry_after("not-a-number-or-date") is None

    def test_parse_http_date_rfc_9110(self) -> None:
        ref_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
        header_date = "Mon, 26 Oct 2026 12:00:30 GMT"
        parsed = parse_retry_after(header_date, now=ref_time)
        assert parsed == 30.0

    def test_parse_past_http_date_returns_zero(self) -> None:
        ref_time = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
        header_date = "Mon, 26 Oct 2026 11:59:30 GMT"
        parsed = parse_retry_after(header_date, now=ref_time)
        assert parsed == 0.0


class TestRetryDelay:
    """Nominal ladder, upward jitter, Retry-After precedence and cap."""

    def test_nominal_ladder_zero_jitter(self) -> None:
        """Attempt index 0, 1, 2 map to 5s, 30s, 120s with zero jitter."""
        assert retry_delay(0, jitter_ratio=0.0) == 5.0
        assert retry_delay(1, jitter_ratio=0.0) == 30.0
        assert retry_delay(2, jitter_ratio=0.0) == 120.0

    def test_budget_exhaustion_past_ladder(self) -> None:
        """Attempt >= 3 (the 4th retry) returns None (budget exhausted)."""
        assert retry_delay(3, jitter_ratio=0.0) is None
        assert retry_delay(4, jitter_ratio=0.0) is None

    def test_upward_jitter_bounds(self) -> None:
        """Jitter [0.0, 0.2] scales delay upward, clamped to cap."""
        # Step 0: 5.0 * 1.2 = 6.0
        assert retry_delay(0, jitter_ratio=0.2) == 6.0
        # Step 1: 30.0 * 1.2 = 36.0
        assert retry_delay(1, jitter_ratio=0.2) == 36.0
        # Step 2: 120.0 * 1.2 = 144.0 -> clamped to 120.0
        assert retry_delay(2, jitter_ratio=0.2) == 120.0

    def test_retry_after_within_cap_takes_max_with_ladder(self) -> None:
        """If Retry-After is smaller than nominal ladder, ladder wins."""
        assert retry_delay(0, retry_after_s=2.0, jitter_ratio=0.0) == 5.0
        assert retry_delay(0, retry_after_s=45.0, jitter_ratio=0.0) == 45.0
        assert retry_delay(1, retry_after_s=50.0, jitter_ratio=0.0) == 50.0

    def test_retry_after_exceeding_cap_fails_fast(self) -> None:
        """Retry-After > cap (120s) returns None to fail fast immediately."""
        assert retry_delay(0, retry_after_s=121.0, jitter_ratio=0.0) is None
        assert retry_delay(0, retry_after_s=300.0, jitter_ratio=0.0) is None
        assert retry_delay(1, retry_after_s=500.0, jitter_ratio=0.0) is None

    def test_retry_after_exactly_at_cap(self) -> None:
        assert retry_delay(0, retry_after_s=120.0, jitter_ratio=0.0) == 120.0

    def test_custom_ladder_and_cap(self) -> None:
        custom_ladder = (2.0, 10.0)
        assert retry_delay(0, ladder=custom_ladder, cap=50.0, jitter_ratio=0.0) == 2.0
        assert retry_delay(1, ladder=custom_ladder, cap=50.0, jitter_ratio=0.0) == 10.0
        assert retry_delay(2, ladder=custom_ladder, cap=50.0, jitter_ratio=0.0) is None


class TestRetryWrapperPin:
    """Pins for the activity-side model wrapper and judge call budget under 429."""

    @pytest.mark.asyncio
    async def test_wrapper_always_429_bounded_by_four_total_requests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An always-429 provider experiences 4 requests (1 initial + 3 retries) then raises."""
        from pydantic_ai import Agent
        from pydantic_ai.exceptions import ModelHTTPError

        from sdlc.agents.model_ids import single_retry_layer
        from tests.durability._http_stub import ProviderStub

        monkeypatch.setattr("sdlc.agents.retry_policy.DEFAULT_LADDER", (0.0, 0.0, 0.0))
        monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

        with ProviderStub(mode="always_429") as stub:
            monkeypatch.setenv("OPENAI_BASE_URL", stub.base_url)
            model = single_retry_layer().resolver(None, "openai:gpt-5.2")  # type: ignore[arg-type]

            agent = Agent(model)
            with pytest.raises(ModelHTTPError) as exc_info:
                await agent.run("ping")

            assert exc_info.value.status_code == 429
            assert stub.count == 4, f"expected exactly 4 requests on always-429, got {stub.count}"

    @pytest.mark.asyncio
    async def test_wrapper_fail_once_succeeds_on_exactly_two_requests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One transient 429 followed by success costs exactly 2 requests (1 failed + 1 success)."""
        from pydantic_ai import Agent

        from sdlc.agents.model_ids import single_retry_layer
        from tests.durability._http_stub import ProviderStub

        monkeypatch.setattr("sdlc.agents.retry_policy.DEFAULT_LADDER", (0.0, 0.0, 0.0))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "stub-key")

        with ProviderStub(mode="fail_once") as stub:
            monkeypatch.setenv("ANTHROPIC_BASE_URL", stub.base_url)
            model = single_retry_layer().resolver(None, "anthropic:claude-sonnet-5")  # type: ignore[arg-type]

            # pydantic-ai 2.61 upgrades Anthropic requests to streaming when effective
            # max_tokens exceeds _MAX_NON_STREAMING_TOKENS. ProviderStub serves JSON (not SSE),
            # so explicit max_tokens is passed to prevent the streaming upgrade. Production
            # sets max_tokens explicitly (e.g. judge sets judge_max_tokens).
            agent = Agent(model, model_settings={"max_tokens": 100})
            res = await agent.run("ping")

            assert res.output == "ok"
            assert stub.count == 2, f"expected exactly 2 requests on fail-once, got {stub.count}"

    @pytest.mark.asyncio
    async def test_wrapper_non_transient_400_fails_fast_on_one_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 400 bad request fails immediately without any retries (exactly 1 request)."""
        from pydantic_ai import Agent
        from pydantic_ai.exceptions import ModelHTTPError

        from sdlc.agents.model_ids import single_retry_layer
        from tests.durability._http_stub import ProviderStub

        monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

        with ProviderStub(mode="always_400") as stub:
            monkeypatch.setenv("OPENAI_BASE_URL", stub.base_url)
            model = single_retry_layer().resolver(None, "openai:gpt-5.2")  # type: ignore[arg-type]

            agent = Agent(model)
            with pytest.raises(ModelHTTPError) as exc_info:
                await agent.run("ping")

            assert exc_info.value.status_code == 400
            assert stub.count == 1, f"expected exactly 1 request on 400, got {stub.count}"

    def test_judge_and_wrapper_do_not_multiply_attempts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Judge call on 429 must not multiply attempts (pin <= 4 calls total)."""
        from pydantic_ai.exceptions import ModelHTTPError

        from sdlc.benchmarks import judge as judge_mod
        from tests.durability._http_stub import ProviderStub

        monkeypatch.setattr("sdlc.agents.retry_policy.DEFAULT_LADDER", (0.0, 0.0, 0.0))
        monkeypatch.setattr(judge_mod, "_JUDGE_RETRY_DELAYS", (0.0, 0.0, 0.0))
        monkeypatch.setenv("OPENAI_API_KEY", "stub-key")

        with ProviderStub(mode="always_429") as stub:
            monkeypatch.setenv("OPENAI_BASE_URL", stub.base_url)
            with pytest.raises(ModelHTTPError):
                judge_mod._run_judge_agent("openai:gpt-5.2", "sys", "user prompt")

            assert stub.count <= 4, (
                f"Judge call on always-429 saw {stub.count} requests; "
                f"pin <= 4 must hold without multiplication between wrapper and judge loop"
            )

    @pytest.mark.asyncio
    async def test_wrapper_honors_retry_after_and_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Wrapper retries after Retry-After header and succeeds on attempt 2."""
        from pydantic_ai import Agent

        from sdlc.agents.model_ids import single_retry_layer
        from tests.durability._http_stub import ProviderStub

        monkeypatch.setattr("sdlc.agents.retry_policy.DEFAULT_LADDER", (0.0, 0.0, 0.0))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "stub-key")
        with ProviderStub(mode="retry_after_once") as stub:
            monkeypatch.setenv("ANTHROPIC_BASE_URL", stub.base_url)
            model = single_retry_layer().resolver(None, "anthropic:claude-sonnet-5")  # type: ignore[arg-type]
            # pydantic-ai 2.61 upgrades Anthropic requests to streaming when effective
            # max_tokens exceeds _MAX_NON_STREAMING_TOKENS. ProviderStub serves JSON (not SSE),
            # so explicit max_tokens is passed to prevent the streaming upgrade. Production
            # sets max_tokens explicitly (e.g. judge sets judge_max_tokens).
            agent = Agent(model, model_settings={"max_tokens": 100})
            res = await agent.run("ping")
            assert res.output == "ok"
            assert stub.count == 2, f"expected 2 requests on retry_after_once, got {stub.count}"

    @pytest.mark.asyncio
    async def test_wrapper_fails_fast_on_excessive_retry_after(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Wrapper fails fast on attempt 1 when Retry-After exceeds 120s cap."""
        from pydantic_ai import Agent
        from pydantic_ai.exceptions import ModelHTTPError

        from sdlc.agents.model_ids import single_retry_layer
        from tests.durability._http_stub import ProviderStub

        monkeypatch.setenv("OPENAI_API_KEY", "stub-key")
        with ProviderStub(mode="always_429_excessive_retry_after") as stub:
            monkeypatch.setenv("OPENAI_BASE_URL", stub.base_url)
            model = single_retry_layer().resolver(None, "openai:gpt-5.2")  # type: ignore[arg-type]
            agent = Agent(model)
            with pytest.raises(ModelHTTPError) as exc_info:
                await agent.run("ping")
            assert exc_info.value.status_code == 429
            assert stub.count == 1, (
                f"expected fail-fast on attempt 1 with Retry-After > 120s, got {stub.count}"
            )


class TestExtractStatusAndRetryAfter:
    def test_model_http_error_with_numeric_retry_after(self) -> None:
        from pydantic_ai.exceptions import ModelHTTPError

        err = ModelHTTPError(429, "test-model", headers={"retry-after": "12.5"})
        status, delay, timed_out = extract_status_and_retry_after(err)
        assert status == 429
        assert delay == 12.5
        assert not timed_out

    def test_model_http_error_with_date_retry_after(self) -> None:
        from pydantic_ai.exceptions import ModelHTTPError

        err = ModelHTTPError(
            503, "test-model", headers={"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}
        )
        status, delay, timed_out = extract_status_and_retry_after(err)
        assert status == 503
        assert delay is not None
        assert not timed_out

    def test_model_http_error_without_headers(self) -> None:
        from pydantic_ai.exceptions import ModelHTTPError

        err = ModelHTTPError(400, "test-model")
        status, delay, timed_out = extract_status_and_retry_after(err)
        assert status == 400
        assert delay is None
        assert not timed_out

    def test_httpx_status_error_with_headers(self) -> None:
        import httpx

        req = httpx.Request("POST", "http://example.com")
        resp = httpx.Response(429, headers={"retry-after": "45"}, request=req)
        err = httpx.HTTPStatusError("rate limited", request=req, response=resp)
        status, delay, timed_out = extract_status_and_retry_after(err)
        assert status == 429
        assert delay == 45.0
        assert not timed_out

    def test_httpx_timeout_exception(self) -> None:
        import httpx

        err = httpx.ReadTimeout("hang")
        status, delay, timed_out = extract_status_and_retry_after(err)
        assert status is None
        assert delay is None
        assert timed_out

    def test_arbitrary_exception(self) -> None:
        err = RuntimeError("something broke")
        status, delay, timed_out = extract_status_and_retry_after(err)
        assert status is None
        assert delay is None
        assert not timed_out
