# Measurement and Shared Grounding Verifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a never-measured value structurally unconfusable with a measured one (E-40/FR-915), and make every model-asserted quote in the pipeline verifiable against the bytes it cites (E-43/FR-914).

**Architecture:** Two new pure modules — `measurement.py` (`Measurement`, `CollectionState`) and `grounding.py` (`normalize`, `verify_quote`, `quote_violation`, `Profile`, `Violation`) — neither importing `models.py` nor Temporal. `research/verify.py` keeps its page lookup and delegates the match. `CoverageReport`, `SecurityReport`, `QAReport` and `handoff.claim_survival_score` are retrofitted onto `Measurement`, and the merge gate's `security_no_critical` splits into two absolute checks so "scan found nothing" and "no scan happened" stop being the same gate result. Two live consumers that carry unverified quotes today — handoff claims and deep-review integrity flags — start verifying them, dropping (never failing) on a violation.

**Tech Stack:** Python 3.12+, Pydantic v2, Temporal Python SDK, pytest, defusedxml.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-06-measurement-and-shared-grounding-verifier-design.md`. Decisions D1–D7 there are binding; this plan implements them and does not revisit them.
- **`measurement.py` imports only Pydantic. `grounding.py` imports only stdlib and Pydantic.** Neither imports `models.py`, `activities.py`, or anything from `temporalio`. A future dependency must appear as a reviewable import.
- **Enum idiom is `class X(str, Enum)`**, matching `models.py:18-41`. Do not use `StrEnum`.
- **Replace, no compatibility shim (D3).** Old fields are deleted, not deprecated alongside new ones. Do not add back-compat validators or aliases.
- **Normalization profiles must never be merged (D6).** `EXTRACTED_TEXT`'s apostrophe and `**` loosenings are justified by two specific documented Tavily extraction bugs and must not apply to code or transcripts, where `**` and quote glyphs are meaningful.
- **The verifier never decides consequences (D7).** `verify_quote` / `quote_violation` return a verdict. Research fails its stage; handoff and deep-review drop the item; assessment (not built here) will fail closed.
- **Lenses must never fail delivery.** `_run_handoff` and `_run_deep_review` keep their `except Exception` fallbacks. Verification is added *inside* the try, and an unavailable haystack means "skip verification", never "drop everything" (spec §5, consumer note).
- **Cause records carry `fix_attempts=0`.** Unchanged from the existing handoff/deep_review records; do not alter.
- Run tests with `python -m pytest`. `git` must be on PATH. Importing workflow/agent modules requires `ANTHROPIC_API_KEY` set (a dummy value works).
- Commit after every task. Do not batch commits across tasks.

---

## File Structure

**Create:**
- `src/sdlc/measurement.py` — `CollectionState`, `Measurement`. Pure; the validator that makes the illegal state unconstructible.
- `src/sdlc/grounding.py` — `Profile`, `Violation`, `normalize`, `verify_quote`, `quote_violation`. Pure; the one substring invariant plus its two normalization profiles.
- `tests/test_measurement.py`, `tests/test_grounding.py`, `tests/test_read_committed_bytes.py`

**Modify:**
- `src/sdlc/research/verify.py` — delete local `normalize`/`Violation`/regexes; delegate to `grounding`.
- `src/sdlc/models.py` — `CoverageReport`, `SecurityReport`, `QAReport`.
- `src/sdlc/activities.py` — `measure_coverage`, `security_scan`, new `read_committed_bytes`.
- `src/sdlc/toolchain/sarif.py` — `report_from_sarif` collection state.
- `src/sdlc/handoff.py` — `CrossCheckResult`, quote verification, `claim_survival_score`.
- `src/sdlc/workflows/feature.py` — merge-gate checks, `_run_handoff`, `_run_deep_review`, research violation formatting.
- `src/sdlc/worker.py` — register `read_committed_bytes`.
- `tests/fakes/fake_activities.py`, `tests/fakes/canned.py`, `tests/test_research_verify.py`, `tests/test_research_grounding.py`, `tests/test_research_e2e.py`, `tests/test_measure_coverage.py`, `tests/test_analyst_models.py`, `tests/test_security_floor.py`, `tests/test_sarif.py`, `tests/test_handoff_crosscheck.py`

**Deliberately NOT modified:** the research grounding policy (E-29 fail-and-continue), `check_adr6_families`, the advisory `coverage` check's pass semantics, and `sarif.py`'s SARIF→finding mapping.

---

## Task 1: `Measurement` and `CollectionState`

The type the rest of the plan retrofits onto. Pure, no consumers yet.

**Files:**
- Create: `src/sdlc/measurement.py`
- Test: `tests/test_measurement.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `CollectionState.{MEASURED,NOT_COLLECTED,UNKNOWN}`; `Measurement(state=..., value=float|None, reason=str)`; constructors `Measurement.measured(value: float)`, `Measurement.not_collected(reason: str)`, `Measurement.unknown(reason: str)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_measurement.py`:

```python
"""FR-915: a measured value and a never-measured value must not be the same
object. The validator is the mechanism -- the illegal state is unconstructible,
not merely discouraged."""
import pytest
from pydantic import ValidationError

from sdlc.measurement import CollectionState, Measurement


def test_measured_carries_a_value():
    m = Measurement.measured(0.0)
    assert m.state is CollectionState.MEASURED
    assert m.value == 0.0


def test_measured_without_a_value_is_unconstructible():
    with pytest.raises(ValidationError):
        Measurement(state=CollectionState.MEASURED)


def test_not_collected_with_a_value_is_unconstructible():
    """The whole point: a not-collected measurement cannot smuggle a zero."""
    with pytest.raises(ValidationError):
        Measurement(state=CollectionState.NOT_COLLECTED, value=0.0,
                    reason="no artifact")


def test_unknown_with_a_value_is_unconstructible():
    with pytest.raises(ValidationError):
        Measurement(state=CollectionState.UNKNOWN, value=0.0, reason="nan rate")


def test_non_measured_states_require_a_reason():
    with pytest.raises(ValidationError):
        Measurement(state=CollectionState.NOT_COLLECTED)
    with pytest.raises(ValidationError):
        Measurement(state=CollectionState.UNKNOWN, reason="   ")


def test_measured_zero_is_not_equal_to_not_collected():
    assert Measurement.measured(0.0) != Measurement.not_collected("no artifact")


def test_the_distinction_survives_a_json_round_trip():
    """These travel through Temporal history as JSON; the distinction has to
    survive serialization or it is decorative."""
    for m in (Measurement.measured(0.0),
              Measurement.not_collected("no artifact"),
              Measurement.unknown("non-finite rate")):
        assert Measurement.model_validate_json(m.model_dump_json()) == m


def test_constructors_set_the_state_they_name():
    assert Measurement.not_collected("r").state is CollectionState.NOT_COLLECTED
    assert Measurement.unknown("r").state is CollectionState.UNKNOWN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_measurement.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.measurement'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/measurement.py`:

