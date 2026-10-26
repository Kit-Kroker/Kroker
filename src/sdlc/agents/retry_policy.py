"""Pure exponential backoff policy and error classification for the single-retry seam.

This module provides offline-testable delay calculations, transient error
classification, and the RetryBackoffModel wrapper.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any, NoReturn

from pydantic_ai.models.wrapper import WrapperModel

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models import (
        Model,
        ModelRequestParameters,
        ModelResponse,
        StreamedResponse,
    )
    from pydantic_ai.settings import ModelSettings
    from pydantic_ai.tools import RunContext

_LOGGER = logging.getLogger(__name__)

DEFAULT_LADDER: tuple[float, ...] = (5.0, 30.0, 120.0)
DEFAULT_CAP: float = 120.0
DEFAULT_TRANSIENT_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def is_transient(status: int | None, timed_out: bool = False) -> bool:
    """True iff the error is a transient failure worthy of a backoff retry.

    Transient errors:
    - HTTP statuses 429 (rate limit) and 500, 502, 503, 504 (server errors).
    - Read/connect timeouts (provider hangs).

    All other 4xx (400 bad request, 401 auth, 403 forbidden, 404 not found, 422)
    and 5xx (501 not implemented, 505) fail-fast without retry.
    """
    if timed_out:
        return True
    return status is not None and status in DEFAULT_TRANSIENT_STATUSES


def parse_retry_after(
    raw: str | int | float | None,
    *,
    now: datetime | None = None,
) -> float | None:
    """Parse a Retry-After header value into seconds.

    Supports:
    - Integer or float seconds (>= 0).
    - RFC 9110 HTTP-date strings (e.g. 'Wed, 21 Oct 2026 07:28:00 GMT').

    Returns None if absent, negative, or unparseable.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw >= 0 else None

    text = str(raw).strip()
    if not text:
        return None

    # Try numeric seconds first
    try:
        val = float(text)
        return val if val >= 0 else None
    except (ValueError, OverflowError):
        pass

    # Try HTTP-date parsing
    try:
        retry_time = parsedate_to_datetime(text)
        if retry_time.tzinfo is None:
            retry_time = retry_time.replace(tzinfo=UTC)
        current = now if now is not None else datetime.now(UTC)
        wait = (retry_time - current).total_seconds()
        return max(0.0, wait)
    except Exception:
        return None


def retry_delay(
    attempt: int,
    *,
    retry_after_s: float | None = None,
    jitter_ratio: float = 0.0,
    ladder: tuple[float, ...] = DEFAULT_LADDER,
    cap: float = DEFAULT_CAP,
) -> float | None:
    """Compute the backoff delay for an attempt index (0-indexed).

    Returns None if:
    - attempt >= len(ladder) (exhausted retry budget).
    - retry_after_s > cap (fail fast immediately rather than burning attempts).

    Otherwise:
    - nominal delay = max(ladder[attempt], retry_after_s) if retry_after_s given,
      else ladder[attempt].
    - upward jitter = min(cap, nominal * (1.0 + max(0.0, jitter_ratio))).
    """
    if attempt < 0 or attempt >= len(ladder):
        return None

    if retry_after_s is not None:
        if retry_after_s > cap:
            return None
        nominal = max(ladder[attempt], retry_after_s)
    else:
        nominal = ladder[attempt]

    jittered = nominal * (1.0 + max(0.0, jitter_ratio))
    return min(cap, jittered)


def extract_status_and_retry_after(
    exc: Exception,
) -> tuple[int | None, float | None, bool]:
    """Extract HTTP status, Retry-After seconds, and timeout flag from an exception.

    Inspects:
    - pydantic_ai.exceptions.ModelHTTPError
    - httpx.HTTPStatusError
    - httpx.TimeoutException
    """
    import httpx
    from pydantic_ai.exceptions import ModelHTTPError

    if isinstance(exc, ModelHTTPError):
        retry_after = getattr(exc, "retry_after", None)
        if retry_after is None and exc.headers:
            retry_after = parse_retry_after(exc.headers.get("retry-after"))
        return exc.status_code, retry_after, False

    if isinstance(exc, httpx.HTTPStatusError):
        raw_header = exc.response.headers.get("retry-after")
        return exc.response.status_code, parse_retry_after(raw_header), False

    if isinstance(exc, httpx.TimeoutException):
        return None, None, True

    return None, None, False


def _active_ladder(custom_ladder: tuple[float, ...] | None = None) -> tuple[float, ...]:
    """Active retry ladder, respecting an explicit tuple or runtime
    monkeypatch of DEFAULT_LADDER.
    """
    if custom_ladder is not None:
        return tuple(float(d) for d in custom_ladder)

    from . import retry_policy

    ladder = getattr(retry_policy, "DEFAULT_LADDER", DEFAULT_LADDER)
    return tuple(float(d) for d in ladder)


def _raise_with_temporal_non_retryable(exc: Exception) -> NoReturn:
    """Re-raise exc, marking it non-retryable if inside a Temporal activity."""
    try:
        from temporalio import activity
        from temporalio.exceptions import ApplicationError

        if activity.in_activity():
            raise ApplicationError(
                str(exc),
                type=type(exc).__name__,
                non_retryable=True,
            ) from exc
    except ImportError:
        pass
    raise exc


class RetryBackoffModel(WrapperModel):
    """Model wrapper providing activity-side exponential backoff with jitter for 429/5xx."""

    def __init__(self, wrapped: Model, ladder: tuple[float, ...] | None = None):
        super().__init__(wrapped)
        self.ladder = ladder

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        ladder = _active_ladder(self.ladder)

        for attempt in range(len(ladder) + 1):
            try:
                return await self.wrapped.request(
                    messages, model_settings, model_request_parameters
                )
            except Exception as exc:
                status, retry_after, timed_out = extract_status_and_retry_after(exc)
                if not is_transient(status, timed_out=timed_out):
                    _raise_with_temporal_non_retryable(exc)
                if attempt >= len(ladder):
                    _raise_with_temporal_non_retryable(exc)
                jitter_ratio = random.uniform(0.0, 0.2)
                delay = retry_delay(
                    attempt,
                    retry_after_s=retry_after,
                    jitter_ratio=jitter_ratio,
                    ladder=ladder,
                    cap=DEFAULT_CAP,
                )
                if delay is None:
                    _raise_with_temporal_non_retryable(exc)
                _LOGGER.warning(
                    "model request failed (%s, HTTP %s) (attempt %d/%d); retrying in %ss",
                    type(exc).__name__,
                    status,
                    attempt + 1,
                    len(ladder) + 1,
                    delay,
                )
                if delay > 0:
                    await asyncio.sleep(delay)

        raise AssertionError("unreachable: the retry loop returns or raises")

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncGenerator[StreamedResponse]:
        async with self.wrapped.request_stream(
            messages, model_settings, model_request_parameters, run_context
        ) as response_stream:
            yield response_stream
