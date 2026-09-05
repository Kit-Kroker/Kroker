# Herdr round protocol: five real bugs fixed, and the E-87b scope gap

> **Context.** This session picked up right where
> `2026-08-30-herdr-real-server-findings-and-improvement-plan.md` left off: that doc's §4
> (Claude Code's onboarding wizard) and §5 item 5 (the live-contract test redesign) were the
> known-open items. Fixing the onboarding wizard turned out to be the first of five
> independent bugs stacked on top of each other — each one only became visible once the bug
> in front of it was fixed. All five are now fixed and verified live against a real herdr
> 0.8.2 + Claude Code 2.1.218 server. What's left is not a bug: `herdr-probe`'s `code` stage
> still can't produce a good result, because E-87a's herdr integration has exactly one layout
> ("plan") and it only knows how to produce a planning document, never a code diff. That gap
> is what E-87b needs to close.

## 0. Bottom line

- Every one of tonight's ten `herdr-probe` dispatch attempts failed before this session, and
  the first six of tonight's own attempts *also* failed — each time for a genuinely different
  reason. Five real, independent bugs sat between "a pane opens" and "a round completes":
  an onboarding wizard, a workspace-trust dialog, a silent CLI self-update, an unanswered
  file-write permission prompt, and a race between `agent.prompt` and `agent.wait`. All five
  are fixed, each confirmed by hand against a live pane before being called done.
- With all five fixed, a direct, unassisted `TabDriver.run()` call completed cleanly on the
  **first try** — real deliverable written, valid status file, no manual intervention. That is
  the actual proof the round machine itself now works.
- `herdr-probe`'s own benchmark report still shows `code`/`herdr` failing (`n=3`,
  `cost: n/a`, `quality: 0.000` on the last attempt, down from `n=21` before tonight's fixes).
  This is **not a sixth bug** — it's `herdr/layouts/plan.yaml` being the only layout E-87a
  ships, and it always runs the `planner` skill asking for a `spec.md`, no matter which SDLC
  role (`dev`/`test`/`devops`) invoked `HerdrHarness.run()`. A real dev-task brief (implement a
  FastAPI/SQLite stack, pass pytest) gets wrapped in "write your spec.md" instructions the
  model can't reconcile, and the round ends with nothing written. This is the E-87b gap: §5
  below is the recommended shape for closing it.
- One operational, not-a-bug hazard surfaced along the way: recreating the `worker` container
  while a herdr activity is genuinely mid-flight orphans the live pane (herdr itself isn't
  restarted, so the pane survives, `Blocked`, forever) and the next attempt's `agent.start`
  collides on the reused agent name (`agent_name_taken`). §3 covers it.

## 1. Bugs found and fixed, in the order encountered

Every fix below is small, targeted, and covered by a unit test (`pytest tests/ -k herdr` is
green throughout, plus a new `tests/test_planner_agent_retries.py`). Each was also confirmed
against the real server via `herdr workspace create` / `herdr agent start` / `herdr agent
read` / `herdr agent send-keys`, not inferred from logs alone.

### 1.1 Claude Code's onboarding wizard

**Symptom.** A brand-new `claude` process launched interactively (exactly what `agent.start`
does) shows a theme picker, an API-key confirmation defaulting to "No", and a login-method
select — none of which the round protocol answers, so `agent.prompt`'s text lands on a menu,
never a real chat input.

**Fix** (`scripts/herdr-entrypoint.sh`): on every container boot (this state is per-container,
not on any mounted volume, so it's re-seeded every time, not once):
- `~/.claude.json` pre-seeded with `hasCompletedOnboarding`, `hasTrustDialogAccepted`, `theme`
  — undocumented keys, lifted from a maintained community image
  (`github.com/beevelop/docker-claude`), confirmed live against 2.1.218 (a fresh pane goes
  straight to the real prompt, no theme/login screen).
- The real API key is renamed to `HERDR_ANTHROPIC_API_KEY` and `ANTHROPIC_API_KEY` is
  `unset` before `exec`, so no pane ever inherits it directly — the interactive
  API-key-approval screen is specific to Claude Code detecting that env var
  (`code.claude.com/docs/en/authentication`), and there's no such screen documented for
  `apiKeyHelper`.
- `scripts/herdr-api-key-helper.sh` (new) hands the renamed key back via the documented
  `apiKeyHelper` settings.json key, failing loud (stderr + exit 1) if the var is missing
  rather than handing Claude Code an empty string.

### 1.2 A per-directory workspace-trust dialog

**Symptom.** Fixing 1.1 didn't fully unblock a fresh pane: it still showed "Quick safety
check: Is this a project you created or one you trust?" — a *separate* screen from the
onboarding wizard, tracked per **cwd**, not by any global onboarding flag. Since every herdr
task gets a fresh worktree, this fires on every single pane, not just a container's first
launch.

**Fix** (`src/sdlc/herdr/driver.py:146` `_start_pane`, new `_dismiss_startup_block` at line
209): after the existing readiness `agent.wait`, if `agent_status == "blocked"`, send one
`Enter` via `agent.send_keys` (the default option is already "1. Yes, I trust this folder")
and re-wait for `idle`/`working`, raising loud if it's still blocked. Scoped to `kind ==
"claude"` since only that kind is confirmed to show this dialog.

### 1.3 Claude Code silently self-updating mid-launch

**Symptom.** A diagnostic pane launched with the pinned `CLAUDE_CODE_VERSION=2.1.218` (per the
Dockerfile) showed `Claude Code v2.1.251` and an "Updated to latest" banner within seconds —
the npm-installed CLI auto-updates in the background regardless of install method. This is
almost certainly what made the *first* attempt at fixing 1.2 look like an
`agent_not_found` — the process this session's `agent.start` was tracking got swapped out
mid-launch, racing herdr's own process tracking.

**Fix** (`scripts/herdr-entrypoint.sh`): `"env": {"DISABLE_AUTOUPDATER": "1"}` added to the
same pre-seeded `~/.claude/settings.json` (documented at
`code.claude.com/docs/en/setup#disable-auto-updates`). Confirmed live: a pane launched after
this fix stayed on `v2.1.218` with no update banner.

### 1.4 A file-write permission prompt with no answerer

**Symptom.** This was the big one. With 1.1–1.3 fixed, a pane would correctly load the
`planner` skill, read the brief, and write real content — then sit forever at "Do you want to
create spec.md? 1. Yes / 2. Yes, allow all edits / 3. No". herdr reports the pane as `idle`
the *entire time* it's sitting there (`idle` just means "stopped talking, waiting for input",
which a permission menu satisfies as much as a finished turn), so `_reconcile` read a status
file that was never written and called it `protocol_violation`. **This is the actual reason
every real herdr round failed before tonight** — the first three fixes only got a pane far
enough to reach this screen.

Confirmed by hand: manually pressing `1` for the `spec.md` prompt, then again for the
`status/planner.json` prompt, let one full round complete with a valid deliverable and status
file.

**Fix** (`src/sdlc/herdr/driver.py:159` `_start_pane`): `--permission-mode acceptEdits` added
to the writing pane's `agent.start` args, scoped to `role.writes` (least privilege — a
non-writing pane has no edits to pre-approve). `acceptEdits` auto-approves file writes and
common filesystem commands while still gating other Bash/network calls behind
`--allowedTools`/`permissions.allow` — the narrowest mode that unblocks a writing pane's own
job.

