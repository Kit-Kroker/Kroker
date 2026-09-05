# Herdr vs. a real server: findings and improvement plan

> **Context.** E-87a's driver, client, and Docker image were built and unit-tested against
> fakes and an assumed herdr API surface, but the "live contract test" (Task 15) that was
> supposed to catch drift against a *real* herdr server was never actually run with a real
> agent CLI before tonight — only the echo-pane path. This session rebuilt the Docker stack,
> ran the driver against a genuinely live herdr 0.8.2 server, and found the two had diverged
> substantially. This doc records what broke, what was fixed, what was measured, and what is
> still broken, ranked by priority.

## 0. Bottom line

- herdr's real, published API (protocol 20 / v0.8.2) is **not the API this codebase was
  written against**: different field names, a different pane/agent bootstrap model, and a
  transport with a "one request per connection" limit that the client never assumed. All of
  this is now fixed and covered by unit tests.
- With those fixed, a real herdr tab runs end-to-end for free (no LLM spend) through
  `agent.start`, and for cheap (~$0.01, one real turn) through a full round.
- The **committed benchmark run** (via the actual `sdlc benchmark run` CLI, not an ad hoc
  script) got through `clarify` → `architecture` → `plan` → into 21 real `code`-stage attempts
  under the `herdr` harness, and **all 21 failed** for the same reason: Claude Code's
  interactive first-run onboarding wizard (theme picker → API-key confirmation → login-method
  select) blocks every fresh session, and nothing in the round protocol dismisses it. This is
  the #1 priority fix — see §4.
- Five more bugs were found and fixed along the way (transport, request shapes, a Docker build
  gap, a Docker asset-copy gap, and a stale timeout constant); see §2.
- Two more environment-only gaps (unrelated to herdr) were found and worked around rather than
  fixed, since fixing them is out of scope for this harness; see §3.

## 1. What "collect statistics" actually produced

One complete run through the real Temporal pipeline (`benchmarks/cases/herdr-probe/case.yaml`,
harness `herdr`, `--gate-policy off`), report at
`runs/benchmarks/bench-herdr-probe-1788090533/report.md` (inside the `worker` container's
`/app/runs`, not the host — see §3.3):

| stage | harness | model | n | quality | cost ($) | wall (s) |
|---|---|---|---|---|---|---|
| clarify | proposer | anthropic:glm-5.2 | 1 | n/a | 0.006 | 29.0 |
| architecture | proposer | anthropic:glm-5.2 | 1 | n/a | 0.009 | 36.9 |
| plan | proposer | anthropic:glm-5.2 | 1 | n/a | 0.033 | 56.6 |
| **code** | **herdr** | **herdr:claude-opus-5** | **21** | **0.000** | **n/a** | **~25 avg** |
| review | proposer | anthropic:glm-5.2 | 21 | 0.000 | n/a | 25.3 |
| qa | proposer | anthropic:glm-5.2 | 21 | n/a | 0.002 | 25.3 |
| merge | proposer | deterministic | 1 | 0.000 | n/a | 2.6 |

Two prior attempts at this same run were burned by config bugs before reaching herdr at all
(see §3) — a plan-validation flake (unrelated to herdr, a planner-model DAG inconsistency) and
a `wall_clock_s`/activity-timeout tie (§2.5). The number above is the first attempt that
actually exercised herdr for real.

