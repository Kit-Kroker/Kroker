# F2 — `sdlc doctor`: setup diagnosis

**Status:** ACCEPTED 2026-09-10. Register row F2
(`docs/reports/external-ideas-2026-09.md:91`), priced there as "a good
afternoon's work" — see §11 and RULING 4. Reviewer gate: approved
(round 2). User gate: ruled 2026-09-10, recorded in §13.

## 1. The problem

The register frames F2 as convenience. It is not, quite. This repo's setup
surface fails in three shapes, and only the first is diagnosed today:

1. **Fails at worker boot, loudly.** `worker.py:201-210` runs
   `validate_registry(load_registry())`, `validate_crew_clis()` and
   `check_harness_versions()`. Good, but it dies on the *first* error, and it
   only runs if you already got far enough to start a worker.
2. **Fails at the moment of use, late.** `gh` and the `origin` remote are
   checked inside `open_pull_request` (`src/sdlc/stages/merge/activities.py:219-235`)
   — the last step of a feature run, after every gate is green. `.env.example`
   says so in as many words: "Without it a run reaches the PR step with every
   gate green and then fails to push." No *LLM* provider key
   (anthropic/openai/gemini) is validated anywhere; the first proposer call
   401s. And nothing anywhere detects a **placeholder**: the one key check that
   does exist at boot — `validate_registry`'s research-provider clause
   (`agents/loader.py:315-324`) — tests non-empty only, so a `TAVILY_API_KEY`
   copied verbatim from `.env.example` boots a worker cleanly and fails on
   first use.
3. **Does not fail — it silently degrades.** The one that earns this row its
   keep. `run_coding_task` swallows a failed checkpoint commit:

   ```python
   commit = _git(["commit", "-m", f"sdlc checkpoint (exit={result.exit_code})",
                  "--allow-empty"], inp.worktree)
   if commit.returncode == 0:
       result.commit_sha = _git(["rev-parse", "HEAD"], inp.worktree).stdout.strip()
   ```
   (`src/sdlc/stages/code/activities.py:197-202` — no raise, no log.)

   With no git committer identity, every checkpoint commit fails and
   `commit_sha` stays `None`. `freeze.py:46-51` documents the consequence:
   "`commit_sha` is None when an attempt produced no checkpoint (a swallowed
   commit failure) … Then A simply does not move; there is deliberately no
   branch_point fallback." The C2 test-freeze anchor never advances, so the
   drift backstop measures against nothing. An unset `user.email` silently
   disarms an integrity control.

`python -m sdlc.cli doctor` does not exist (`src/sdlc/cli.py:164`,
`build_parser`).

## 2. What doctor is

One local subcommand that runs every check, reports **all** findings, and
exits non-zero if any is FAIL. It makes no call to any external service; its
only socket is the Temporal probe, which targets `TEMPORAL_HOST` — a local
one (`localhost:7233`) unless the operator has pointed it elsewhere.

```
$ python -m sdlc.cli doctor
[PASS] agents registry     17 roles; ADR-6 family inequality holds
[PASS] crew CLIs           every layout role's CLI is on PATH
[WARN] harness versions    opencode is 1.19.0, pinned 1.18.4
[PASS] git                 git 2.47.1 on PATH
[FAIL] git identity        no committer identity: git var GIT_COMMITTER_IDENT
                           exits 128. Every checkpoint commit will fail
                           SILENTLY and the C2 test-freeze anchor will not
                           advance (stages/code/activities.py:197).
[PASS] gh                  gh 2.63.2 on PATH
[FAIL] GH_TOKEN            set, but equals the .env.example placeholder
                           'your-github-token'
[PASS] provider keys       ANTHROPIC_API_KEY, EXA_API_KEY set
[FAIL] temporal            localhost:7233 unreachable (connection refused)
[PASS] board db            D:\own\Kroker\runs\board.sqlite3 (stock default;
                           parent writable)
[PASS] containment policy  policy/containment.yaml parses (v1, 5 rules)
[PASS] notify routes       policy/notifications.yaml parses (v1)
8 passed, 1 warning, 3 failed
```

`--json` emits the same results as a list of objects for machines. `--strict`
makes a WARN exit non-zero too.

## 3. The inclusion rule

A check earns its place only when all three hold:

