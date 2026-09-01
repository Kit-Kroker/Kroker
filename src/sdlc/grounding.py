"""FR-914/FR-107 (E-43): no claim may be labelled grounded unless its quote is
verbatim in the bytes it cites.

One invariant, three byte-sources: pages fetched this run (research), stored
harness transcripts (handoff, deep_review), and committed code at path@sha
(assessment, not yet wired). Callers supply the bytes; this module only decides
whether the quote is in them.

TWO PROFILES, DELIBERATELY NOT ONE (spec D6). EXTRACTED_TEXT carries the two
loosenings a third-party HTML/PDF extractor forces on us, each proven by a
specific false failure. VERBATIM_BYTES carries neither, because `**` is
meaningful Python and quote glyphs are meaningful inside string literals --
applying the extractor profile to code would silently weaken the check SC-7
rests on. Every further loosening is a hole: add none without a test proving
the specific false-failure it fixes.

This module NEVER decides consequences (spec D7). It returns a verdict; the
caller chooses between failing a stage, dropping a claim, or failing closed.

Pure by design -- stdlib and Pydantic only. Must never import models.py or
temporalio.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class Profile(StrEnum):
    EXTRACTED_TEXT = "extracted_text"  # third-party extractor output
    VERBATIM_BYTES = "verbatim_bytes"  # committed code, stored transcripts


_WS = re.compile(r"\s+")

# Proven false-failure (cat-cafe-monitoring smoke run, 2026-07-20): Tavily's
# PDF extractor decoded a source's curly apostrophe (U+2019) as U+FFFD
# (REPLACEMENT CHARACTER) -- "owner<FFFD>s phone" on the page, "owner's phone"
# in an otherwise word-for-word-verbatim quote. Not a model error; the byte was
# already lost upstream of us. Apostrophe/quote variants are low-signal
# punctuation, so dropping them symmetrically from quote and haystack closes
# this hole without weakening word-level matching.
# NOT in VERBATIM_BYTES: in source code a quote glyph is content, not noise.
_APOSTROPHE = re.compile(r"['‘’`\ufffd]")

# Proven false-failure (same smoke run): Tavily's HTML-to-text extraction left
# literal markdown emphasis markers (`**bold**`) inside otherwise-plain prose.
# The model quoted the underlying sentence without them, which is faithful to
# the source but breaks a byte-exact substring check.
# NOT in VERBATIM_BYTES: `**` is Python's kwargs/exponent operator.
_MD_BOLD = re.compile(r"\*\*")


def normalize(text: str, profile: Profile) -> str:
    """Collapse whitespace runs to one space under both profiles; additionally
    drop apostrophe-glyph noise and markdown bold markers under
    EXTRACTED_TEXT. Case and all other punctuation are preserved.

    Whitespace collapse applies to VERBATIM_BYTES too because transcripts and
    prompt-rendered code get re-wrapped and re-indented. The consequence -- an
    indentation-only difference is not detected -- is acceptable: the question
    is "did this text appear", not "is this valid code".
    """
    if profile is Profile.EXTRACTED_TEXT:
        text = _MD_BOLD.sub("", _APOSTROPHE.sub("", text))
    return _WS.sub(" ", text).strip()


class Violation(BaseModel):
    """One unverifiable claim. `source` is whatever identifies the bytes:
    a url, a "path@sha", or a session ref."""

    kind: Literal["quote_not_found", "source_unavailable", "quote_empty"]
    source: str
    quote: str


def verify_quote(quote: str, haystack: str, profile: Profile) -> bool:
    """True iff `quote` appears in `haystack` under `profile`.

    A quote that normalizes to empty is NEVER grounded: `"" in haystack` is
    True, so an empty quote would otherwise verify trivially. There is no
    minimum length beyond non-empty -- an arbitrary threshold invents false
    failures.
    """
    needle = normalize(quote, profile)
    if not needle:
        return False
    return needle in normalize(haystack, profile)


def quote_violation(quote: str, haystack: str, profile: Profile, source: str) -> Violation | None:
    """The kind-aware form of verify_quote: None when grounded, otherwise the
    typed Violation. For callers that report why, rather than only whether."""
    if not normalize(quote, profile):
        return Violation(kind="quote_empty", source=source, quote=quote)
    if verify_quote(quote, haystack, profile):
        return None
    return Violation(kind="quote_not_found", source=source, quote=quote)