```python
"""FR-915 (E-40): a value that was never measured must not be representable as
a measured value.

Imported wholesale from BrownKit's `not-collected` discipline, which treats it
as a first-class state with a recorded reason and forbids defaulting to zero.
The model validator is the mechanism: `Measurement(NOT_COLLECTED, value=0.0)`
does not construct, so the ambiguity cannot be reintroduced by a careless
producer.

Pure by design -- Pydantic only. This module must never import models.py,
activities.py, or temporalio; a dependency here would appear as a reviewable
import.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, model_validator


class CollectionState(str, Enum):
    MEASURED = "measured"
    NOT_COLLECTED = "not_collected"   # we did not or could not measure
    UNKNOWN = "unknown"               # we tried; the result is uninterpretable


class Measurement(BaseModel):
    """A number we may not have, with the reason we do not have it.

    NOT_COLLECTED vs UNKNOWN: no coverage.xml is not_collected; a coverage.xml
    that parses but yields a non-finite rate is unknown. The distinction is
    whether an attempt produced output. Both require a reason.
    """
    state: CollectionState
    value: float | None = None
    reason: str = ""

    @model_validator(mode="after")
    def _value_matches_state(self) -> "Measurement":
        if self.state is CollectionState.MEASURED:
            if self.value is None:
                raise ValueError("MEASURED requires a value")
        else:
            if self.value is not None:
                raise ValueError(
                    f"{self.state.value} must not carry a value "
                    f"(got {self.value!r}) -- that is the conflation this "
                    f"type exists to prevent")
            if not self.reason.strip():
                raise ValueError(f"{self.state.value} requires a reason")
        return self

    @classmethod
    def measured(cls, value: float) -> "Measurement":
        return cls(state=CollectionState.MEASURED, value=value)

    @classmethod
    def not_collected(cls, reason: str) -> "Measurement":
        return cls(state=CollectionState.NOT_COLLECTED, reason=reason)

    @classmethod
    def unknown(cls, reason: str) -> "Measurement":
        return cls(state=CollectionState.UNKNOWN, reason=reason)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_measurement.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/measurement.py tests/test_measurement.py
git commit -m "feat: Measurement type with an unconstructible illegal state (E-40/FR-915)"
```

---

## Task 2: `grounding.py` — the shared verifier

The invariant, extracted so three byte-sources share it without sharing a normalization profile.

**Files:**
- Create: `src/sdlc/grounding.py`
- Test: `tests/test_grounding.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Profile.{EXTRACTED_TEXT,VERBATIM_BYTES}`; `Violation(kind: Literal["quote_not_found","source_unavailable","quote_empty"], source: str, quote: str)`; `normalize(text: str, profile: Profile) -> str`; `verify_quote(quote: str, haystack: str, profile: Profile) -> bool`; `quote_violation(quote: str, haystack: str, profile: Profile, source: str) -> Violation | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_grounding.py`:

```python
"""FR-914 (E-43): one substring invariant, two normalization profiles.

The profile split is the load-bearing part. EXTRACTED_TEXT's loosenings are
justified by specific Tavily extraction bugs; applying them to code or
transcripts would weaken the check SC-7 rests on.
"""
from sdlc.grounding import (
    Profile, Violation, normalize, quote_violation, verify_quote,
)

EXTRACTED = Profile.EXTRACTED_TEXT
VERBATIM = Profile.VERBATIM_BYTES


def test_plain_substring_grounds_under_both_profiles():
    hay = "The library handles retries natively."
    assert verify_quote("handles retries natively", hay, EXTRACTED)
    assert verify_quote("handles retries natively", hay, VERBATIM)


def test_absent_quote_fails_under_both_profiles():
    hay = "Nothing about retries here."
    assert not verify_quote("handles retries natively", hay, EXTRACTED)
    assert not verify_quote("handles retries natively", hay, VERBATIM)


def test_whitespace_collapses_under_both_profiles():
    """Extractors mangle whitespace; transcripts and prompt-rendered code get
    re-wrapped and re-indented. This is the one loosening both profiles share."""
    hay = "handles    retries\n\tnatively"
    assert verify_quote("handles retries natively", hay, EXTRACTED)
    assert verify_quote("handles retries natively", hay, VERBATIM)


def test_case_is_never_normalized():
    hay = "handles retries natively"
    assert not verify_quote("HANDLES RETRIES NATIVELY", hay, EXTRACTED)
    assert not verify_quote("HANDLES RETRIES NATIVELY", hay, VERBATIM)


def test_replacement_char_apostrophe_grounds_only_under_extracted_text():
    """Tavily's PDF extractor decoded a curly apostrophe as U+FFFD
    (cat-cafe-monitoring smoke run, 2026-07-20). Justified for extractor
    output; NOT justified for code, where quote glyphs are meaningful inside
    string literals."""
    hay = "send it to owner�s phone"
    assert verify_quote("send it to owner's phone", hay, EXTRACTED)
    assert not verify_quote("send it to owner's phone", hay, VERBATIM)


def test_markdown_bold_grounds_only_under_extracted_text():
    """Tavily left literal ** markers in plain prose (same smoke run). Under
    VERBATIM_BYTES this must fail: ** is meaningful Python."""
    hay = "achieve **centimeter-level precision** for robotics"
    assert verify_quote("achieve centimeter-level precision", hay, EXTRACTED)
    assert not verify_quote("achieve centimeter-level precision", hay, VERBATIM)


def test_kwargs_in_code_survives_verbatim_but_is_corrupted_by_extracted():
    """The concrete reason the profiles must never be merged."""
    hay = "def f(**kwargs):\n    return kwargs\n"
    assert verify_quote("def f(**kwargs):", hay, VERBATIM)
    # Under EXTRACTED_TEXT both sides lose the markers, so a DIFFERENT
    # signature would also match -- exactly the loosening we refuse for code.
    assert verify_quote("def f(kwargs):", hay, EXTRACTED)
    assert not verify_quote("def f(kwargs):", hay, VERBATIM)


def test_normalization_does_not_mask_a_real_word_mismatch():
    hay = "the dog's favorite spot"
    assert not verify_quote("the cat's favorite spot", hay, EXTRACTED)


def test_empty_quote_never_grounds():
    """`"" in haystack` is True, so an empty quote verified trivially before
    this check existed -- a hole in the shipped research verifier."""
    assert not verify_quote("", "anything at all", EXTRACTED)
    assert not verify_quote("   \n\t ", "anything at all", VERBATIM)


def test_quote_violation_returns_none_when_grounded():
    assert quote_violation("retries", "handles retries", VERBATIM,
                           source="src/a.py@abc") is None


def test_quote_violation_kinds():
    absent = quote_violation("missing", "haystack", VERBATIM, source="s")
    assert absent == Violation(kind="quote_not_found", source="s",
                               quote="missing")
    empty = quote_violation("  ", "haystack", VERBATIM, source="s")
    assert empty.kind == "quote_empty"


def test_normalize_is_idempotent():
    for profile in (EXTRACTED, VERBATIM):
        once = normalize("a  **b**  c", profile)
        assert normalize(once, profile) == once
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grounding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.grounding'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/grounding.py`:

```python
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
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class Profile(str, Enum):
    EXTRACTED_TEXT = "extracted_text"    # third-party extractor output
    VERBATIM_BYTES = "verbatim_bytes"    # committed code, stored transcripts


_WS = re.compile(r"\s+")

# Proven false-failure (cat-cafe-monitoring smoke run, 2026-07-20): Tavily's
# PDF extractor decoded a source's curly apostrophe (U+2019) as U+FFFD
# (REPLACEMENT CHARACTER) -- "owner<FFFD>s phone" on the page, "owner's phone"
# in an otherwise word-for-word-verbatim quote. Not a model error; the byte was
# already lost upstream of us. Apostrophe/quote variants are low-signal
# punctuation, so dropping them symmetrically from quote and haystack closes
# this hole without weakening word-level matching.
# NOT in VERBATIM_BYTES: in source code a quote glyph is content, not noise.
_APOSTROPHE = re.compile(r"['‘’`�]")

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


def quote_violation(quote: str, haystack: str, profile: Profile,
                    source: str) -> Violation | None:
    """The kind-aware form of verify_quote: None when grounded, otherwise the
    typed Violation. For callers that report why, rather than only whether."""
    if not normalize(quote, profile):
        return Violation(kind="quote_empty", source=source, quote=quote)
    if verify_quote(quote, haystack, profile):
        return None
    return Violation(kind="quote_not_found", source=source, quote=quote)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounding.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/grounding.py tests/test_grounding.py
