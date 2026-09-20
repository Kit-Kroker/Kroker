# Bug Assessment: machine-global memo cache root breaks run hermeticity

- **Slug**: memo-cache-root
- **Created**: 2026-09-20
- **Source**: pasted text — task brief at `D:/own/Kroker/.workspace/tmp/memo-cache-bug-brief.md`, carrying `.specify/bugs/e2e-proposer-hang/follow-up-machine-global-memo-cache.md` + `chaos-qa-findings.md` §"machine-global memo cache masks the hang" (both re-verified locally in this worktree)
- **Verdict**: valid
- **Severity**: high — hermeticity/determinism defect in the run and test fabric; it masked the e2e-proposer-hang (making it cold-cache-only) for weeks and lets one checkout consume a proposer judgment another checkout's run produced. Not `critical`: payloads are value-correct for their keys (no artifact corruption), no security boundary crossed, and the dev-loop half of the cache is default-off.

## Report (verbatim or summarized)

`src/sdlc/memoization/cache.py::_cache_root()` defaults to a machine-global
`%TEMP%/sdlc/memo_cache` shared across checkouts, branches and runs, while all
memo keys are pure content — so outcomes depend on machine history: a warm cache
lets assessment e2e pass via memo hit (the workflow path never executes; this is
what made e2e-proposer-hang cold-cache-only), and an entry judged in ANY
checkout can be served in ANOTHER one under the same key. Hermeticity defect:
tests and runs are not independent of `%TEMP%` state.

## Symptom

A run's memo lookup can be satisfied by an entry any earlier run anywhere on the machine wrote (any checkout, any branch, primary or worktree), so run and test outcomes depend on machine history instead of on the current checkout's own prior runs; expected: memo reuse within one checkout across runs (DD10), invisibility across checkouts.

## Reproduction

Re-verified live on this worktree (2026-09-20, `.venv\Scripts\python.exe`, pure filesystem, uuid-free probe with manual cleanup — no Temporal):

1. Delete `SDLC_MEMOIZATION_CACHE_ROOT` from env (exercise the default root).
2. Compute `risk_key("probe-project", "t"*40, "d"*64, "r"*64, "p"*64, "anthropic:x")` — pure content, no checkout term.
3. `cache.put(key, judged)` with cwd = checkout A; `cache.get(key)` with cwd = checkout B (a different directory).
4. Observed: `default_root = C:\Users\start\AppData\Local\Temp\sdlc\memo_cache`; **B sees A's entry (cross-checkout leak)**; B's own rerun in B also hits (same-checkout reuse — the DD10 core that must survive). Verdict: `DEFECT_REPRODUCED`.

This is the mechanism chaos-qa documented for e2e-proposer-hang (Mechanism 2): the e2e `assessed_repo` fixture builds a byte-identical tree every run, so any earlier run of the scenario — including from the primary checkout — leaves a judged map under the exact key the "hanging" test computes; `_assess`/`_discover` hit the memo and never await the run's own proposer.

## Suspected Code Paths

