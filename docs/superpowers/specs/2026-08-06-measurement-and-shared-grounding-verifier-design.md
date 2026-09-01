# Measurement and Shared Grounding Verifier — Design

| | |
|---|---|
| Date | 2026-08-06 |
| Work items | **E-40** (partial — `Measurement` only), **E-43** |
| Requirements | FR-915, FR-914; touches FR-106, SC-5, SC-7 |
| Scope input | `docs/superpowers/specs/2026-07-25-brownfield-assessment-and-outcome-measurement-design.md` §4, §10; `ROADMAP.md` §10, §14 |
| Status | Approved design, not yet implemented |

The two invariants ROADMAP §14 ranks first: *a value that was never measured must
not be representable as a measured value*, and *no claim may be labelled grounded
unless its quote is verbatim in the bytes it cites*. Both land in existing code
paths and both improve the current pipeline on their own.

---

## 1. What the code actually looks like today

Three corrections to the roadmap's framing, established by reading the code
before designing against it.

**The roadmap's stated E-40 defect is stale.** ROADMAP §10 says
`QAReport.coverage_pct: float | None` leaves the advisory coverage check unable
to distinguish a measured zero from a never-measured value. It does not: the
merge gate reads `CoverageReport` (`models.py:566`), which E-30 already gave a
`measured: bool` + `detail` discipline, and `measure_coverage`
(`activities.py:751`) already returns `measured=False` with a reason on every
failure path. `QAReport.coverage_pct` is an LLM-asserted field that **nothing
reads** — its only occurrences are its declaration (`models.py:365`) and two test
fakes.

**The sharper instance is on the absolute floor.** `report_from_sarif`
(`toolchain/sarif.py:71`) returns `SecurityReport(critical=0, findings=[])` for a
malformed, truncated, or partial SARIF document — byte-identical to a clean scan.
`security_no_critical` is the **absolute** SC-5 check, and it asks
`security.critical == 0`. A broken scanner therefore reads as a passing security
floor. This is latent, not live: nothing shells semgrep today, and the default
regex `security_scan` always collects. Latent is exactly the condition under
which the guard is cheap to install.

**The verifier's shareable core exists but is not factored out.**
`research/verify.py:50` `normalize()` plus the substring test *is* the invariant;
what is research-specific is only where the bytes come from (`pages_dir`,
`page_filename`).

**Two live consumers already carry unverified model-asserted quotes.**
`HandoffClaim.evidence` (`models.py:272`) is documented as a quote from the
scrubbed `HarnessSession`, and `handoff.py:cross_check_claims` verifies only that
*paths* named in a claim appear in the diff — the quote itself is never checked,
and a surviving claim is injected into downstream tasks' prompts.
`IntegrityFlag.evidence` (`models.py:417`) has the same gap for the E-39
deep-review lens: an anti-cheat accusation whose supporting quote is unverified.

So E-43 is not, as the roadmap assumes, an invariant with no consumer until
assessment exists. It has two today.

## 2. Decisions

Recorded with the alternatives, because each was a real fork.

**D1 — Retrofit the live contracts, do not merely add a type.** The alternatives
were a contracts-only increment (define `Measurement` for the future triage tier,
touch nothing) and a literal reading (retype `coverage_pct` and stop). Both leave
§14's argument for doing E-40 now — "improves the current pipeline on its own" —
untrue, and neither closes the SARIF hole while it is still free to close.

**D2 — `RepoTriage` defers to E-41.** The roadmap titles E-40 "`Measurement` type
+ `RepoTriage` contracts", but nothing produces a `RepoTriage`: the hygiene
signals (E-41) and the workflow and readiness gate (E-42) are both unstarted. A
contract designed with no producer gets rewritten by its first producer.
`Measurement` — the part E-41 actually needs from E-40 — lands here.

**D3 — Replace, no compatibility shim.** Old field shapes are removed rather than
deprecated alongside new ones. A field that still exists still gets read. This
breaks replay of in-flight runs and invalidates stored records carrying these
shapes; that cost was accepted for this repo.