1. The config surface exists in code, at a `file:line` this spec cites.
2. It can actually be misconfigured — a check that cannot fire is a defect
   here, not a freebie. This repo has form on both halves of that: the merge
   gate synthesizes a *failing* `MISCONFIGURED` result for a required check
   that never reached it (`src/sdlc/stages/merge/merge.md:27,43`), and the
   DevEval import report names an upstream acceptance test "partly vacuous"
   for comparing a reference file against itself
   (`docs/reports/deveval-import-report-2026-08-09.md:88-92`). A check that
   cannot fail is the same defect wearing a green tick.
3. Delegation over reimplementation. Where a canonical validator exists,
   doctor calls it and catches its exception. Doctor owns no second copy of
   any rule.

The rule is a necessary condition, not a sufficient one. Every deferred check
in §5 satisfies all three and is still cut, on a fourth criterion the rule
deliberately does not carry: default-path relevance. That is a judgement about
this repo's shipped defaults, not a property of the check, so it is argued
case by case in §5's deferral paragraph rather than mechanised here.

## 4. Severity

Four outcomes, because three do not fit:

| | Meaning | Exit |
|---|---|---|
| **PASS** | The surface is configured and usable. | 0 |
| **WARN** | A real hazard the run may or may not reach. | 0, or 1 under `--strict` |
| **FAIL** | A hard requirement of the default path is broken. | 1 |
| **SKIP** | The feature is off, so the surface is not required. Printed with the reason, never silently omitted. | 0 |

Doctor isolates each check: a FAIL in one never stops the others. The one
place that promise does not hold is *inside* the agents registry —
`validate_registry` raises on its first structural error by design, and
decomposing it would mean either a shadow parser in `doctor/` (guaranteed
drift) or an error-bag refactor of `loader.py` against tests that pin
`pytest.raises(RegistryError, match=…)`. Doctor therefore treats the registry
as one holistic check and says so in the output:

```
[FAIL] agents registry  role 'reviewer': missing instructions.md
                        (first error only; re-run doctor after fixing)
```

**SKIP is not only for row 10.** Two of the delegated validators return
quietly rather than passing, and doctor must not render silence as PASS.
`validate_crew_clis` returns early when the checkout carries no crew assets
(`crew/loader.py:210-211`), and `check_harness_versions` skips any harness
whose CLI is absent from PATH or which declares no pinned version
(`harness/registry.py:33-37`). Both legs report SKIP with the reason —
`SKIP crew CLIs (no crew/layouts in this checkout)`,
`SKIP harness versions (cursor-agent not on PATH; claude, opencode checked)`.
A row whose every leg SKIPs prints one SKIP line, never a PASS.

Erratum (F2 final review, 2026-09-11): the partial-SKIP example above ("cursor-agent not on PATH; claude, opencode checked") names behaviour v1 does not ship. `check_harness_drift` reports SKIP — "pinned harness CLIs are not on PATH; nothing was checked" — only when no pinned CLI is on PATH; when some are, it reports PASS/WARN over the CLIs examined and does not name the absent ones. Per-CLI partial naming is deferred to a follow-up if operator demand appears.

## 5. The check register (v1)

| # | Check | Delegates to / reads | Bad → |
|---|---|---|---|
| 1 | agents registry | `validate_registry(load_registry())` — `agents/loader.py:210,276` | FAIL |
| 2 | crew layout CLIs | `validate_crew_clis()` — `crew/loader.py:195` | FAIL |
| 3 | harness CLI drift | `check_harness_versions()` — `harness/registry.py:27` (see §6) | WARN |
| 4 | `git` on PATH | `shutil.which("git")` — used by `vcs/git.py:41` | FAIL |
| 5 | git committer identity | `git var GIT_COMMITTER_IDENT` (see §6) | FAIL |
| 6 | `gh` on PATH | `shutil.which("gh")` — `stages/merge/activities.py:219` | FAIL |
| 7 | `GH_TOKEN` | set, non-empty, not a placeholder (§7) | FAIL |
| 8 | Temporal reachable | `TEMPORAL_HOST` (default `localhost:7233`), 3s probe | FAIL |
| 9 | board SQLite | `db_path()` — `board/schema.py:154-159` | WARN / FAIL |
| 10 | model provider keys | derived from `agents/*/agent.yaml` (§7) | FAIL |
| 11 | containment policy parses | `load_policy()` — `harness/containment.py:134` | WARN |
| 12 | notify routes parse | `load_routes()` — `notify/routes.py:105` | WARN |

