# Skeptic brief 1 — research-partial-salvage (draft decision)

Role contract: adversarial review only — read tools, no edits to the repo,
no commits. Write your full answer to
`.workspace/tmp/research-partial-salvage-skeptic-1.md` and reply in the
pane with only that path.

Read: `.specify/assessments/research-partial-salvage/decision.md` (draft
1), then `concept.md`, `problem.md`, `research.md`. Experiments are in
`experiments/`. Treat every claim as a hypothesis and check it in code
(`src/sdlc/stages/research/`) before accepting it.

## Your job: make the kill-case

The draft is a split verdict:

- **kill for now** on sub-question salvage (the register row as titled);
- **go, small** on keeping finished findings when synthesis fails
  (concept Option B), plus naming the real cause in gaps.

Attack both halves.

1. **Kill-case against the go.** Argue that Option B should not be built.
   In particular:
   - Is the claimed loss real? Check `step.py:254-271` and whether a
     synthesis failure can actually happen after 3 attempts in a way the
     activity can see.
   - Is "replay-safe inside the existing synthesis activity on its last
     attempt" true? What does the activity need to know, and what breaks?
   - Is "no pre-filter, verify once" a regression against today's
     always-passes degraded brief? Is it honest to call that the same
     exposure as a clean run?
   - Does keeping `findings` really fix the refine-round id collision
     (`step.py:318`, `AGENTS.md:49-54`), or did I assert it?
   - Is the cause-string change really free of replay risk?
   - Is M the right size, or is this two unrelated changes glued together?
2. **Kill-case against the kill.** Argue that declining sub-question
   salvage is wrong or lazy:
   - Is "cannot measure without a live call" true, or is there a cheaper
     check I skipped?
   - Did I dismiss "reserve the last request" (E7) or "record findings as
     you go" too quickly?
   - Is the reopening condition one that can ever be met, or a polite
     never?
3. **Facts.** Any claim in research.md you find wrong in code, with
   file:line. Especially M1–M7, A1–A7, and E7's reading.
4. **Verdict you would give**: go / needs-clarification / kill for each
   half, in one line each.

Keep it short: findings first, each with where you checked.