### 1.5 `agent.prompt` + separate `agent.wait` race — the real root cause

**Symptom.** Even after 1.1–1.4, most rounds *still* failed: `agent.prompt` would return
`ok`, and **~65–150ms later** `tab.close` would fire — far too fast for any real generation.
The pane's cost record showed real output tokens from a *different*, stale session file
(`_session_file`'s newest-file-wins glob silently misattributes an old file's cumulative
totals when the current pane never wrote its own transcript at all — a related, secondary
finding: the probe should refuse to attribute a file whose mtime predates the round it's
costing, rather than silently reusing ancient data).

**Root cause, confirmed via `herdr agent prompt --help`:** plain `agent.wait` has no concept
of "since this submission" — if the pane is *already* idle (it always is, right after
`agent.start`'s own readiness wait), a *separate* `agent.wait(until=["idle",...])` issued
right after `agent.prompt` matches that **pre-existing** idle status immediately, before the
model has done any work. herdr's own CLI documents the fix directly: `agent.prompt --wait`
*"requires an observed state CHANGE"* within a grace window, returning
`agent_prompt_stalled` otherwise if none occurs.

**Fix** (`src/sdlc/herdr/driver.py:331` `run`): merged the two calls into one atomic
`agent.prompt` request carrying its own `wait: {until, timeout_ms}` field, per herdr's
documented pattern. `agent_prompt_stalled` is translated to the same `"timeout"` status the
round machine already handles.

**Verification:** a direct `TabDriver.run()` call against a fresh worktree, no manual
intervention, completed on the first try:

```json
"outcome": "done",
"deliverable_text": "{\"schema\": \"spec-v1\", \"message\": \"hello\"}\n"
```

## 2. A secondary, unrelated bug fixed along the way: planner output retries

Not a herdr bug — it blocked `herdr-probe` from ever reaching the `code` stage on two
attempts, so it's recorded here too. `agents/planner/agent.py` relied on pydantic_ai's
default output-retry budget (1). `anthropic:glm-5.2`'s `ImplementationPlan.tasks` array (a
long run of near-identical `DevTask` objects) reliably filled the first task's `description`
correctly, then dropped it on every task after — a validated pattern-completion degradation
on repeated structured output. A budget of 1 spends its only attempt on that first,
uncorrected response. **Fixed** by widening to `retries={"output": 3}`, scoped to `output`
only since tool-call retries weren't the failure mode. Pinned by
`tests/test_planner_agent_retries.py`.