Row 9 FAILs when the nearest existing ancestor directory is not writable,
since `connect()` creates the parent and opens the file on first use
(`board/schema.py:162-174`). Doctor probes with `os.access`; it never creates
the database. Its *other* leg is unsettled: warning on a relative path would
fire on every stock install, because `SDLC_BOARD_DB` unset resolves to the
relative `runs/board.sqlite3`. The two-launch-directories hazard is real, but
a WARN nobody can clear is a WARN operators learn to skip — and `--strict`
would exit 1 out of the box. **See OQ-3.**

Rows 11–12 are one `try/except` each around a loader that already exists.
They are WARN, not FAIL, because both features are off in the default path
(`containment_enabled: bool = False`, `core/models.py:377`; the shipped
`policy/notifications.yaml` routes everything to `log`) — but a malformed
committed asset is still a defect the operator wants named. Whether they ship
in v1 at all is **OQ-2**.

**Deferred, with reasons.** Row 13, the `webhook:$VAR` silent-drop trap at
`notify/routes.py:83-87` (an unset env var drops the route and the asset still
looks configured); row 14, a webhook host outside `allow_hosts`
(`notify/notifiers.py:47` refuses it at delivery time); memory backend config
under `SDLC_MEMORY_ENABLED`; operator chat assets under `SDLC_CHAT_ENABLED`
(`interfaces/dashboard/api/main.py:88-92` swallows a `ChatConfigError` into a
log line, so this one is a genuine silent degradation too). All four only fire
for a customised, opt-in configuration. Row 13 is filed as a follow-up task.

**Not in scope, deliberately.** The `origin` remote: doctor's cwd is not the
run's worktree (`vcs/worktree.py:150-165` creates it under
`SDLC_WORKTREES_ROOT`, cut from the *target* repo), so checking `origin` here
would fail falsely in containers, CI and benchmark runs. Live API calls of any
kind — no test completions, no `gh auth status`, no webhook POSTs. The
register's "missing labels" has no counterpart in this codebase; there is no
label concept to check.

**A note for benchmark-only operators.** Rows 6 and 7 (`gh`, `GH_TOKEN`) FAIL
on a keyless install, and that is correct for the default path, which ends in
a pull request. Benchmark runs legitimately have neither: they run against
scratch checkouts with no remote and skip the PR step outright
(`stages/merge/step.py:521` returns `skipped:benchmark-run-has-no-remote`;
`.env.example:38-40` says the same). An operator running only benchmarks may
read those two rows as advisory. Doctor does not model that as a mode — see
§8's refusal of `--profile`-shaped configuration — it says so in the check's
own detail line.

## 6. Two checks that need detail

**Harness drift (row 3).** `check_harness_versions()` returns `None` and
reports only through `_log.warning`, so doctor cannot read a verdict from it.
Fix at the source rather than scraping logs: have it *return* its findings
while keeping the existing `_log.warning` call. `worker.py:210` discards the
value and needs no edit; `tests/test_cursor_harness.py:111,120,138` call it
and assert on `caplog` only, so they pass unchanged. Four-line diff, zero
drift. This is the only edit outside `doctor/` (see OQ-1).

**Git identity (row 5).** The probe is `git var GIT_COMMITTER_IDENT`, run
with cwd set to a directory that is **not** a git repository. That matters:
`git worktree add` gives the task worktree the *target* repo's config, not
this checkout's, so a repo-local identity here proves nothing about a run.
Running outside a repo resolves exactly the system + global + env layers a
freshly cloned target inherits. Verified: it exits 128 with git's own "Please
tell me who you are" text when the identity is unresolvable, and 0 with the
resolved ident otherwise — git's own resolution, so no rule is duplicated.

Honest limit: on a host with a resolvable hostname git may auto-detect a junk
identity and exit 0. The check proves an identity *can be produced*, not that
it is the right one.

## 7. Placeholders and provider keys

Placeholder detection applies **only to the keys rows 7 and 10 resolve** —
never to every variable in the environment. That scoping is load-bearing, not
tidiness: `.env.example` ships real working defaults alongside its
placeholders (`TEMPORAL_HOST=localhost:7233`, `SDLC_MEMORY_BACKEND=hindsight`,
`ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic`), and a blanket
"value equals the shipped value" rule would flag every one of them.

Two tiers:

1. Parse `.env.example` into `{KEY: shipped_value}`. A *resolved key* whose
   value equals the value `.env.example` ships for that same key is a
   placeholder. Self-maintaining — a new key added to `.env.example` extends
   the check for free — and it cannot false-positive on a real credential.
   `.env.example` ships four placeholder values today: `your-zai-api-key`
   (:7), `your-tavily-api-key` (:16), `your-llm-api-key` (:21) and
   `your-github-token` (:41).
2. A small static floor for when `.env.example` is not on disk (wheel install,
   worker image) and for stubs it does not ship: `test-dummy`, `test-key`,
   `dummy`, `changeme`, plus any value starting `your-`. Whether tier 2 ships
   in v1 is part of **OQ-4**.

Note that `tests/conftest.py:21-23` sets `ANTHROPIC_API_KEY=test-dummy` for
import-only tests, so doctor run under pytest correctly reports placeholders.
Doctor is not a CI check (§8).

**Provider keys (row 10)** are derived, not hardcoded: for each role from
`load_registry()` where `kind != "harness"`, map `model_family(cfg.model)`
(`agents/loader.py:87`) to its env var — `anthropic` → `ANTHROPIC_API_KEY`,
`openai` → `OPENAI_API_KEY`, `google`/`gemini` → `GEMINI_API_KEY` — and for
`kind == "research"` map `cfg.provider` to `TAVILY_API_KEY` / `EXA_API_KEY`
(the pairing `validate_registry` already enforces at `loader.py:315-324`).
Each resolved key must be set, non-empty, and not a placeholder. An unmapped
family is reported SKIP, naming the family, rather than guessed at.

Row 10 and row 1 do not overlap, and §3's delegation rule is why. For the two
research keys, *presence* is already row 1's — `validate_registry` fails boot
without them. Row 10 does not re-litigate that; what it adds, for those two
keys and for every LLM key that nothing checks at all, is the **placeholder**
rule. Row 10 owns placeholder-ness; row 1 owns presence.

One honest exception to §3's "doctor owns no second copy of any rule": the
two-entry provider->env-var map (`tavily`->`TAVILY_API_KEY`,
`exa`->`EXA_API_KEY`) exists both in `loader.py:315-324` and in row 10's
derivation. Two entries over a closed vocabulary --
`RoleConfig.provider` is `Literal["tavily", "exa", "fake"] | None`
(`core/models.py:191`) -- so the drift risk is near zero, but it is a second
copy, and the implementation carries a comment pointing at `loader.py`.

`kind == "harness"` roles are excluded on purpose: their model
(`zai-coding-plan/glm-5.2`) is resolved by the coding CLI, which authenticates
out of band — `opencode.json` carries no credentials and `build_agents`
skips harness roles (`agents/loader.py:447`). Demanding an env var for them
would be a check that can only fire falsely.

## 8. Shape

```
src/sdlc/doctor/
├── __init__.py
├── models.py     # Status enum, CheckResult, Report
├── checks.py     # the twelve checks + the CHECKS registry
└── cli.py        # add_doctor_parser(sub), run_doctor(args)
```

Mirrors `src/sdlc/capability/` (`add_capability_parser` / `run_capability`),
the house pattern for a local-only subcommand, with one deliberate
divergence: `run_doctor` is `async` where `run_capability` is sync
(`cli.py:559`). The Temporal probe is the whole reason; see the wiring
paragraph below. `CHECKS` is an ordered registry of callables, the same shape
as `HARNESSES` (ADR-2, `harness/registry.py:18`) and `NOTIFIERS`
(`notify/notifiers.py:70`).

Wiring in `src/sdlc/cli.py`: `add_doctor_parser(sub)` beside
`add_capability_parser` (~line 270), dispatch via
`raise SystemExit(await run_doctor(args))`, and **`"doctor"` joins the
`local_only` tuple in `_needs_temporal_client` (`cli.py:104-117`)**. That last
one is not optional: if doctor went through `main()`'s shared
`Client.connect`, `sdlc doctor` would crash with a connection error in exactly
the situation it exists to diagnose. Doctor runs its own probe under
`asyncio.wait_for` (`Client.connect` takes no timeout parameter) and reports
the failure as a check result. `run_doctor` is `async` for this one reason;
every other check is a plain sync function.

