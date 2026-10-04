# Skeptic brief 2 — research-partial-salvage (draft 2)

Role contract: adversarial review only — read tools, no edits to the repo,
no commits. Write your full answer to
`.workspace/tmp/research-partial-salvage-skeptic-2.md` and reply in the
pane with only that path.

Your first kill-case changed the draft. Read `decision.md` (draft 2,
"What changed since draft 1"), `concept.md` (Options B and D are new or
rewritten), and `research.md` sections "E7b" and "Skeptic kill-case 1 —
what was upheld". The new experiment is
`experiments/e7b_reserve_last_request_hook.py`.

Draft 2's verdict has three parts:

1. **kill** after-the-fact salvage (no reopening condition any more);
2. **needs-clarification** on "conclude on the last request" (Option D),
   blocked on one live check E8;
3. **go, small** on "keep findings when synthesis fails, verify, fall
   back to today's brief on any violation" (Option B, now workflow code
   behind a patch marker).

## Make the kill-case again, on what is new

1. **Part 3 (Option B as rewritten).** Is "never worse than today, by
   fallback" actually true? Walk `step.py:254-303` and say what the
   command sequence is on each path under a patch marker: synthesis
   fails → merge → verify clean; synthesis fails → merge → violations →
   fallback. Does the fallback need a second verify call? Does calling
   `merge_briefs` in workflow code break anything in the sandbox? Is M
   still honest for this, or is it now bigger than its value?
2. **Part 2 (Option D).** Attack the mechanism and the claim that it
   "costs clean runs nothing". Check `pydantic_ai/usage.py:532-534` and
   the E7b script. What does the hook do on the architect's call path
   (`toolset.py:50-70`)? Is the residual (a forced-turn brief with a bad
   quote fails the stage) bad enough that needs-clarification should be
   kill? Is the proposed live check E8 able to answer the question, and
   is its pass criterion ("verifies in most repetitions") too soft?
3. **Points where I did not uphold you** (research.md S3, S7, S8): say
   if I am wrong, with where you checked.
4. **Verdict you would give** for each of the three parts, one line each,
   and the one change that would move you on each.

Keep it short: findings first, each with where you checked.