## 3. Operational hazard: recreating the worker mid-flight orphans a pane

Not a bug in the fixes above — a real trap hit twice tonight while iterating. `herdr` and
`worker` are separate containers; recreating `worker` (`docker compose up -d
--force-recreate worker`) does not restart `herdr`. If a `run_coding_task` activity is
genuinely mid-flight when `worker` is killed, the Python coroutine running `TabDriver.run()`
never reaches its own `finally: await self._teardown()` — the container is gone, not
cancelled — and the live pane it opened is orphaned inside `herdr`, staying `Blocked`
indefinitely. The next attempt's `agent.start(name="planner", ...)` then fails with
`agent_name_taken`, since herdr tracks agent names globally, not per workspace.

`driver.py`'s own comment already names this as a known gap: *"E-87a has no orphan
sweeper... every ending nobody enumerated... leaked a tab and its billed CLI processes
forever."* Tonight's specific trigger (rebuilding `worker` mid-run) is a new way to hit an
already-known class of problem. Recovery is manual and cheap: `herdr workspace list` to find
the stray tab, `herdr tab close <tab_id>`. See §5 item 4.

## 4. The remaining gap: E-87a is planning-only

With all five bugs fixed, `herdr-probe`'s own `code`/`herdr` row went from `n=21` (every
attempt dying at bootstrap) to `n=3` (every attempt completing a real round, still scored
0) — the fix_attempts budget, not an infra failure, is what stopped it at 3.

The reason: `HerdrHarness.run()` (`src/sdlc/herdr/adapter.py`) always drives
`herdr/layouts/plan.yaml` — the only layout E-87a ships — regardless of which SDLC role
called it. That layout's lead role is `planner` (`herdr/roles/planner.yaml`, skill
`planner`), and `_round_brief` always tells the pane to write a `spec.md` matching schema
`spec-v1`. When the `dev` role's real task brief comes through instead (confirmed against a
live worktree):