**D4 — Non-generic `Measurement` plus a shared `CollectionState`.** A generic
`Measurement[T]` has exactly one real instantiation (`float`, twice); the third
site is not a value at all but a collection state over a list. Two shapes,
because there are honestly two: *a number we may not have*, and *a collection
that may not have happened*.

**D5 — Pure verifier core, per-consumer byte lookup.** A `QuoteSource` protocol
with three implementations was considered and rejected: all consumers already
hold their own bytes, so the protocol would unify a lookup nobody shares. A
single `verify_claims` Temporal activity with a source discriminator was rejected
for forcing every consumer across an activity boundary to do a substring match.

**D6 — Normalization is per-source, not global.** This is the most important
decision in the spec. `research/verify.py:36-47` strips apostrophe glyphs and
markdown `**` markers, each justified by a specific documented Tavily extraction
bug. Applying that profile to source code would be an unjustified loosening:
`**` is meaningful in Python (`**kwargs`, exponentiation) and quote glyphs are
meaningful in string literals. Sharing the implementation *without* sharing the
profile is the whole trick — sharing the profile would silently weaken the
code-side check that SC-7 rests on.

**D7 — The verifier never decides consequences.** It returns a verdict. The
disposition belongs to the consumer, which is what lets one implementation serve
a gating stage and a non-gating lens without either policy leaking into the
other (§6).

## 3. Architecture

Two new pure modules. No new stage, no new workflow, one new (unwired) activity.

```
src/sdlc/measurement.py    NEW  Measurement, CollectionState. Pure.
src/sdlc/grounding.py      NEW  verify_quote, normalize, Profile, Violation. Pure.
src/sdlc/research/verify.py     keeps pages_dir/page_filename/brief_digest/
                                verify_brief_activity; delegates the match.
src/sdlc/handoff.py             cross_check_claims verifies quotes;
                                claim_survival_score returns Measurement.
src/sdlc/models.py              CoverageReport, SecurityReport, QAReport retrofit.
src/sdlc/toolchain/sarif.py     report_from_sarif -> not_collected on malformed input.
src/sdlc/activities.py          measure_coverage/security_scan emit states;
                                NEW read_committed_bytes (tested, unwired).
src/sdlc/workflows/feature.py   merge-gate check construction.
```

`measurement.py` imports only Pydantic; `grounding.py` only stdlib and Pydantic.
Neither imports `models.py`. A future workflow dependency in either module
therefore appears as a reviewable import rather than as drift.

## 4. Contracts

```python
# measurement.py
class CollectionState(StrEnum):
    MEASURED = "measured"
    NOT_COLLECTED = "not_collected"  # we did not or could not measure
    UNKNOWN = "unknown"  # we tried; the result is uninterpretable


class Measurement(BaseModel):
    state: CollectionState
    value: float | None = None
    reason: str = ""
    # model_validator enforces:
    #   value is not None      <=>  state is MEASURED
    #   state is not MEASURED  =>   reason is non-empty
```

The validator is the mechanism. `Measurement(state=NOT_COLLECTED, value=0.0)` and
`Measurement(state=MEASURED)` both raise. A measured zero and a never-measured
value stop being the same object because they stop being *constructible* as the
same object. `not_collected` versus `unknown`: no `coverage.xml` is
`not_collected`; a `coverage.xml` that parses but yields a non-finite rate is
`unknown`. The distinction is whether an attempt produced output; both require a
reason.

**Retrofits:**

| Site | Before | After |
|---|---|---|
| `CoverageReport` | `measured: bool`, `diff_pct: float \| None`, `detail: str` | `coverage: Measurement` (`detail` folds into `reason`) |
| `SecurityReport` | `critical: int`, `findings: list` | adds `state: CollectionState`, `reason: str` |
| `QAReport.coverage_pct` | `float \| None` | **deleted** |
| `handoff.claim_survival_score()` | `-> float \| None` | `-> Measurement` |

`claim_survival_score` returns `MEASURED` with the surviving fraction in `[0,1]`
when at least one claim was cross-checked, and `NOT_COLLECTED` with reason
`"no claims extracted"` when there were none — which is the rule its current
docstring already argues for by hand (`handoff.py:49-57`).