git commit -m "feat: shared grounding verifier with per-source profiles (E-43/FR-914)"
```

---

## Task 3: Research delegates to the shared verifier

Behavior-preserving refactor. The regression bar: existing research tests pass unchanged except for the `source_never_fetched` → `source_unavailable` rename and the `source_url` → `source` field rename.

**Files:**
- Modify: `src/sdlc/research/verify.py:23-54` (delete regexes and `normalize`), `:95-114` (`Violation`, `verify_brief`), `:142-150` (`GroundingViolation` message)
- Modify: `src/sdlc/workflows/feature.py:1706`
- Modify: `tests/test_research_verify.py:44-49`, `tests/test_research_grounding.py:43,61`, `tests/test_research_e2e.py:46,177` (comments only)

**Interfaces:**
- Consumes: `grounding.Profile`, `grounding.Violation`, `grounding.quote_violation` (Task 2).
- Produces: `verify_brief(brief, run_id) -> list[grounding.Violation]` — same signature, `Violation` is now the shared type with `.source` (not `.source_url`) and kind `source_unavailable` (not `source_never_fetched`). `pages_dir`, `page_filename`, `write_page`, `brief_digest`, `verify_brief_activity`, `GroundingViolation` all keep their names and signatures.

- [ ] **Step 1: Update the existing tests to the new names**

In `tests/test_research_verify.py`, replace the `test_source_never_fetched_is_a_violation` test with:

```python
def test_source_unavailable_is_a_violation(runs_root):
    # No page file written for this url -> recalled-lead demotion (finding 5).
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/never", quote="anything", claim="c")])
    vios = verify.verify_brief(brief, "r1")
    assert [v.kind for v in vios] == ["source_unavailable"]
    assert vios[0].source == "https://x/never"
```

Append this new test to the same file:

```python
def test_empty_quote_is_a_violation_not_a_free_pass(runs_root):
    """`"" in haystack` is True, so before the shared verifier an empty quote
    grounded trivially against any fetched page."""
    _write_page("r1", "https://x/1", "some content")
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/1", quote="   ", claim="c")])
    assert [v.kind for v in verify.verify_brief(brief, "r1")] == ["quote_empty"]
```

In `tests/test_research_grounding.py`, change the two `"source_never_fetched"` string literals (lines 43 and 61) to `"source_unavailable"`. In `tests/test_research_e2e.py`, update the two comments (lines 46 and 177) that name `source_never_fetched` to `source_unavailable`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_research_verify.py tests/test_research_grounding.py -v`
Expected: FAIL — the renamed-kind tests fail with `AssertionError: ['source_never_fetched'] != ['source_unavailable']`, and `test_empty_quote_is_a_violation_not_a_free_pass` fails with `[] != ['quote_empty']`.

- [ ] **Step 3: Refactor `research/verify.py`**

Delete these from `src/sdlc/research/verify.py`: the `_WS`, `_APOSTROPHE`, `_MD_BOLD` regex definitions with their comment blocks (lines 25-47), the `normalize` function (lines 50-54), and the local `Violation` class (lines 95-99). They now live in `grounding.py` — the comment blocks moved there verbatim in Task 2, with the added note about why they are absent from `VERBATIM_BYTES`.

Add to the imports at the top:

```python
from ..grounding import Profile, Violation, quote_violation
```

Replace the body of `verify_brief` with:

```python
def verify_brief(brief: ResearchBrief, run_id: str) -> list[Violation]:
    """Verify every grounded finding against the page fetched THIS run for its
    source_url. EXTRACTED_TEXT profile: these bytes came out of a third-party
    HTML/PDF extractor, which is what justifies its two loosenings."""
    d = pages_dir(run_id)
    violations: list[Violation] = []
    for f in brief.grounded_findings:
        page = d / page_filename(f.source_url)
        if not page.is_file():
            violations.append(Violation(kind="source_unavailable",
                                        source=f.source_url, quote=f.quote))
            continue
        v = quote_violation(f.quote, page.read_text(encoding="utf-8"),
                            Profile.EXTRACTED_TEXT, source=f.source_url)
        if v is not None:
            violations.append(v)
    return violations
```

In `GroundingViolation.__init__` (line 144), change the message line to use the renamed field:

```python
        lines = "\n".join(
            f"- {v.kind}: {v.source}: {v.quote!r}" for v in violations)
```

Update the module docstring's first paragraph to say the match itself lives in `sdlc/grounding.py` and this module owns the page lookup.

- [ ] **Step 4: Fix the workflow's violation formatting**

In `src/sdlc/workflows/feature.py:1706`, change `v.source_url` to `v.source`:

```python
                err = "; ".join(
                    f"{v.kind}: {v.source}: {v.quote[:80]!r}"
                    for v in violations)
```

- [ ] **Step 5: Run the full research suite**

Run: `python -m pytest tests/ -k "research" -v`
Expected: PASS. Any failure beyond the two renames means the refactor changed behavior it should not have — stop and investigate rather than adjusting the test.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/research/verify.py src/sdlc/workflows/feature.py tests/test_research_verify.py tests/test_research_grounding.py tests/test_research_e2e.py
git commit -m "refactor: research verification delegates to the shared verifier (E-43)"
```

---

## Task 4: `CoverageReport` on `Measurement`

**Files:**
- Modify: `src/sdlc/models.py:566-573`
- Modify: `src/sdlc/activities.py:751-800`
- Modify: `src/sdlc/workflows/feature.py:2152-2161`
- Modify: `tests/test_measure_coverage.py`, `tests/test_analyst_models.py:29-31`, `tests/fakes/fake_activities.py:79-82`

**Interfaces:**
- Consumes: `Measurement`, `CollectionState` (Task 1).
- Produces: `CoverageReport(coverage: Measurement)` — `measured`, `diff_pct` and `detail` are gone. Readers use `report.coverage.state`, `report.coverage.value`, `report.coverage.reason`.

- [ ] **Step 1: Write the failing tests**

Replace the assertions in `tests/test_measure_coverage.py` — every `assert r.measured is False` becomes a state assertion, and the two non-finite cases become `UNKNOWN`. The full replacements:

```python
from sdlc.measurement import CollectionState
```

```python
@pytest.mark.asyncio
async def test_no_artifact_means_not_collected(tmp_path):
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.coverage.state is CollectionState.NOT_COLLECTED
    assert r.coverage.value is None
    assert "coverage.xml" in r.coverage.reason


