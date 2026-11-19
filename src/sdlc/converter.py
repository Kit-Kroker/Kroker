"""The 2MB wire guard (FR-702, ADR-10): ``sdlc_data_converter``.

This is the production ``temporalio.contrib.pydantic.pydantic_data_converter``
with ONE change: the JSON plain converter refuses to serialize any single
payload whose wire data is 2MB or larger. Every client and worker in this
repo builds on it, so no payload over the cap can be written to history
from any process — the fix is always the same: claim-check the bulk via an
``ArtifactRef`` and pass the reference instead.

Construction is copied verbatim from the installed ``temporalio/contrib/
pydantic.py`` (temporalio is pinned at 1.31.0 in ``uv.lock``): the
composite substitutes the JSON plain converter inside
``DefaultPayloadConverter.default_encoding_payload_converters`` and the
``DataConverter`` is built from ``payload_converter_class`` alone. There
is deliberately NO failure-converter argument — the failure wire format
is untouched, so in-flight histories and replay are unaffected.

Why the payload converter and not a ``PayloadCodec``: ``to_payload`` is
the one chokepoint every serialization in-process passes through
(activity inputs scheduled from workflow code, activity results,
signals, start args); payload codecs are applied by RPC-path helpers and
are not guaranteed on all write paths.

Decode (``from_payload``) is NEVER guarded: events written before this
guard existed may be arbitrarily large and must keep decoding (design
D7). The failure modes on the write side, both accepted by design:

- *Activity result oversized*: the activity task fails with this error;
  retries re-produce the same result and exhaust; the workflow takes its
  existing failure path. Loud and terminal.
- *Input oversized* (activity args, signals, continue-as-new carries):
  the WORKFLOW task fails and Temporal retries workflow tasks
  indefinitely — the run wedges ``RUNNING`` with this error in history
  until an operator terminates it. Such an input was already doomed
  past the server's own payload cap; the guard converts an opaque
  retryable rejection into a local, labeled failure at the same
  threshold.
"""

from __future__ import annotations

from typing import Any

import temporalio.api.common.v1
from temporalio.contrib.pydantic import (
    PydanticJSONPlainPayloadConverter,
    PydanticPayloadConverter,
)
from temporalio.converter import (
    CompositePayloadConverter,
    DataConverter,
    DefaultPayloadConverter,
    JSONPlainPayloadConverter,
)

MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
"""FR-702: no single payload written to history may reach 2MB."""

CLAIM_CHECK_HINT = "claim-check it via ArtifactRef (FR-702)"


class PayloadTooLargeError(RuntimeError):
    """A payload hit the 2MB wire cap. Claim-check it via an ArtifactRef."""


class _GuardedJSONPlainPayloadConverter(PydanticJSONPlainPayloadConverter):
    """The pydantic JSON plain converter with the FR-702 size guard on writes."""

    def to_payload(self, value: Any) -> temporalio.api.common.v1.Payload | None:
        payload = super().to_payload(value)
        if payload is not None and len(payload.data) >= MAX_PAYLOAD_BYTES:
            raise PayloadTooLargeError(
                f"payload is {len(payload.data)} bytes >= {MAX_PAYLOAD_BYTES}"
                f" (2MB history cap); {CLAIM_CHECK_HINT}"
            )
        return payload


class _GuardedPayloadConverter(PydanticPayloadConverter):
    """``PydanticPayloadConverter``'s composite with the guarded JSON converter.

    The ``__init__`` body is the installed ``PydanticPayloadConverter``'s,
    verbatim (built on ``CompositePayloadConverter`` directly so the guarded
    class lands in the chain instead of the plain one).

    The ``PydanticPayloadConverter`` base is LOAD-BEARING: pydantic-ai's
    Temporal plugin — which every production worker and replayer here runs —
    replaces any converter whose ``payload_converter_class`` is not a genuine
    ``PydanticPayloadConverter`` subclass with its own, guard-less
    ``PydanticAIPayloadConverter``
    (pydantic_ai/durable_exec/temporal/__init__.py, ``_data_converter``);
    subclasses are preserved by contract. Pinned by
    ``test_pydantic_ai_plugin_preserves_the_guarded_converter``.
    """

    def __init__(self) -> None:
        """Initialize object"""
        json_payload_converter = _GuardedJSONPlainPayloadConverter()
        CompositePayloadConverter.__init__(
            self,
            *(
                c if not isinstance(c, JSONPlainPayloadConverter) else json_payload_converter
                for c in DefaultPayloadConverter.default_encoding_payload_converters
            ),
        )


sdlc_data_converter = DataConverter(payload_converter_class=_GuardedPayloadConverter)
"""The production wire converter: pydantic, plus the 2MB write guard."""