`QAReport.coverage_pct` is deleted rather than retyped. An LLM-asserted coverage
number beside a deterministically measured one is a second registry for one fact
— the failure mode the `agents.yaml` / `cfg.roles` work already paid for once
(ROADMAP §9.1, `2026-07-16-registry-drives-every-role`). Nothing reads it.

## 5. The verifier

```python
# grounding.py
class Profile(StrEnum):
    EXTRACTED_TEXT = "extracted_text"    # third-party extractor output (research)
    VERBATIM_BYTES = "verbatim_bytes"    # committed code, stored transcripts

class Violation(BaseModel):
    kind: Literal["quote_not_found", "source_unavailable", "quote_empty"]
    source: str          # url | "path@sha" | session id
    quote: str

def normalize(text: str, profile: Profile) -> str
def verify_quote(quote: str, haystack: str, profile: Profile) -> bool
```

| Normalization | `EXTRACTED_TEXT` | `VERBATIM_BYTES` |
|---|---|---|
| whitespace runs collapse to one space | yes | yes |
| apostrophe / `U+FFFD` glyph strip | yes | no |
| markdown `**` strip | yes | no |
| case preserved, other punctuation preserved | yes | yes |

Both `EXTRACTED_TEXT` loosenings move across carrying their documented Tavily
false-failure comments (`research/verify.py:27-47`) and gain a line recording why
they are *not* in the other profile (D6). Whitespace collapse is in both, because
transcripts and prompt-rendered code get re-wrapped and re-indented; the
consequence — an indentation-only difference is not detected — is acceptable
because the question is "did this text appear", not "is this valid code".

**`quote_empty` closes a live hole.** Today `"" in haystack` is `True`, so a
grounded finding with an empty quote verifies trivially in the shipped research
check. A quote that normalizes to empty is a violation. No minimum length beyond
that: an arbitrary threshold invents false failures, and the existing path and
diff cross-checks cover the rest.

**Rename:** `source_never_fetched` becomes `source_unavailable`. The shared type
serves three byte-sources and only one of them fetches.

**Byte-sources and consumers:**

1. **Research** (live, unchanged semantics) — `verify_brief` keeps `pages_dir` /
   `page_filename` and delegates the match. `EXTRACTED_TEXT`.
2. **Handoff** (live, currently unverified) — `cross_check_claims` takes the
   scrubbed session text as a parameter and verifies each `HandoffClaim.evidence`
   against it under `VERBATIM_BYTES`, in addition to today's path check. It
   returns `CrossCheckResult(kept, dropped_paths, dropped_quotes)` instead of a
   two-tuple, so the two drop reasons stay distinguishable in the waste metrics.
3. **Deep review** (live, currently unverified) — `IntegrityFlag.evidence`
   verified against the same scrubbed session text; unverifiable flags are
   dropped before the report is recorded or retained.
   **When the session text is unavailable** (capture failed, or the artifact
   cannot be loaded), consumers 2 and 3 fall back to today's behavior — path
   cross-check only, quote verification skipped, recorded as skipped. Dropping
   every quoted claim because the *haystack* is missing would punish claims for
   an infrastructure failure and would silently empty the handoff, which is a
   delivery failure by another name (§6, row 2). Absence of the haystack is not
   evidence against the quote.

4. **Assessment** (unwired) — `read_committed_bytes(repo_dir, path, commit_sha)
   -> str | None`, a `git show <sha>:<path>` activity. Ships with tests and no
   caller; E-41 is its consumer. It is the only genuinely new byte-source, and it
   is I/O, so it cannot live in the pure module.

## 6. Failure semantics

`verify_quote` returns a verdict and never decides consequences (D7).

| Consumer | On violation | Why |
|---|---|---|
| research grounded findings | stage `FAIL`, run continues | E-29's fail-and-continue decision, unchanged |
| handoff claims | claim **dropped**, counted | lenses must never fail delivery (global constraint, `2026-08-05-verified-handoff-and-decorrelated-verdict`) |
| deep-review integrity flags | flag **dropped**, counted | advisory lens, never gates; an accusation whose quote is not in the transcript is worse than no accusation |
| assessment findings (E-41) | fail-closed, hard | SC-7 — one violation is a defect, not a percentage |

Four dispositions, one implementation.