@pytest.mark.asyncio
async def test_diff_scoped_percentage_over_changed_files(tmp_path):
    (tmp_path / "coverage.xml").write_text(COBERTURA, encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.coverage.state is CollectionState.MEASURED
    assert r.coverage.value == pytest.approx(80.0)
```

`test_no_changed_file_in_report_means_unmeasured`, `test_malicious_xml_degrades_to_unmeasured`, `test_suffix_match_without_path_boundary_is_rejected` and `test_malformed_xml_degrades_to_unmeasured` each replace their `assert r.measured is False` with:

```python
    assert r.coverage.state is CollectionState.NOT_COLLECTED
```

`test_non_finite_line_rate_degrades_safely` and `test_infinite_line_rate_is_skipped` each replace theirs with:

```python
    assert r.coverage.state is CollectionState.UNKNOWN
```

and their docstrings gain a sentence: *"The file parsed and the changed file was present — an attempt produced uninterpretable output, which is `unknown`, not `not_collected`."*

Append a new test:

```python
@pytest.mark.asyncio
async def test_a_measured_zero_is_distinguishable_from_no_measurement(tmp_path):
    """The defect this retrofit exists to fix: 0% coverage on a changed file
    must not look like a coverage run that never happened."""
    zero = """<?xml version="1.0" ?>
<coverage><packages><package name="app"><classes>
  <class filename="app/main.py" line-rate="0.0"/>
</classes></package></packages></coverage>
"""
    (tmp_path / "coverage.xml").write_text(zero, encoding="utf-8")
    r = await measure_coverage(CoverageInput(worktree=str(tmp_path),
                                             changed_files=["app/main.py"]))
    assert r.coverage.state is CollectionState.MEASURED
    assert r.coverage.value == pytest.approx(0.0)
```

In `tests/test_analyst_models.py`, replace `test_coverage_report_unmeasured`:

```python
def test_coverage_report_unmeasured():
    c = CoverageReport(coverage=Measurement.not_collected("no artifact"))
    assert c.coverage.value is None
```

and add `from sdlc.measurement import Measurement` to that file's imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_measure_coverage.py tests/test_analyst_models.py -v`
Expected: FAIL — `ValidationError` / `AttributeError: 'CoverageReport' object has no attribute 'coverage'`

- [ ] **Step 3: Retype the model**

In `src/sdlc/models.py`, add `from .measurement import CollectionState, Measurement` to the imports, and replace `CoverageReport` (lines 566-573) with:

```python
class CoverageReport(BaseModel):
    """Diff-scoped coverage evidence for the advisory `coverage` check.

    FR-915: a non-MEASURED state means the seam could not measure, so the
    advisory check passes as a no-op rather than forcing a spurious human
    override every run. A MEASURED 0.0 is a real zero and is graded as one.
    """
    coverage: Measurement
```

- [ ] **Step 4: Update `measure_coverage`**

In `src/sdlc/activities.py`, replace the four `CoverageReport(...)` returns in `measure_coverage` and add the non-finite tracking. The relevant edits:

```python
    path = os.path.join(inp.worktree, "coverage.xml")
    if not os.path.isfile(path):
        return CoverageReport(coverage=Measurement.not_collected(
            "no coverage.xml (seam not measured)"))
    try:
        root = DET.parse(path).getroot()
    except (DefusedXmlException, DET.ParseError, OSError):
        return CoverageReport(coverage=Measurement.not_collected(
            "coverage.xml unparseable or unsafe"))
    rates: list[float] = []
    skipped_non_finite = 0
```

Inside the class loop, the `isfinite` guard increments the counter instead of silently continuing:

```python
            if not math.isfinite(rate):
                # Hostile/corrupt input (nan, inf) -- never let it propagate
                # into a measured value, where e.g. `nan >= threshold` silently
                # evaluates False and fabricates an advisory failure. An
                # attempt DID produce output, so this is `unknown`, not
                # `not_collected` (FR-915).
                skipped_non_finite += 1
                continue
```

and the two terminal returns become:

```python
    if not rates:
        if skipped_non_finite:
            return CoverageReport(coverage=Measurement.unknown(
                f"{skipped_non_finite} changed-file line-rate(s) non-finite"))
        return CoverageReport(coverage=Measurement.not_collected(
            "no changed file found in coverage.xml (seam not measured)"))
    ...
    pct = sum(rates) / len(rates)
    return CoverageReport(coverage=Measurement.measured(pct))
```

Add `from .measurement import Measurement` to `activities.py`'s imports.

- [ ] **Step 5: Update the gate call site**

In `src/sdlc/workflows/feature.py`, replace the `coverage` check (lines 2152-2161):

```python
            build_check(
                "coverage",
                (True if cov.coverage.state is not CollectionState.MEASURED
                 else cov.coverage.value >= cfg.coverage_threshold),
                CheckClass.ADVISORY,
                detail=(cov.coverage.reason
                        if cov.coverage.state is not CollectionState.MEASURED
                        else f"diff coverage {cov.coverage.value:.1f}% vs "
                             f"threshold {cfg.coverage_threshold:.1f}%")),
```

Add a dedicated line to the workflow's `unsafe.imports_passed_through()` import block (beside `from ..gate import ...` at `feature.py:39`), importing from the pure module rather than relying on a re-export through `models.py`:

```python
    from ..measurement import CollectionState, Measurement
```

Update the fake in `tests/fakes/fake_activities.py`:

```python
@activity.defn(name="measure_coverage")
async def fake_measure_coverage(inp: CoverageInput) -> CoverageReport:
    # No coverage artifact in this offline run -> not collected, check passes.
    return CoverageReport(coverage=Measurement.not_collected("fake: unmeasured"))
```

with `from sdlc.measurement import Measurement` added to that file's imports.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_measure_coverage.py tests/test_analyst_models.py tests/test_integration_checks.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/models.py src/sdlc/activities.py src/sdlc/workflows/feature.py tests/test_measure_coverage.py tests/test_analyst_models.py tests/fakes/fake_activities.py
git commit -m "refactor: CoverageReport carries a Measurement (E-40/FR-915)"
```

---

## Task 5: `SecurityReport` collection state and the gate split

The absolute floor. A malformed SARIF must stop reading as a clean scan.

**Files:**
- Modify: `src/sdlc/models.py:382-389`
- Modify: `src/sdlc/gate.py:57` (`ABSOLUTE_FLOOR`)
- Modify: `src/sdlc/activities.py:741`
- Modify: `src/sdlc/toolchain/sarif.py:71-74`
- Modify: `src/sdlc/workflows/feature.py:2135-2139`
- Modify: `tests/test_security_floor.py`, `tests/test_sarif.py`, `tests/fakes/fake_activities.py:75-76`

**Interfaces:**
- Consumes: `CollectionState` (Task 1).
- Produces: `SecurityReport(critical: int, findings: list[SecurityFinding], state: CollectionState, reason: str)` — `state` is **required**, no default. `report_from_sarif(doc) -> SecurityReport` returns `NOT_COLLECTED` for a malformed document. Two absolute gate checks: `security_scan_collected` and `security_no_critical`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_security_floor.py`, replace `test_security_report_defaults_clean` and append the new floor test:

```python
from sdlc.measurement import CollectionState


def test_security_report_requires_a_collection_state():
    """A report cannot be built without saying whether a scan happened."""
    import pytest as _pytest
    from pydantic import ValidationError
    with _pytest.raises(ValidationError):
        SecurityReport(critical=0)


def test_clean_scan_is_measured():
    r = SecurityReport(critical=0, state=CollectionState.MEASURED)
    assert r.findings == []
    assert r.state is CollectionState.MEASURED


@pytest.mark.asyncio
async def test_regex_scan_always_reports_measured(tmp_path: pathlib.Path):
    """The default path always collects, so this retrofit changes no live
    behavior -- the guard is installed before the semgrep path that would
    trip it."""
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    report = await security_scan(SecurityScanInput(worktree=str(tmp_path)))
    assert report.state is CollectionState.MEASURED
```

In `tests/test_sarif.py`, replace `test_report_from_malformed_is_zero_critical`:

```python
def test_report_from_malformed_is_not_collected_not_clean():
    """The defect: critical=0 from a broken document was byte-identical to a
    clean scan, and security_no_critical is an ABSOLUTE check."""
    from sdlc.measurement import CollectionState
    r = report_from_sarif({"runs": [{"results": "x"}]})
    assert r.state is CollectionState.NOT_COLLECTED
    assert r.critical == 0 and r.findings == []


def test_report_from_well_formed_is_measured():
    from sdlc.measurement import CollectionState
    assert report_from_sarif(WELL_FORMED).state is CollectionState.MEASURED
```

Create `tests/test_security_collection_gate.py`:

```python
"""SC-5's sibling: an absolute floor that could not be measured must not be
silently satisfied."""
from sdlc.gate import (
    ABSOLUTE_FLOOR, CheckClass, build_check, evaluate_quality_gate,
)
from sdlc.measurement import CollectionState
from sdlc.models import SecurityReport


def _checks(report: SecurityReport):
    return [
        build_check("security_scan_collected",
                    report.state is CollectionState.MEASURED,
                    CheckClass.ABSOLUTE, detail=report.reason or "scan ran"),
        build_check("security_no_critical", report.critical == 0,
                    CheckClass.ABSOLUTE,
                    detail=f"{report.critical} critical finding(s)"),
    ]


def test_collection_check_is_in_the_absolute_floor():
    """ABSOLUTE_FLOOR forces the classification regardless of what a caller
    requests. A collection check outside it could be downgraded to advisory
    at a call site, which is the same bypass by another route."""
    assert "security_scan_collected" in ABSOLUTE_FLOOR


def test_a_caller_cannot_downgrade_the_collection_check():
    c = build_check("security_scan_collected", False, CheckClass.ADVISORY)
    assert c.classification is CheckClass.ABSOLUTE


def test_not_collected_scan_blocks_on_its_own_check():
    report = SecurityReport(critical=0, state=CollectionState.NOT_COLLECTED,
                            reason="sarif unparseable")
    result = evaluate_quality_gate(_checks(report))
    assert "security_scan_collected" in result.blocking
    assert "security_no_critical" not in result.blocking


def test_measured_clean_scan_passes_both():
    report = SecurityReport(critical=0, state=CollectionState.MEASURED)
    assert evaluate_quality_gate(_checks(report)).blocking == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_security_floor.py tests/test_sarif.py tests/test_security_collection_gate.py -v`
Expected: FAIL — `SecurityReport` has no `state` field, and `security_scan_collected` is not in `ABSOLUTE_FLOOR`.

- [ ] **Step 3: Add the collection check to the absolute floor**

In `src/sdlc/gate.py:57`:

```python
ABSOLUTE_FLOOR: frozenset[str] = frozenset({
    "security_no_critical",
    # FR-915: "the scan could not run" is as absolute as "the scan found a
    # critical". Outside the floor, a call site could request ADVISORY and
    # reopen the bypass this check exists to close.
    "security_scan_collected",
})
```

- [ ] **Step 4: Add the state to the model**

In `src/sdlc/models.py`, replace `SecurityReport` (lines 382-389):

```python
class SecurityReport(BaseModel):
    """Deterministic scanner evidence for the merge gate's absolute floor
    (FR-106/NFR-5/SC-5).

    FR-915: `state` is REQUIRED and has no default. A producer cannot forget
    to say whether a scan happened, because `critical=0` from a broken scanner
    is byte-identical to `critical=0` from a clean repository -- and the check
    reading this is absolute.
    """
    critical: int
    findings: list[SecurityFinding] = Field(default_factory=list)
    state: CollectionState
    reason: str = ""
```

- [ ] **Step 5: Update the producers**

`src/sdlc/activities.py:741` — the regex scan always collects:

```python
    return SecurityReport(critical=critical, findings=findings,
                          state=CollectionState.MEASURED)
```

`src/sdlc/toolchain/sarif.py` — replace `report_from_sarif` and add the import `from ..measurement import CollectionState`:

```python
def report_from_sarif(doc: dict) -> SecurityReport:
    """A malformed or partial SARIF yields NOT_COLLECTED, never a clean-looking
    zero-critical report (FR-915). findings_from_sarif stays fail-safe-empty:
    a broken scan must not fabricate a blocking finding OR crash the gate --
    but it must also not read as a passing absolute floor."""
    if not _is_well_formed(doc):
        return SecurityReport(critical=0, state=CollectionState.NOT_COLLECTED,
                              reason="SARIF document malformed or partial")
    findings = findings_from_sarif(doc)
    critical = sum(1 for f in findings if f.severity == "critical")
    return SecurityReport(critical=critical, findings=findings,
                          state=CollectionState.MEASURED)


def _is_well_formed(doc: dict) -> bool:
    """A document is well-formed when it has a `runs` list whose every entry
    is a dict carrying a `results` list. Anything else means we did not read a
    scan, whatever findings_from_sarif managed to salvage."""
    if not isinstance(doc, dict):
        return False
    runs = doc.get("runs")
    if not isinstance(runs, list) or not runs:
        return False
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("results"), list):
            return False
    return True
```

Update the fake in `tests/fakes/fake_activities.py`:

```python
@activity.defn(name="security_scan")
async def fake_security_scan(inp: SecurityScanInput) -> SecurityReport:
    return SecurityReport(critical=0, findings=[],
                          state=CollectionState.MEASURED)
```

with `from sdlc.measurement import CollectionState` added to that file's imports.

- [ ] **Step 6: Split the gate check**

In `src/sdlc/workflows/feature.py`, replace the single `security_no_critical` check (lines 2135-2139) with two:

```python
            # FR-915: "the scan found nothing" and "no scan happened" are
            # different facts and get different check names. Conflating them
            # into one compound condition is the exact defect this split
            # exists to prevent, reproduced inside the gate that prevents it.
            build_check(
                "security_scan_collected",
                security.state is CollectionState.MEASURED,
                CheckClass.ABSOLUTE,
                detail=(security.reason or "security scan ran")),
            build_check(
                "security_no_critical", security.critical == 0,
                CheckClass.ABSOLUTE,
                detail=f"{security.critical} critical finding(s)"),
```

- [ ] **Step 7: Run the tests**

Run: `python -m pytest tests/test_security_floor.py tests/test_sarif.py tests/test_security_collection_gate.py tests/test_quality_gate.py tests/test_merge_gate_wiring.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/models.py src/sdlc/gate.py src/sdlc/activities.py src/sdlc/toolchain/sarif.py src/sdlc/workflows/feature.py tests/test_security_floor.py tests/test_sarif.py tests/test_security_collection_gate.py tests/fakes/fake_activities.py
git commit -m "feat: an unmeasured security scan cannot satisfy the absolute floor (E-40/SC-5)"
```

---

## Task 6: Delete `QAReport.coverage_pct`

An LLM-asserted coverage number beside a deterministically measured one is a second registry for one fact.

**Files:**
- Modify: `src/sdlc/models.py:363-372`
- Modify: `tests/fakes/canned.py:51`, `tests/fakes/fake_activities.py:51`
- Check: `agents/qa/instructions.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `QAReport` without `coverage_pct`. Coverage evidence comes from `CoverageReport` only.

- [ ] **Step 1: Verify nothing reads the field**

Run: `git grep -n "coverage_pct"`
Expected: matches only in `src/sdlc/models.py:365`, `tests/fakes/canned.py:51`, `tests/fakes/fake_activities.py:51`. If any other reader appears, stop — the deletion premise is wrong and the field must be retyped to `Measurement` instead.

- [ ] **Step 2: Delete the field**

In `src/sdlc/models.py`, remove the `coverage_pct: float | None = None` line from `QAReport` and add to its docstring:

```python
class QAReport(BaseModel):
    """Clean-context QA evidence for the merge gate.

    Deliberately carries NO coverage number: coverage is measured
    deterministically into CoverageReport (FR-106), and a model-asserted
    figure beside a measured one is a second registry for one fact -- the
    failure mode the agents.yaml / cfg.roles work already paid for once.
    """
```

- [ ] **Step 3: Update the fakes**

`tests/fakes/canned.py:51` → `QA_OK = QAReport(tests_passed=True)`
`tests/fakes/fake_activities.py:51` → `return QAReport(tests_passed=True)`

- [ ] **Step 4: Check the QA role's instructions**

Run: `grep -in "coverage" agents/qa/instructions.md`
If the prompt asks the QA role to report a coverage percentage, delete that clause — the field it would fill no longer exists. If there is no match, no edit is needed.

- [ ] **Step 5: Run the suite**

Run: `python -m pytest tests/ -x -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py tests/fakes/canned.py tests/fakes/fake_activities.py agents/qa/instructions.md
git commit -m "refactor: drop the LLM-asserted QAReport.coverage_pct (E-40)"
```

---

## Task 7: Handoff claims verify their evidence quotes

The first live hole E-43 closes: a fabricated evidence quote currently reaches downstream tasks' prompts.

**Files:**
- Modify: `src/sdlc/handoff.py:26-57`
- Modify: `src/sdlc/workflows/feature.py:1003-1021`
- Modify: `tests/test_handoff_crosscheck.py`

**Interfaces:**
- Consumes: `verify_quote`, `Profile` (Task 2); `Measurement` (Task 1).
- Produces: `CrossCheckResult(kept: list[HandoffClaim], dropped_paths: int, dropped_quotes: int)`; `cross_check_claims(claims, files_touched, session_text: str | None = None) -> CrossCheckResult`; `claim_survival_score(kept: int, dropped: int) -> Measurement`.

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/test_handoff_crosscheck.py`'s tuple-unpacking calls as `CrossCheckResult` attribute access, and add the quote tests. The full new content of the file:

```python
"""The deterministic half of the handoff (spec 2.3) plus E-43 quote
verification.

A claim may only name files the diff actually touched, and its evidence quote
must actually appear in the transcript it was drawn from. The first stops the
extractor attributing a change to a file the task never opened; the second
stops it inventing the quote that supports the claim.
"""
from sdlc.grounding import Profile, verify_quote
from sdlc.handoff import claim_survival_score, cross_check_claims
from sdlc.measurement import CollectionState
from sdlc.models import HandoffClaim

SESSION = "file_write src/app.py\nI'll use cookies here\nfile_write src/app.py"


def test_claim_naming_touched_file_survives():
    claims = [HandoffClaim(text="rewrote src/app.py routing",
                           evidence="file_write src/app.py")]
    r = cross_check_claims(claims, ["src/app.py"])
    assert len(r.kept) == 1
    assert r.dropped_paths == 0 and r.dropped_quotes == 0


def test_claim_naming_untouched_file_is_dropped():
    claims = [HandoffClaim(text="patched src/other.py too",
                           evidence="file_write src/other.py")]
    r = cross_check_claims(claims, ["src/app.py"])
    assert r.kept == []
    assert r.dropped_paths == 1


def test_claim_naming_no_file_survives():
    """Design decisions legitimately mention no path at all."""
    claims = [HandoffClaim(text="chose cookie sessions over JWT",
                           evidence="I'll use cookies here")]
    r = cross_check_claims(claims, ["src/app.py"])
    assert len(r.kept) == 1


def test_path_in_evidence_is_checked_not_only_text():
    claims = [HandoffClaim(text="fixed the parser",
                           evidence="file_write src/ghost.py")]
    r = cross_check_claims(claims, ["src/app.py"])
    assert r.kept == [] and r.dropped_paths == 1


def test_windows_separators_normalise():
    claims = [HandoffClaim(text=r"edited src\app.py",
                           evidence="file_write src/app.py")]
    r = cross_check_claims(claims, ["src/app.py"])
    assert len(r.kept) == 1


def test_evidence_present_in_the_session_survives():
    claims = [HandoffClaim(text="chose cookie sessions over JWT",
                           evidence="I'll use cookies here")]
    r = cross_check_claims(claims, ["src/app.py"], session_text=SESSION)
    assert len(r.kept) == 1
    assert r.dropped_quotes == 0


def test_fabricated_evidence_is_dropped():
    """E-43: today this claim survives and is injected into the next task's
    prompt, carrying a quote nobody said."""
    claims = [HandoffClaim(text="chose cookie sessions over JWT",
                           evidence="I decided to use JWTs after benchmarking")]
    r = cross_check_claims(claims, ["src/app.py"], session_text=SESSION)
    assert r.kept == []
    assert r.dropped_quotes == 1 and r.dropped_paths == 0


def test_claim_with_no_evidence_text_survives():
    """Same rationale as the no-path rule: absence of a quote is not a
    fabricated quote."""
    claims = [HandoffClaim(text="chose cookie sessions over JWT", evidence="")]
    r = cross_check_claims(claims, ["src/app.py"], session_text=SESSION)
    assert len(r.kept) == 1


def test_missing_session_text_skips_quote_verification():
    """Absence of the haystack is not evidence against the quote. If session
    capture failed, dropping every quoted claim would silently empty the
    handoff over an infrastructure failure."""
    claims = [HandoffClaim(text="chose cookies",
                           evidence="nothing like this was ever said")]
    r = cross_check_claims(claims, ["src/app.py"], session_text=None)
    assert len(r.kept) == 1
    assert r.dropped_quotes == 0


def test_path_check_still_applies_when_the_quote_verifies():
    claims = [HandoffClaim(text="patched src/other.py",
                           evidence="file_write src/app.py")]
    r = cross_check_claims(claims, ["src/app.py"], session_text=SESSION)
    assert r.kept == [] and r.dropped_paths == 1


def test_evidence_is_verified_verbatim_not_as_extracted_text():
    """VERBATIM_BYTES: a transcript is bytes we stored, not extractor output."""
    assert not verify_quote("def f(kwargs):", "def f(**kwargs):",
                            Profile.VERBATIM_BYTES)


def test_survival_score():
    assert claim_survival_score(3, 1).value == 0.75
    assert claim_survival_score(4, 0).value == 1.0
    assert claim_survival_score(0, 2).value == 0.0
    assert claim_survival_score(0, 2).state is CollectionState.MEASURED


def test_survival_score_is_not_collected_when_no_claims():
    """No claims is not a score of zero -- nothing was measured."""
    m = claim_survival_score(0, 0)
    assert m.state is CollectionState.NOT_COLLECTED
    assert m.value is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_handoff_crosscheck.py -v`
Expected: FAIL — `ImportError: cannot import name 'CollectionState'` is resolved by Task 1, so the real failures are `AttributeError: 'tuple' object has no attribute 'kept'`.

- [ ] **Step 3: Implement in `handoff.py`**

Replace `cross_check_claims` and `claim_survival_score` in `src/sdlc/handoff.py`, adding the imports `from pydantic import BaseModel`, `from .grounding import Profile, verify_quote`, `from .measurement import Measurement`:

```python
class CrossCheckResult(BaseModel):
    """Kept claims plus the two drop reasons, counted separately: a claim
    naming a file the diff never touched and a claim quoting something nobody
    said are different extractor failures, and the waste metrics should not
    average them together."""
    kept: list[HandoffClaim] = []
    dropped_paths: int = 0
    dropped_quotes: int = 0


def cross_check_claims(
    claims: list[HandoffClaim],
    files_touched: list[str],
    session_text: str | None = None,
) -> CrossCheckResult:
    """Keep claims whose referenced paths are all in `files_touched` AND whose
    evidence quote appears in `session_text`.

    A claim naming NO path survives: design decisions ("chose cookie sessions
    over JWT") legitimately reference no file, and dropping them would discard
    exactly the content the diff cannot supply. A claim with NO evidence text
    survives on the same rationale -- absence of a quote is not a fabricated
    quote.

    `session_text=None` skips quote verification entirely (E-43, spec §5): if
    capture failed there is no haystack, and absence of the haystack is not
    evidence against the quote. Dropping every quoted claim over an
    infrastructure failure would silently empty the handoff, which is a
    delivery failure by another name.

    VERBATIM_BYTES profile: a stored transcript is bytes we wrote, not
    third-party extractor output, so none of EXTRACTED_TEXT's loosenings apply.
    """
    allowed = {_normalise(f) for f in files_touched}
    result = CrossCheckResult()
    for c in claims:
        referenced = _paths_in(c.text) | _paths_in(c.evidence)
        if not referenced <= allowed:
            result.dropped_paths += 1
            continue
        if (session_text is not None and c.evidence.strip()
                and not verify_quote(c.evidence, session_text,
                                     Profile.VERBATIM_BYTES)):
            result.dropped_quotes += 1
            continue
        result.kept.append(c)
    return result


def claim_survival_score(kept: int, dropped: int) -> Measurement:
    """Fraction of claims that survived the cross-check.

    NOT_COLLECTED when there were no claims at all -- nothing was measured,
    and a 0.0 would claim it was (FR-915; waste_matrix.py's rule).
    """
    total = kept + dropped
    if total == 0:
        return Measurement.not_collected("no claims extracted")
    return Measurement.measured(kept / total)
```

- [ ] **Step 4: Update the workflow call site**

In `src/sdlc/workflows/feature.py`, inside `_run_handoff`, replace lines 1003-1018:

```python
            kept_total = 0
            dropped_total = 0
            fields = {}
            for name in ("what_changed", "decisions_made", "open_concerns"):
                checked = cross_check_claims(
                    getattr(out, name), files, session_text=loaded.text)
                fields[name] = checked.kept
                kept_total += len(checked.kept)
                dropped_total += checked.dropped_paths + checked.dropped_quotes

            handoff = HandoffSummary(task_id=task.id, files_touched=files,
                                     **fields)
            await self._record(cfg, self._stage_record(
                cfg, stage="handoff", role="handoff",
                started=_started, ended=workflow.now(),
                # .value is None when no claims were extracted, which is
                # exactly what quality_score must carry -- never a 0.0.
                quality_score=claim_survival_score(
                    kept_total, dropped_total).value,
```

`loaded.text` is the scrubbed session the extractor itself was given, so the haystack is the same bytes the model read. Keep everything else in the record unchanged, including `fix_attempts=0`.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_handoff_crosscheck.py tests/test_handoff_workflow.py tests/test_handoff_role.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/handoff.py src/sdlc/workflows/feature.py tests/test_handoff_crosscheck.py
git commit -m "feat: handoff claims verify their evidence quotes against the session (E-43)"
```

---

## Task 8: Deep-review integrity flags verify their evidence

An anti-cheat accusation whose quote is not in the transcript is worse than no accusation.

**Files:**
- Modify: `src/sdlc/workflows/feature.py:891-906`
- Test: `tests/test_deep_review_flag_verification.py`

**Interfaces:**
- Consumes: `verify_quote`, `Profile` (Task 2).
- Produces: `verified_integrity_flags(flags: list[IntegrityFlag], session_text: str | None) -> tuple[list[IntegrityFlag], int]` in `src/sdlc/handoff.py` — kept flags and the dropped count. It lives beside `cross_check_claims` because it is the same deterministic, pure, session-quote check over a different record type.

- [ ] **Step 1: Write the failing test**

Create `tests/test_deep_review_flag_verification.py`:

```python
"""E-43: an anti-cheat accusation must be able to point at the transcript line
it is accusing. A flag whose quote nobody said is worse than no flag."""
from sdlc.handoff import verified_integrity_flags
from sdlc.models import IntegrityFlag

SESSION = "bash cat oracle/test_app.py\nfile_write src/app.py\n"


def _flag(evidence: str) -> IntegrityFlag:
    return IntegrityFlag(kind="oracle_peeking", detail="read the oracle",
                         evidence=evidence)


def test_flag_quoting_the_session_survives():
    kept, dropped = verified_integrity_flags(
        [_flag("bash cat oracle/test_app.py")], SESSION)
    assert len(kept) == 1 and dropped == 0


def test_flag_quoting_nothing_in_the_session_is_dropped():
    kept, dropped = verified_integrity_flags(
        [_flag("bash curl https://answers.example.com")], SESSION)
    assert kept == [] and dropped == 1


def test_flag_with_empty_evidence_survives():
    """Same rule as handoff claims: absence of a quote is not a fabricated
    quote, and the flag's `detail` still carries signal."""
    kept, dropped = verified_integrity_flags([_flag("")], SESSION)
    assert len(kept) == 1 and dropped == 0


def test_no_session_text_skips_verification():
    kept, dropped = verified_integrity_flags([_flag("never said")], None)
    assert len(kept) == 1 and dropped == 0


def test_empty_flag_list_is_not_an_error():
    assert verified_integrity_flags([], SESSION) == ([], 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_deep_review_flag_verification.py -v`
Expected: FAIL — `ImportError: cannot import name 'verified_integrity_flags' from 'sdlc.handoff'`

- [ ] **Step 3: Implement the helper**

Append to `src/sdlc/handoff.py` (import `IntegrityFlag` alongside `HandoffClaim` from `.models`):

```python
def verified_integrity_flags(
    flags: list[IntegrityFlag],
    session_text: str | None,
) -> tuple[list[IntegrityFlag], int]:
    """Drop deep-review integrity flags whose evidence quote is not in the
    transcript (E-43). Returns (kept, dropped).

    Same three rules as cross_check_claims: an empty quote survives, a missing
    haystack skips verification, and the profile is VERBATIM_BYTES because a
    stored transcript is bytes we wrote.

    This lens NEVER gates, so a dropped flag only reduces what is recorded and
    retained -- it can never fail a task.
    """
    if session_text is None:
        return list(flags), 0
    kept: list[IntegrityFlag] = []
    dropped = 0
    for f in flags:
        if f.evidence.strip() and not verify_quote(
                f.evidence, session_text, Profile.VERBATIM_BYTES):
            dropped += 1
            continue
        kept.append(f)
    return kept, dropped
```

- [ ] **Step 4: Wire it into `_run_deep_review`**

In `src/sdlc/workflows/feature.py`, immediately after the `report = (await self._run_role(...)).output` assignment in `_run_deep_review` (line 896), insert:

```python
            # E-43: an accusation must point at a line the transcript
            # contains. Verified against `transcript`, the same bytes the
            # lens itself read. Dropping, never failing -- this lens must
            # never fail delivery.
            kept_flags, dropped_flags = verified_integrity_flags(
                report.integrity_flags, transcript)
            if dropped_flags:
                workflow.logger.warning(
                    "deep_review: dropped %d integrity flag(s) for task %s "
                    "whose evidence is not in the transcript",
                    dropped_flags, task.id)
            report = report.model_copy(update={"integrity_flags": kept_flags})
```

Because `cheat_detected` is a property over `integrity_flags`, the existing `quality_score`, `outcome` and `_retain` lines below it now read the verified list without further change. Add `verified_integrity_flags` to the existing `from ..handoff import ...` line in the workflow's import block.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_deep_review_flag_verification.py tests/test_deep_review_wiring.py tests/test_deep_review_models.py tests/test_deep_review_agent.py tests/test_deep_review_read.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/handoff.py src/sdlc/workflows/feature.py tests/test_deep_review_flag_verification.py
git commit -m "feat: deep-review integrity flags verify their evidence quotes (E-43)"
```

---

## Task 9: `read_committed_bytes` — the third byte-source

Ships tested and registered, with no caller. E-41 is its consumer.

**Files:**
- Modify: `src/sdlc/activities.py`
- Modify: `src/sdlc/worker.py:30,87` (import and registration lists)
- Test: `tests/test_read_committed_bytes.py`

**Interfaces:**
- Consumes: the existing `_git(args, cwd)` helper (`activities.py:55`).
- Produces: `@dataclass CommittedBytesInput(repo_dir: str, path: str, commit_sha: str)`; `async read_committed_bytes(inp) -> str | None` — the file's text at that commit, or `None` when the path or sha does not resolve. Never raises.

- [ ] **Step 1: Write the failing test**

Create `tests/test_read_committed_bytes.py`:

```python
"""E-43's third byte-source: quote vs. bytes at path@commit_sha.

Ships with no caller -- the assessment stage (E-41) is its consumer. Tested
against real git, because `git show` behaviour on a deleted path is exactly
the case the fail-closed rule depends on.
"""
import subprocess

import pytest

from sdlc.activities import CommittedBytesInput, read_committed_bytes
from sdlc.grounding import Profile, verify_quote


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True,
                          encoding="utf-8", check=True)


@pytest.fixture
def repo(tmp_path):
    _run(["git", "init", "-q"], tmp_path)
    _run(["git", "config", "user.email", "t@example.com"], tmp_path)
    _run(["git", "config", "user.name", "T"], tmp_path)
    (tmp_path / "app.py").write_text("def f(**kwargs):\n    return kwargs\n",
                                     encoding="utf-8")
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "one"], tmp_path)
    first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                           capture_output=True, encoding="utf-8",
                           check=True).stdout.strip()
    (tmp_path / "app.py").unlink()
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "two"], tmp_path)
    second = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                            capture_output=True, encoding="utf-8",
                            check=True).stdout.strip()
    return tmp_path, first, second


@pytest.mark.asyncio
async def test_existing_path_at_a_real_sha_returns_bytes(repo):
    d, first, _ = repo
    text = await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(d), path="app.py", commit_sha=first))
    assert "def f(**kwargs):" in text


@pytest.mark.asyncio
async def test_the_returned_bytes_verify_under_verbatim_profile(repo):
    """The whole point of the source: a quote is checked against these bytes."""
    d, first, _ = repo
    text = await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(d), path="app.py", commit_sha=first))
    assert verify_quote("def f(**kwargs):", text, Profile.VERBATIM_BYTES)


@pytest.mark.asyncio
async def test_deleted_path_at_a_later_sha_returns_none(repo):
    d, _, second = repo
    assert await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(d), path="app.py", commit_sha=second)) is None


@pytest.mark.asyncio
async def test_nonexistent_sha_returns_none(repo):
    d, _, _ = repo
    assert await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(d), path="app.py",
        commit_sha="0" * 40)) is None


@pytest.mark.asyncio
async def test_nonexistent_repo_returns_none_rather_than_raising(tmp_path):
    assert await read_committed_bytes(CommittedBytesInput(
        repo_dir=str(tmp_path / "nope"), path="a.py",
        commit_sha="HEAD")) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_read_committed_bytes.py -v`
Expected: FAIL — `ImportError: cannot import name 'CommittedBytesInput' from 'sdlc.activities'`

- [ ] **Step 3: Implement the activity**

Add to `src/sdlc/activities.py`, beside the other git-backed activities:

```python
@dataclass
class CommittedBytesInput:
    repo_dir: str
    path: str
    commit_sha: str


@activity.defn
async def read_committed_bytes(inp: CommittedBytesInput) -> str | None:
    """E-43/FR-914's third byte-source: the file's content at a pinned commit,
    for verifying a quote against `path@commit_sha`.

    Returns None -- never raises -- when the path or sha does not resolve
    (deleted file, bad sha, not a repository). The caller records a
    `source_unavailable` Violation; fail-closed means "unverified", not
    "crash". Pure read: no checkout, no worktree mutation, so it is
    reproducible across Temporal retries.
    """
    try:
        proc = _git(["show", f"{inp.commit_sha}:{inp.path}"], cwd=inp.repo_dir)
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout
```

- [ ] **Step 4: Register it on the worker**

In `src/sdlc/worker.py`, add `read_committed_bytes` to the import list from `.activities` (line 30 block) and to the registered activities list (line 87 block), keeping both lists alphabetically consistent with their neighbours. Registration is not wiring: no workflow calls it, and E-41 will.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_read_committed_bytes.py tests/test_worker_registration.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/activities.py src/sdlc/worker.py tests/test_read_committed_bytes.py
git commit -m "feat: read_committed_bytes activity for path@sha grounding (E-43)"
```

---

## Task 10: Full-suite verification and roadmap update

**Files:**
- Modify: `ROADMAP.md` §1 (stage 12 note), §2 (FR-914/FR-915 lines), §10 (E-40, E-43)

**Interfaces:**
- Consumes: everything above.
- Produces: no code.

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest tests/ -q`
Expected: PASS with no skips beyond those already skipped on a clean checkout. If anything fails, fix it before touching the roadmap — a green suite is the precondition for claiming the increment landed.

- [ ] **Step 2: Confirm the purity constraint holds**

Run: `python -m pytest tests/test_factory_purity.py -v`
Expected: PASS.

Run: `git grep -n "^from\|^import" src/sdlc/measurement.py src/sdlc/grounding.py`
Expected: only `__future__`, `enum`, `re`, `typing`, and `pydantic`. Any other import violates the global constraint.

- [ ] **Step 3: Update `ROADMAP.md`**

In §10, mark E-40 and E-43 and record what did and did not close:

```markdown
- [ ] ⚠️ **E-40 — `Measurement` type + `RepoTriage` contracts** → FR-915, FR-901.
  *`Measurement` landed (2026-08-06)*: `src/sdlc/measurement.py`, retrofitted
  onto `CoverageReport`, `SecurityReport` and `claim_survival_score`, with
  `QAReport.coverage_pct` deleted as a second registry for a measured fact.
  The roadmap's original framing of the defect was stale — the merge gate
  reads `CoverageReport` (which E-30 had already given a `measured` flag), and
  the live conflation worth fixing was on the **absolute** floor:
  `report_from_sarif` returned `critical=0` for a malformed document. That is
  now `not_collected`, and `security_no_critical` split into
  `security_scan_collected` + `security_no_critical` so an unmeasurable floor
  cannot be silently satisfied. **`RepoTriage` deferred to E-41**, where the
  signals that populate it are designed. FR-915 stays open until then.
- [x] **E-43 — grounding verifier** → FR-914, shares FR-107's implementation.
  *Landed (2026-08-06):* `src/sdlc/grounding.py` owns the one substring
  invariant with **two normalization profiles** — `EXTRACTED_TEXT` (research's
  two documented Tavily loosenings) and `VERBATIM_BYTES` (code and
  transcripts, where `**` and quote glyphs are meaningful). Sharing the
  implementation without sharing the profile is the load-bearing decision.
  Three byte-sources: fetched pages (research, unchanged semantics), stored
  sessions (**two live holes closed** — `HandoffClaim.evidence` and
  `IntegrityFlag.evidence` were model-asserted and unverified), and
  `read_committed_bytes` for `path@sha` (tested, registered, no caller until
  E-41). Also closed a live hole in the shipped research check: an empty quote
  grounded trivially, since `"" in haystack` is True. FR-914 stays open until
  an assessment stage consumes the commit source. **OQ-7 untouched.**
```

In §2, append to the FR-914 and FR-915 lines a pointer to the spec
`docs/superpowers/specs/2026-08-06-measurement-and-shared-grounding-verifier-design.md`
and note that FR-915's contract half landed while the triage half is E-41.

In §1 stage 12, add one sentence: the merge gate now carries a
`security_scan_collected` absolute check beside `security_no_critical`.

- [ ] **Step 4: Commit**

```bash
git add -f ROADMAP.md docs/superpowers/plans/2026-08-06-measurement-and-shared-grounding-verifier.md
git commit -m "docs: record Measurement + shared grounding verifier in the roadmap"
```

**Note on `git add -f`:** `docs/superpowers/` is listed in `.gitignore:10`, but all 75 existing specs and plans are tracked. Follow the established convention rather than the ignore rule.