Nothing else is wired to doctor — not worker boot (it would have to decide
whether a WARN blocks startup, and it already fails closed on rows 1–2), not
pre-commit (developers would need a live Temporal and real keys to commit a
docs typo), not CI (unit CI has neither). Operator-run, by hand.

**Flags not taken.** `--offline` would gate exactly one check, and that check
targets a local socket on the default `TEMPORAL_HOST` (a remote host makes it
a network call, which is the operator's own choice) — an operator who has not
started Temporal wants to be told, not to have it hidden behind a flag. `--profile dev|prod|ci` would
invent a second configuration axis alongside `PipelineConfig` and the
environment, to be maintained forever, so that doctor could re-derive
something it can already observe: whether a feature is switched on. Doctor
reads the environment it is in and reports SKIP with a reason (§4). Two flags
only: `--json`, `--strict`.

## 9. Testing

Every check is a plain function returning a `CheckResult`, so the tier is fast
unit tests with `monkeypatch` — no marker groups, no Temporal.

- One test per check for each outcome it can produce. A check with no failing
  test is not proven able to fire, which is the vacuity this spec's §3 rule
  exists to prevent.
- Placeholder detection: `.env.example` present and absent; a real value; a
  value equal to the shipped placeholder; a static-floor stub.
- Provider-key derivation: a registry whose roles are all `kind=harness`
  derives no key; an unmapped family reports SKIP, not FAIL.
- Temporal: the connector is a parameter, so the test injects a fake that
  raises and one that returns.
- `run_doctor` exit codes: 0 clean, 0 with a WARN, 1 with a WARN under
  `--strict`, 1 with a FAIL; `--json` round-trips.
- Parser wiring, via `build_parser()` — the pattern
  `test_tidyup_cli` already uses.

## 10. Docs

`README.md`'s human-in-the-loop CLI section gains the verb. `.env.example`
gains one line under the tunables pointing at it. No `ARCHITECTURE.md` change:
doctor introduces no component and no ADR.

## 11. Size

The register prices F2 as "a good afternoon's work"
(`docs/reports/external-ideas-2026-09.md:141-143`). **As specced above, it is
not.** Counted honestly: twelve checks, two-tier placeholder detection,
registry-derived provider keys, an async Temporal probe, one source edit in
`harness/registry.py`, and §9's own rule — a test per outcome per check —
which lands the suite near 40 tests. That is a day to a day and a half of
careful work.

Two ways to close the gap, and the choice belongs to the user gate, not to
this spec: re-price the row, or cut to fit. **OQ-4** puts both, with the
named cuts that make the afternoon real.

## 12. Open questions

Four, for the user gate. Each is a decision this spec cannot make from the
code alone.

### OQ-1 — Does F2 edit `src/sdlc/harness/registry.py`?

Row 3 needs `check_harness_versions()` to return its findings; today it
returns `None` and reports only through `_log.warning` (`registry.py:27,46`).
This would be the only edit outside `doctor/`.

- **(a) Return-refactor — recommended.** Add a return value, keep the existing
  `_log.warning` call. Verified zero-breakage: `worker.py:210` discards the
  value, and `tests/test_cursor_harness.py:111,120,138` assert on `caplog`
  only. Four-line diff.
- (b) Cut row 3 from v1. Keeps the diff strictly inside `doctor/`; loses the
  E-24/E-35 drift signal, which is the one check here that catches a silent
  *upgrade* rather than a missing setting.
- (c) Capture log records with a temporary handler. No source edit, but
  doctor's correctness then rides on a log string, and it treats an
  observability side-effect as a domain interface. Not recommended.

### OQ-2 — Do rows 11–12 (containment / notify policy parse) ship in v1?

- **(a) Ship both as WARN — recommended, but see OQ-4.** One `try/except`
  each around an existing loader, ~6 lines total. Both assets are committed
  repo files; a malformed one is a defect whether or not the feature is on.
- (b) Defer both to the follow-up task that already carries row 13. v1 is ten
  checks. This is the reviewer's preference and it is the cheapest honest
  trim toward the afternoon price — it is folded into OQ-4(b).
- (c) Ship as FAIL. Argued against: `containment_enabled` defaults False
  (`core/models.py:377`) and the shipped notify routes are all `log`, so FAIL
  would block an operator whose setup is genuinely fine.

### OQ-3 — What does row 9 do on a stock install?

`SDLC_BOARD_DB` unset resolves to the relative `runs/board.sqlite3`
(`board/schema.py:154-159`), so a bare relative-path WARN fires on every
default install — training operators to ignore WARNs, and making `--strict`
exit 1 out of the box. The unwritable-parent FAIL leg is not in question.

- **(a) WARN only when `SDLC_BOARD_DB` is explicitly set to a relative path —
  recommended.** The hazard is real precisely when an operator has *chosen* a
  path and not noticed it is cwd-relative. Silence on the shipped default,
  which is a deliberate default and not a misconfiguration.
- (b) PASS, printing the resolved absolute path. Visibility without alarm; the
  operator can see which database this cwd binds to. Weaker: nothing flags the
  explicitly-set relative path either.
- (c) WARN always, as originally drafted. Honest about a real hazard, but it
  is a WARN nobody can clear, and §4's severity table loses meaning if one row
  is permanently yellow.

### OQ-4 — Re-price the row, or cut it to fit the afternoon?

§11 states the honest estimate: a day to a day and a half as specced, against
the register's "a good afternoon's work". The register is the user's roadmap
and this spec does not edit it, so the ruling is the user's.

- **(a) Re-price: ship all twelve checks and record the true size —
  recommended by this spec.** The scope is not padding. Rows 5, 7 and 10 are
  the ones that repay the extra half-day: row 5 is the C2-anchor
  silent-disarm, and rows 7/10 are the placeholder detection that is the
  register row's own headline wording ("placeholders, missing … keys"). Eight
  of the twelve rows are three lines of delegation; the cost is concentrated
  in the test suite, which is where it should be.
- (b) **Cut to fit — the reviewer's recommendation.** Drop rows 11 and 12
  (OQ-2(b)) and §7's tier-2 static floor, which is reachable only on a wheel
  install with no `.env.example`. Leaves rows 1–10 with tier-1 placeholder
  detection: an afternoon, and it keeps every finding that motivated the row.
  Cut items join row 13 in the existing follow-up task.
- (c) Cut harder — rows 1–10 minus OQ-1's registry edit (so row 3 goes too),
  nine checks. Half a day. Only worth taking if the afternoon is a hard
  ceiling; it drops a real signal to save four lines.

A note on how (a) and (b) differ in kind: (b) is a genuine descope with a
filed follow-up, not a quality cut. Neither option changes rows 1–10 or the
inclusion rule.

## 13. Rulings

The user gate ruled all four open questions on **2026-09-10**, each as §12
recommended. The options as §12 states them are left standing above: what was
weighed is part of the record, not scaffolding to be removed once a choice is
made.

**RULING 1 (OQ-1) → (a) return-refactor.** `check_harness_versions()` gains a
return value carrying its findings and keeps its existing `_log.warning` call.
`worker.py:210` and `tests/test_cursor_harness.py:111,120,138` are untouched.
This is the one edit outside `src/sdlc/doctor/`; row 3 ships.

**RULING 2 (OQ-2) → (a) rows 11–12 ship in v1 as WARN.** The containment and
notify policy assets are parsed by delegating to `load_policy()` and
`load_routes()`. WARN, not FAIL: both features are off in the default path, so
a malformed committed asset is named without blocking an operator whose setup
is otherwise sound.

**RULING 3 (OQ-3) → (a) WARN only on an explicitly relative `SDLC_BOARD_DB`.**
Row 9 is silent on the stock default: with `SDLC_BOARD_DB` unset it PASSes,
printing the resolved absolute path so the operator can see which database
this working directory binds to. The WARN fires only when the operator has
*set* the variable to a relative path — the case where a choice was made and
its cwd-dependence probably went unnoticed. The unwritable-parent FAIL leg is
unchanged. §2's sample output renders this ruling.

**RULING 4 (OQ-4) → (a) ship twelve checks; §11's price stands.** F2 is a day
to a day and a half of careful work, not an afternoon, and the register's
estimate is superseded by §11 rather than met by descoping. Rows 11–12 stay
(RULING 2) and §7's tier-2 static placeholder floor stays. Nothing moves to
the follow-up task except row 13 and the other deferrals §5 already names on
their own merits.

Consequence for the follow-up task: the inheritance clause in
`.workspace/tasks/2026-09-10-notify-route-unset-env-var-drops-silently.md`,
which was conditional on RULING 2 or 4 going the other way, is moot and has
been removed. That task carries row 13 and its two related findings only.