**Gate consequence — the one behavioral change.** `security_no_critical` asks
`security.critical == 0`, which a `not_collected` report satisfies. It splits
into two absolute checks:

- `security_scan_collected` — `state is MEASURED`
- `security_no_critical` — `critical == 0`

Conflating them into one compound condition would reproduce this spec's own
defect inside the gate it is fixing. "The scan found nothing" and "no scan
happened" are different facts, and they get different check names, different
details, and different heatmap cells.

Live behavior is unchanged today: the default regex `security_scan` always
collects, so `state` is always `MEASURED`. The guard is installed before the
semgrep path that would trip it.

The advisory `coverage` check keeps today's semantics — a non-`MEASURED` state
passes as a no-op, so an unbuilt measurement still never forces a spurious human
override.

**`Measurement` error paths.** `measure_coverage` returns `NOT_COLLECTED` (no
`coverage.xml`, unparseable or unsafe XML, or no changed file present in it) or
`UNKNOWN` (parsed, but the rate is non-finite — today's silent `continue` at
`activities.py:783` becomes visible). `report_from_sarif` returns `NOT_COLLECTED`
with the parse reason instead of a clean-looking empty report.
`read_committed_bytes` returns `None` rather than raising; the caller records
`source_unavailable`.

## 7. Testing

Both new modules are pure, so nearly everything is unit-testable without
Temporal.

**`measurement.py`** — the validator is the contract, so it gets the adversarial
cases: `MEASURED` without a value raises; `NOT_COLLECTED` with a value raises;
any non-`MEASURED` state without a reason raises. Plus the case the item exists
for: `Measurement(MEASURED, 0.0)` and `Measurement(NOT_COLLECTED, reason=...)`
are unequal, and remain unequal after a JSON round-trip.

**`grounding.py`** — a table test over (quote, haystack, profile). Load-bearing
cases: the two documented Tavily false-failures pass under `EXTRACTED_TEXT` and
**fail** under `VERBATIM_BYTES` (the assertion that stops the profiles being
quietly merged later); `**kwargs` in code verifies under `VERBATIM_BYTES` and is
corrupted by the other profile; empty and whitespace-only quotes yield
`quote_empty`; re-indented code verifies.

**Research regression** — the existing research verification tests pass unchanged
against the refactored implementation, modulo the `source_never_fetched` →
`source_unavailable` rename. Any test needing an edit beyond that rename means
the refactor changed behavior it should not have, and is the signal to stop.

**Gate** — a `SecurityReport` arriving `NOT_COLLECTED` with `critical=0` fails
`security_scan_collected`, terminates the run absolute, and never reaches
`deployed:`. Belongs beside `tests/test_security_floor.py`.

**Handoff and deep review** — a claim whose evidence quote is absent from the
session is dropped and counted in `dropped_quotes`; a claim whose evidence is
present survives; a claim carrying no quote at all survives, on the same
rationale as today's no-path-mentioned rule. Neither lens raises on any input.

**`read_committed_bytes`** — real git in a temporary repository: an existing path
at a real sha returns bytes; a deleted path at a later sha returns `None`; a
nonexistent sha returns `None`; it never raises.

## 8. Out of scope

- `RepoTriage`, the readiness verdict, and hygiene signals — E-41 / E-42 (D2).
- Wiring `read_committed_bytes` to any caller.
- Shelling semgrep. `sarif.py` stays a normalizer; this spec fixes only what it
  returns on malformed input.
- **OQ-7** (inline per-finding verification versus a batch gate before storage) —
  an assessment-stage question. All four consumers here verify inline against
  bytes they already hold.
- Any change to `check_adr6_families`, to the research grounding policy (E-29),
  or to the advisory `coverage` check's pass semantics.

## 9. Roadmap effects

On landing, `ROADMAP.md` should record:

- **E-40** partially closed — `Measurement` landed and retrofitted; `RepoTriage`
  moved to E-41 (D2). FR-915 remains open until triage contracts exist.
- **E-43** closed for the pipeline's live consumers; FR-914 remains open until an
  assessment stage consumes `read_committed_bytes`.
- §10's characterisation of the E-40 defect corrected per §1 above.