**Reading the "21" honestly:** `n=21` is 21 real fix-attempt retries of the same dev task, each
a full herdr tab (workspace → pane → real `claude` launch → real round), each ending in
`protocol_violation` because the pane never produced a valid `status.json` — because the real
`claude` process never got past its own onboarding wizard to see the actual brief. `cost: n/a`
for the `code` row is itself a finding: **every attempt's cost probe failed** (`no session log
matching '*.jsonl'`), because a session transcript is never written until a real turn happens,
and no real turn ever happened. This one root cause (§4) explains the whole `code` row.

## 2. Bugs found and fixed (herdr module, in scope)

All covered by the existing unit suite (`pytest tests/ -k herdr`, 28/28 green after every
change) plus live verification against the real server (free where possible, ~$0.01 for the one
full-round check).

### 2.1 Request field names were stale (`src/sdlc/herdr/driver.py`)
`workspace.create`/`tab.create` sent `name`; the real API wants `label`. `pane.split` sent
`pane_id`; it wants `target_pane_id`. `agent.rename`/`agent.prompt`/`agent.wait` sent `pane_id`;
they want `target`. Confirmed against the live server's own `herdr api schema --json`.

### 2.2 `pane.run` and `pane.set_split_ratio` no longer exist
The whole "run an arbitrary command in a pane" primitive is gone from protocol 20. The real
flow: `workspace.create` now returns its first tab **and** root pane inline (no separate
`tab.create` needed for the lead pane), and starting an agent is `agent.start(name, kind,
pane_id)` against a **fixed list** of natively-detected CLI kinds (`claude`, `opencode`,
`codex`, …) — herdr now types the real binary into the pane and detects readiness itself,
rather than us launching an arbitrary wrapper script and self-reporting state. `pane.split`'s
`ratio` now travels in the same call, so the separate ratio-setting call is gone too.
`_build()`/`_start_pane()` rewritten accordingly; `kroker-pane`'s process-launch role is now
vestigial for the two harnesses E-87a supports (both are natively-detected kinds) — see §3.1.

### 2.3 One request per connection (`src/sdlc/herdr/client.py`)
Confirmed empirically: the api socket answers exactly one request and then resets the
connection — even a second, trivially-valid `ping` right after a successful `workspace.create`
comes back `ConnectionResetError`, and the server's own log shows it never received the second
request. `HerdrClient` was built around one persistent connection multiplexing many requests by
id across a whole tab's lifecycle; that design cannot work against this server. Rewritten to
open a fresh connection per `request()` call; `events()` keeps its own dedicated long-lived
connection, since a subscription is a genuine stream. `open()`/`close()` are now harmless
no-ops kept only so existing `async with HerdrClient(...)` call sites don't need to change.

### 2.4 `agent.rename` after `agent.start` is redundant and racy
`agent.start`'s own `name` param already names the agent atomically. A separate `agent.rename`
called immediately after — the old two-step `pane.run` + `agent.rename` habit — races the
server's own startup and comes back `agent_launch_pending`. Removed; `agent.start` also needs a
short readiness wait immediately after it (its `launch_pending: true` response is not the same
as "addressable by `agent.prompt`" — confirmed empirically via `agent_not_ready`), added via one
`agent.wait` call in `_start_pane`.

### 2.5 `CodingTaskInput.timeout_s` is a disconnected constant (`src/sdlc/activities.py:489`)
`HerdrHarness.run()` validates that the layout's `wall_clock_s` is strictly less than "the
activity's own timeout" — but the number it's given (`req.timeout_s`, hardcoded default
`3600`) is **not** the real per-role Temporal `start_to_close_timeout` (`_long_act()`, 4h by
default) — nothing wires the two together. `herdr/layouts/plan.yaml`'s `wall_clock_s: 3600`
happened to tie that stale constant exactly, and the check (correctly, given its bad input)
rejected every run before a tab ever opened. **Worked around** by lowering the layout to
`3000s` (comment left in place). **Not fixed**: the proper fix is threading the real per-role
activity timeout into `CodingTaskInput` at its `feature.py` call site, which is outside herdr's
own module boundary and affects every harness, not just herdr — flagged for a separate task.

### 2.6 The worker image never received herdr's own config assets (`Dockerfile`)
`HerdrHarness.run()` executes **inside the worker container** (it's the one making the socket
calls), and needs to `load_roles`/`load_layout` from a local `herdr/` directory — but only the
separate `herdr` server image stage ever got `COPY herdr ./herdr` + `SDLC_HERDR_DIR`. The
`base` (worker) stage had neither, so every real run failed at `run_coding_task` with
`HerdrAssetsMissing: no herdr/ directory found` before the socket was ever touched. Fixed by
adding the same `COPY herdr ./herdr` and `ENV SDLC_HERDR_DIR=/app/herdr` to the `base` stage.

### 2.7 The herdr install pin itself was broken (`Dockerfile`, found before any of the above)
`RUN curl -fsSL https://herdr.dev/install.sh | sh` puts the binary in `~/.local/bin`, which is
not on `PATH` in that same non-login `RUN` shell — the very next line's `herdr --version` 404s,
`$found` comes back empty, and the version-pin check fails the *build* even when the install
itself succeeded. Fixed with `ENV PATH="/root/.local/bin:${PATH}"` before the install. Separately,
the pinned `HERDR_VERSION=0.1.0` was stale — herdr.dev's installer has no version-pin support at
all (always fetches latest) and upstream has moved to `0.8.2` — bumped the pin per the
Dockerfile's own documented procedure ("re-run the live contract test, then bump
HERDR_VERSION"). This session **is** that re-run, and it is what surfaced everything in §2.1–2.4.

