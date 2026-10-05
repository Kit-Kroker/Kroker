"""The sub-run usage report: the channel a tool uses to hand the spend of a
model it ran inside its own activity back to the workflow (C12 /
architect-research-surface, plan D1; research R2, R5).

A tool returns ``ToolReturn(return_value=<its value>, metadata=metadata_for(
report))``; the single model-egress point later harvests the reports with
``harvest_reports``. The metadata rides the durable tool-activity boundary as
a plain dict (never a class instance), and the provider mappings never
serialize it, so the model sees nothing new (spike E1/E2).

Pure module: no temporalio, no pydantic_ai, no stage import — importable
activity-side and workflow-side alike.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

SUB_RUN_USAGE_KEY = "sdlc_sub_run_usage"
"""The only place in src/ the reserved metadata key is spelled."""


class SubRunUsage(BaseModel):
    """One inner model run's spend: five small fields, frozen."""

    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(ge=0)


def from_run_usage(run_usage: Any, model: str) -> SubRunUsage | None:
    """Build the report from a caller-owned RunUsage-like object. None when
    input and output are both zero (a call refused before any request stays
    silent — mirrors the stage path); absent counts coerce to 0."""
    input_tokens = getattr(run_usage, "input_tokens", None) or 0
    output_tokens = getattr(run_usage, "output_tokens", None) or 0
    if not (input_tokens or output_tokens):
        return None
    return SubRunUsage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=getattr(run_usage, "cache_read_tokens", None) or 0,
        cache_write_tokens=getattr(run_usage, "cache_write_tokens", None) or 0,
    )


def metadata_for(report: SubRunUsage) -> dict[str, Any]:
    """The tool-return metadata carrying the report: a plain dict under the
    reserved key, JSON-safe so it survives the durable round trip."""
    return {SUB_RUN_USAGE_KEY: report.model_dump(mode="json")}


def harvest_reports(result: Any) -> list[SubRunUsage]:
    """Read the reports a run's messages carry, in message order then part
    order. Duck-typed and total (research R5): a result without a callable
    ``new_messages`` yields nothing; a part counts only when its
    ``part_kind`` is ``tool-return`` and its ``metadata`` is a dict holding
    the key; a payload that fails validation or holds an empty-token report
    is skipped; any other error yields ``[]`` — a malformed report must never
    fail the run."""
    try:
        get_messages = getattr(result, "new_messages", None)
        if not callable(get_messages):
            return []
        reports: list[SubRunUsage] = []
        for message in get_messages() or ():
            for part in getattr(message, "parts", None) or ():
                if getattr(part, "part_kind", None) != "tool-return":
                    continue
                metadata = getattr(part, "metadata", None)
                if not isinstance(metadata, dict) or SUB_RUN_USAGE_KEY not in metadata:
                    continue
                try:
                    report = SubRunUsage.model_validate(metadata[SUB_RUN_USAGE_KEY])
                except Exception:
                    continue
                if not (report.input_tokens or report.output_tokens):
                    continue
                reports.append(report)
        return reports
    except Exception:
        return []
