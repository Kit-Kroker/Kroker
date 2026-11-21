"""The 2MB wire guard (FR-702, ADR-10): payloads through workflow history
stay under 2MB because the platform REFUSES to write them.

``to_payload`` is the one chokepoint every serialization in-process passes
through (activity inputs scheduled from workflow code, activity results,
signals, start args) — a ``PayloadCodec`` is applied by RPC-path helpers
and is not guaranteed on all write paths, which is why the guard lives
here. The construction matches the installed temporalio 1.31.0
``contrib/pydantic.py`` verbatim (``DataConverter(payload_converter_class=
PydanticPayloadConverter)`` — no failure-converter argument exists there,
and the failure wire format is untouched). Decode is untouched: old
events replay fine; only writes over the limit fail.

Failure modes, both accepted (spec D7): an oversized activity RESULT fails
the activity task, retries exhaust, the workflow takes its existing
failure path; an oversized INPUT (activity args, signals, continue-as-new
carries) fails the WORKFLOW task, which Temporal retries indefinitely —
the run wedges Running until terminated, detectable by the deploy drain
query. No escape hatch: a legitimate payload over the limit gets
claim-checked, never env-raised past the guard.
"""

from __future__ import annotations

from typing import Any

from temporalio.api.common.v1 import Payload
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

MAX_PAYLOAD_BYTES = 2 * 1024 * 1024  # PRD FR-702: payloads stay under 2MB


class PayloadTooLargeError(RuntimeError):
    """A payload at or over MAX_PAYLOAD_BYTES was refused at serialization."""


class _GuardedJSONPlainPayloadConverter(PydanticJSONPlainPayloadConverter):
    def to_payload(self, value: Any) -> Payload | None:
        payload = super().to_payload(value)
        if payload is not None and len(payload.data) >= MAX_PAYLOAD_BYTES:
            raise PayloadTooLargeError(
                f"payload is {len(payload.data)} bytes >= {MAX_PAYLOAD_BYTES} "
                "(2MB wire limit); claim-check it via ArtifactRef (FR-702)"
            )
        return payload


class SdlcPayloadConverter(PydanticPayloadConverter):
    """The contrib composite with the guarded JSON converter first — the
    installed module's own construction, JSON leg swapped. The converters
    tuple goes to CompositePayloadConverter directly (the pydantic middle
    class only takes to_json_options)."""

    def __init__(self) -> None:
        json_payload_converter = _GuardedJSONPlainPayloadConverter()
        CompositePayloadConverter.__init__(
            self,
            *(
                c if not isinstance(c, JSONPlainPayloadConverter) else json_payload_converter
                for c in DefaultPayloadConverter.default_encoding_payload_converters
            ),
        )


sdlc_data_converter = DataConverter(payload_converter_class=SdlcPayloadConverter)