## 3. Found, worked around, not fixed (out of herdr's scope)

### 3.1 Claude Code's interactive onboarding wizard — **top priority, see §4**

### 3.2 Greenfield mode has no real repo-scaffolding step (`src/sdlc/workflows/feature.py:1956`)
`repo_path = idea.repo_url or "/var/sdlc/repo"  # prepared by a setup activity IRL` — a literal
placeholder path with a comment admitting nothing in this deployment prepares it.
`setup_integration_branch` fails with `FileNotFoundError` for any greenfield case with
`repo_url: null`, regardless of harness — this would break `claude_code` and `opencode` cases
identically, it is not herdr-specific. Worked around by pointing `herdr-probe`'s `repo_url` at
the already-mounted `/srv/scratch-repos/todo-api-greenfield`, the same trick
`todo-api-greenfield`/`deveval-*` already use. Not fixed: needs a real "provision a scratch repo
for repo_url: null" activity, which is general benchmark infrastructure, not herdr.

### 3.3 Benchmark evidence/reports live in the worker container's own volume
`sdlc benchmark run` prints a path like `runs/benchmarks/bench-.../report.md` relative to
wherever the *workflow* computed it (inside the `worker` container's `/app/runs`, backed by the
`worker-runs` named volume) — not relative to the host shell that invoked the CLI, even though
the CLI itself runs on the host against `localhost:7233`. Reading a report requires `docker
compose exec worker cat /app/runs/...`. Not a bug, just a rough edge worth documenting so the
next person doesn't go looking on the host filesystem the way this session initially did.

### 3.4 ADR-6 anti-collusion needs a deliberate model label, not just "a model"
A case whose `harnesses: [herdr]` declares a single flat `models: [...]` list gets that model
applied to *every* role via `Arm.resolve()`'s catch-all `default`, including `reviewer` — and
the registry's own `reviewer` default (`anthropic:glm-5.2`) and `dev` default
(`zai-coding-plan/glm-5.2`) are deliberately different *provider* prefixes for exactly this
check (`src/sdlc/agents/loader.py:check_adr6_families`). Labeling herdr's dev/test/devops roles
`anthropic:claude-opus-5` collided with reviewer's family and got the whole cell silently
rejected at dispatch (`ADR-6 violation: reviewer family 'anthropic' equals the family of
'dev'`). Not a bug — working as designed — but worth calling out because the failure mode
(a rejected cell, produced with `n=0`, no error in `report.md`) is invisible unless you go
looking at worker logs. Fixed in `herdr-probe/case.yaml` via an explicit `arms:` entry that only
overrides `dev`/`test`/`devops`, leaving every other role at its registry default.

## 4. Priority 1: get past Claude Code's onboarding wizard

**Root cause, with evidence.** A brand-new `claude` process launched interactively (via
`agent.start`, exactly what `_start_pane` does) shows, in order:

1. A theme-picker ("Let's get started. Choose the text style...") — a first-run-only screen.
2. An API-key confirmation ("Detected a custom API key in your environment... Do you want to
   use this API key? 1. Yes / ❯ 2. No (recommended)") — **defaults to No**, keyed per-API-key
   by a fragment of the key value in `~/.claude.json`'s `customApiKeyResponses`.
3. A login-method select ("Select login method: ❯ 1. Claude account with subscription / 2.
   Anthropic Console account · API usage billing / 3. 3rd-party platform") — needs option 2 for
   an API-key deployment; the default (1) would start an interactive OAuth flow that can never
   complete headlessly.

None of these are dismissed by anything in the round protocol. `agent.prompt`'s text lands on
whichever of these screens is showing, not on a real chat input, so the brief is never actually
seen — herdr's own `agent_status` detection still reports plausible `idle`/`working`
transitions (it is watching terminal render state, not asking the model anything), which is why
this produces a clean-looking `protocol_violation` (missing `status.json`) and an empty session
log rather than an obvious crash. This is a **structural** gap, not a config typo — it explains
100% of the 21 failed attempts in §1.

**What does not fix it, confirmed empirically:**
- `--bare` (documented to make auth "strictly ANTHROPIC_API_KEY") still shows all three screens.
- Running `claude -p "..."` once at container start (a real, cheap non-interactive call) does
  complete cleanly and persist a large config file, but does **not** write
  `customApiKeyResponses` or otherwise change what a *subsequent interactive* launch shows —
  confirmed by launching interactively again right after and seeing the identical theme picker.
- Onboarding state is **per-container**, not persisted by any mounted volume (`~/.claude.json`
  and `~/.claude/settings.json` live directly under `/root`, outside every volume this compose
  file mounts for the `herdr` service) — so even if one launch completed onboarding, the next
  `herdr` container recreate starts from zero again.

**Recommended next steps, in order of how much was already de-risked tonight:**
1. **Script the dismissal in `_start_pane`** (`src/sdlc/herdr/driver.py`): right after the
   readiness `agent.wait` this session already added, send the exact keystroke sequence —
   `Enter` (accept default dark theme) → `Up, Enter` (select "1. Yes" for the API key, since the
   default is "No") → `Down, Enter` (select "2. Anthropic Console account" for login method,
   since the default is "1") — then re-read the pane to confirm the real chat prompt is showing
   before returning. This was verified screen-by-screen live tonight (§ diagnostic scripts); it
   is a small, mechanical addition, not a redesign. **Risk**: brittle if a future Claude Code
   version reorders/adds screens or changes which option is the pre-selected default — the
   confirm-by-reading-the-screen step is what makes this safe to ship (fail loud, not silent).
2. **Investigate `--settings <file-or-json>`** as a cleaner alternative: `claude --help`
   documents a settings file/JSON string that "loads additional settings" and specifically
   mentions `apiKeyHelper` as a supported auth path for `--bare` mode. If a settings key exists
   that pre-answers the API-key and login-method questions declaratively, it would be far more
   robust than scripted keystrokes and worth 30–60 minutes of documentation/experimentation
   before committing to option 1.
3. Either way, do this **before** running any further paid herdr benchmark cells — every
   attempt against a fresh container will hit this identical wall until it's fixed, and will
   produce nothing but repeats of the same `protocol_violation` statistic.

## 5. Suggested order for a follow-up session

1. Fix §4 (onboarding dismissal) — highest leverage, unblocks everything downstream.
2. Re-run `benchmarks/cases/herdr-probe/case.yaml` for the 2 remaining paid runs originally
   requested, now that a real round should be able to complete.
3. Fix §2.5 properly (thread the real per-role activity timeout into `CodingTaskInput`) —
   small, but currently silently wrong for every harness, not just herdr.
4. Revisit `kroker-pane` (`scripts/kroker-pane`) and `pane.report_agent`/self-reported lifecycle
   now that native `agent.start` detection covers both of E-87a's harnesses — likely fully
   vestigial for `claude_code`/`opencode`, worth deleting rather than carrying dead code, unless
   E-87b's advisor/reviewer panes need a non-natively-detected `kind`.
5. Task 15's live contract test (`tests/test_herdr_live_contract.py`) needs a redesign: its
   echo-pane substitution (`drv.pane_command = [...]`) no longer works now that pane launch goes
   through `agent.start`'s fixed `kind` list rather than an arbitrary command. Until it's
   redesigned, this class of drift (this entire session's worth of findings) has no automated
   guard and will silently reappear on the next herdr upstream release.