- `src/sdlc/memoization/cache.py:13-15` — `_cache_root()`: `SDLC_MEMOIZATION_CACHE_ROOT` env else `os.path.join(tempfile.gettempdir(), "sdlc", "memo_cache")`. Machine-global; no checkout identity anywhere in path or key. (Confirmed verbatim.)
- `src/sdlc/memoization/cache.py:18-115` — all four key functions are pure content: `content_key(stage|input_json|prompt_sha|model_id|upstream_recall_ref)`, `signal_key(signal_id|version|rules_sha|tree_hash)`, `discover_key(project|tree_hash|context_digest|registry_version|prompt_sha|model)`, `risk_key(project|tree_hash|map_digest|rules_sha|prompt_sha|model)`. `project` is a *name* (`cli.py:738`: `os.path.basename(repo)` or `--project`), not a path — every checkout of the same project shares it.
- `src/sdlc/assessment/scan/memo.py`, `src/sdlc/assessment/discover/memo.py`, `src/sdlc/assessment/risk/memo.py` — phase memos; keys computed **inside activities** (`assessment/activities.py:544,847` + scan activities) where env/CWD reads are legal.
- `src/sdlc/workflows/role_host.py:104-110` — `content_key` computed **inside workflow code** ("Pure function of its arguments — safe to call from workflow code", `cache.py:21`); gated by `cfg.memoization_enabled` (`core/models.py:380`, default `False`).
- `src/sdlc/cli.py:715-748` — `assess` CLI: the only production entry point that starts `AssessmentWorkflow` (memos always active — no flag gates assessment memos).
- `tests/test_assessment_workflow_e2e.py:365-371,484-565` — DD10 and its `assessed_repo` fixture (already pins the env root per test — the previous bug's test-side-only fix).

## Root Cause Hypothesis

**Confidence: high.** The default cache root is machine-global while every memo key is pure content with no checkout term, and no production consumer contracts cross-checkout reuse — so the cache's effective scope ("regardless of which run asked", `cache.py:2`) silently became "regardless of which *checkout* asked". Any prior run on the machine can satisfy a later run's lookup in a different checkout, making both test outcomes and run outcomes functions of machine history. This exact mechanism made the e2e-proposer-hang cold-cache-only (tier position #102 runs before the memo-warming test) and is the deferral the 2026-09-20 cause gate explicitly carried forward as this bug.

## Proposed Remediation

**Recommended direction (c) of the card's three: keep the machine-global `%TEMP%` base, namespace it per resolved checkout.**

`_cache_root()` becomes: env override (treat blank as unset — see risks) → else resolve the checkout root from the process CWD (stdlib-only walk up to the first `.git`) → `%TEMP%/sdlc/memo_cache/<short sha256 of resolved root>/`; when CWD is not inside a git repo, namespace by the digest of the absolute CWD itself (hermetic, never the bare CWD). Keys stay untouched and pure.

Evidence for the ruling (as the card demands):

1. **Who reads/writes the cache outside tests** — exactly two production surfaces: (i) the `asslt assess` CLI (`cli.py:715-748`) driving AssessmentWorkflow's always-on scan/discover/risk memos; (ii) the dev-loop `content_key` cache via `RoleHost._cached_stage`, default-off (`memoization_enabled: bool = False`, `core/models.py:380`), benchmark cells explicitly off (`docs/superpowers/specs/2026-07-24-per-role-model-sweep-design.md:86`), enabled in production only by deliberate config. Crew runs: no memoization references anywhere under `crew/`. Benchmark: aggregation scripts only; never starts AssessmentWorkflow. **No consumer depends on cross-checkout reuse; nothing contracts it.** The only contracted reuse is same-checkout cross-run (DD10; "regardless of which run asked").
2. **Are content keys semantically valid cross-checkout?** Values are correct for their keys (same tree/rules/prompt/model ⇒ payload is what this checkout would compute — scan signals are deterministic functions of tree+rules; proposer judgments are ADR-5 model-output caching). So a cross-checkout hit is not value corruption — but it is uncontracted machine-history dependence, which is the defect. Losing it costs nothing that any test, doc, or consumer pins.
3. **Cost of each option**:
   - **(a) per-checkout root inside the repo** — puts mutable cache state inside the tree the assessment *measures* (scan signals read the repo; a cache directory risks perturbing them), needs gitignore discipline in every worktree (`.herdr/*`), and still needs an un-gitted-CWD fallback story. Medium-high hygiene cost plus self-referential-measurement risk.
   - **(b) checkout identity in the key** — structurally unsound: `content_key` is computed in *workflow* code (`role_host.py:104`); its purity is what makes it replay-safe. Injecting CWD/repo-path reads breaks Temporal determinism (replay in a different process/dir ⇒ divergent history), changes all four key signatures and every caller, and forces re-baselining replay goldens (`tests/replay/test_graph_golden.py`, `test_feature_replay.py` — never re-recorded). Highest blast radius. **Reject.**
   - **(c) namespaced machine-global root** — keys pure, workflow code untouched, replay goldens untouched, env-override semantics unchanged (the whole suite, the chaos file, and DD10's fixture pin it), hermetic across checkouts, same-checkout rerun reuse preserved, no pollution of the measured tree, `%TEMP%` hygiene retained. Cost: uncontracted cross-checkout reuse disappears (that is the desired loss) + a ~15-line stdlib resolver and a blank-env guard.
4. **DD10 under (c)**: stays green twice over — its fixture pins `SDLC_MEMOIZATION_CACHE_ROOT` per test (both runs share one root ⇒ hit), and under the *default* root the same checkout resolves to the same namespace ⇒ run 2 hits run 1. The card's re-statement duty is met by a machine-history-free test of exactly that (see tests below).

**Alternatives**:
- (a) as above — viable but pollutes the measured tree; choose only if cache-inside-repo is wanted for discoverability.
- (b) as above — rejected on Temporal-determinism and blast-radius grounds, not preference.

**Files likely to change**:
- `src/sdlc/memoization/cache.py` — root resolution/namespace + blank-env guard; optionally harden `get()`/`put()` (see Risks).
- `tests/test_memoization_cache_root.py`, `tests/test_memoization_cache_root_chaos.py` — see Open Questions (stale drafts exist).

**Tests to add or update** (machine-history-free by construction — uuid-salted keys, per-test roots where the override is under test, default-root tests self-cleaning):
- Cross-checkout invisibility, both leak directions (clone AND linked-worktree kinship — identity must be path-derived, not sha/.git-derived).
- Same-checkout second-run hit against the *default* root, proven from a second process identified only by its directory (DD10 core restated).
- Env override remains THE root from every checkout (the suite's determinism hatch).
- Edge values: empty env string never degrades to CWD; unreadable entry (garbage bytes / directory squatting the path) is a miss, never a crash.

## Risks & Considerations

- Blank env is currently a live footgun: `os.environ.get` treats `""` as set ⇒ `Path("")` is `.` ⇒ `put()` scatters `<key>.json` into the CWD. The fix must treat blank as unset (or refuse); the chaos edge test pins it.
- `get()` today raises on unreadable entries (`UnicodeDecodeError` on garbage bytes, `OSError` on a directory squatting the path); `%TEMP%` is shared machine space. Recommend folding the miss-not-crash hardening into this fix — same function, same defect class (root/entry resolution) — but flag for the scope ruling since the card says no drive-bys.
- Cache warmth resets per checkout (cold run after cloning) — accepted: that is hermeticity working; the env override remains the pinning hatch.
- Windows `%TEMP%` cleaners may wipe namespaces — already true today; unchanged.
- Keep the namespace digest short (e.g. 16 hex chars) to bound path length.

## Open Questions

- [NEEDS CLARIFICATION: orchestrator — confirm direction (c) as the fix target]
- [NEEDS CLARIFICATION: orchestrator — two UNTRACKED test drafts predate this assessment and are confirmed seat deliverables, not anonymous strays: `tests/test_memoization_cache_root.py` (qa-happy) and `tests/test_memoization_cache_root_chaos.py` (qa-chaos, 5 tests verified RED 2026-09-20 per `.specify/bugs/e2e-proposer-hang/chaos-qa-findings-memo-cache-root.md`). They are mechanism-neutral, uuid-salted, self-cleaning, and match the contracts above. Rule: adopt+re-verify RED via the qa seats, or write fresh. Recommend adopt.]
- [NEEDS CLARIFICATION: orchestrator — `uv.lock` showed modified (+838/−106, apparently an aborted `uv sync`) early in this assessment and was reverted by another seat mid-run; this worktree's `.venv` currently lacks pytest, blocking suite runs. Re-sync before the RED/fix phase. A stray scratch `x/registry/<sha>.json` also appeared mid-run (noted by qa-chaos too); cleanup or ignore.]
- [NEEDS CLARIFICATION: orchestrator — scope: include the `get()` miss-not-crash hardening in this fix, or defer?]
