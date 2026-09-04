"""Artifact models for the context stage (spec A §2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BrownfieldDelta(BaseModel):
    """FR-102's delta: what an architecture change does to a real tree.

    Three classes rather than one flat list because they have OPPOSITE
    grounding rules -- a modified path must exist and an added path must not
    (E-84 D8) -- and a single list cannot carry that distinction.
    """

    added: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