```
MANDATORY STACK (do not deviate, even when revising): Python 3.11+ / FastAPI, SQLite
(stdlib sqlite3), pip, pytest
Previous attempt has issues. Fix them:
- Empty diff: no implementation was provided...
- critical: script creates app.db containing a users table with columns username,
  password_hash, salt, iterations...
```

— the pane receives a real coding brief wrapped inside "write your spec.md using the
planner skill" instructions. The two are irreconcilable: the model isn't a planner being
asked to plan, it's a dev being asked to plan *about* code it was also asked to write. Every
observed attempt spent real tokens (500–7000+ output tokens per round, real generation, not a
crash) but never created a `round-N/` directory or a status file at all — not a timeout, not
a permission block, just no coherent completion.

This exactly matches what this session's own earlier research concluded before any of the
above bugs were touched: E-87a's herdr integration is a **planning-stage substitute**, not a
dev/test/devops-capable harness. `herdr-probe`'s case design (routing `dev`/`test`/`devops` at
`herdr:claude-opus-5`) asks it to do the latter. Fixing the five bugs above was necessary —
without them, `herdr-probe` never got far enough to *reveal* this gap, it just failed at the
door. It was not sufficient to close the gap itself, and nothing at the driver/protocol layer
could close it: the gap is in what the layout tells the pane to produce.

## 5. Recommended next steps for E-87b, in priority order

1. **Give herdr a real coding layout**, not just `plan`. At minimum, a `code` layout whose
   lead role's skill actually produces a diff against the worktree (edit real files, not a
   `spec.md`) and whose `_round_brief`-equivalent passes the *actual* task brief through
   verbatim rather than wrapping it in planning instructions. `HerdrHarness.run()` needs to
   select the layout by something derived from the calling role (or `HarnessRequest` itself),
   not hardcode `"plan"`.
2. **Fix the cost probe's stale-file misattribution** (§1.5's secondary finding):
   `_session_file` should refuse to attribute a file whose mtime predates the round's own
   start, and fail loud (`CostProbeError`) rather than silently charging an unrelated
   session's totals to a round that never wrote its own transcript. This would have made
   tonight's diagnosis much faster — several hours were spent on transcripts that turned out
   to belong to an earlier, unrelated pane.
3. **Redesign `test_herdr_live_contract.py`** (still open from the prior doc, and more true
   than ever now): five real drift/behavior bugs shipped between the last time this test ran
   green and tonight, and it caught none of them because its echo-pane substitution doesn't
   work against `agent.start`'s native-kind launch. A redesigned version — even just
   asserting a real pane reaches `idle` with a real chat prompt showing, no manual
   intervention — would have caught 1.1–1.4 automatically.
4. **An orphan sweeper**, or at minimum a documented recovery runbook for §3: `herdr
   workspace list` + close, on worker startup, so a bad container recreate during
   development doesn't require manual cleanup before the next run.
5. **Revisit `kroker-pane`** (`scripts/kroker-pane`): confirmed fully vestigial for both of
   E-87a's harnesses now that native `agent.start` detection covers `claude_code` and
   `opencode` — worth deleting rather than carrying dead code, unless E-87b's own new layout
   needs a non-natively-detected `kind` (in which case it's the one thing kroker-pane still
   does that `agent.start` can't).
6. **Thread the real per-role activity timeout into `CodingTaskInput`** (carried over from
   the prior doc's §2.5, still not fixed, still affects every harness): `req.timeout_s`
   defaults to a constant disconnected from the real Temporal `start_to_close_timeout`, and
   `herdr/layouts/plan.yaml`'s `wall_clock_s: 3000` is a workaround, not a fix, for that
   mismatch.
