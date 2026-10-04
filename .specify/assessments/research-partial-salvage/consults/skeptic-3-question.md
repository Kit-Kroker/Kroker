# Skeptic brief 3 — research-partial-salvage (part 2 as revised)

Role contract: adversarial review only — read tools, no edits to the repo,
no commits. Write your full answer to
`.workspace/tmp/research-partial-salvage-skeptic-3.md` and reply in the
pane with only that path.

Scope: **part 2 only** — "conclude on the last request" (concept.md,
Option D) as revised after your second pass. Parts 1 and 3 are not under
review here.

Read: `concept.md` Option D (the "Risk, and its answer" bullet, the rabbit
holes, and "The live check D waits on (E8)"); `decision.md` sections
"What changed since draft 1" (second list), "Where the skeptic and I
differ", and "If needs-clarification (part 2)"; `research.md` "Skeptic
kill-case 2 — what was upheld" (T1–T3) and "E7b". Check claims in code
(`src/sdlc/stages/research/`, `agents/research/`) before accepting them.

## What changed in response to your pass 2

1. **Self-check with fallback.** When a sub-question run ends on its
   conclude-only last turn, the sub-question activity checks that brief
   against the fetched pages before returning it; on any violation it
   returns exactly today's gap-only result. All or nothing: no finding is
   filtered or demoted. Briefs from runs that conclude on their own are
   not self-checked.
2. **E8 pass criterion restated.** Ten repetitions of one real
   sub-question on the production model, low request limit. Pass: at
   least five of ten conclude with every quote verifying. The claim is
   that with the self-check this threshold measures value, not safety.
3. **Inert without a limit.** The mechanism does nothing unless the
   sub-question run hands it a limit, so the architect's call path
   (`toolset.py:50-70`) is unaffected.

## Make the kill-case on the revised option

1. **Does the self-check close the residual you named (T1)?** Is "a
   forced turn can never cause a stage grounding failure that today's
   code would not" true? Look for paths where it is not: how the activity
   knows the run ended on the forced turn; output retries on or after
   that turn; the re-fetch race between the self-check and the stage's
   own verify (`verify.py`, `step.py:273-298`); pages written by a
   sibling; anything about calling `verify_brief` inside the sub-question
   activity.
2. **Is all-or-nothing fallback consistent with the grounding rule**, or
   is it a softening by another name (BENCHMARK.md OQ-B3)? It hides a
   violation that a self-concluding run would have been failed for.
3. **Is ">= 5 of 10" a sound threshold** given the self-check, or does it
   still need to be tighter / differently defined? Is one sub-question
   and one low limit (6) representative of a 40-request history? What
   would you require E8 to record?
4. **Is "inert without a limit" enough** for the architect path and for
   replay / serialized-deps byte-identity?
5. **Anything else new** that makes the revised option worse than
   gap-only, or bigger than its value.
6. **Verdict on part 2 as revised**: go / needs-clarification / kill, in
   one line, and the one change that would move you.

Keep it short: findings first, each with where you checked.
