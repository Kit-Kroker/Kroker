# Bug Fix: machine-global memo cache root breaks run hermeticity

- **Slug**: memo-cache-root
- **Fixed**: 2026-09-20
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Scoped the memo cache's default root per checkout (direction (c) of the card, confirmed by the orchestrator's cause-gate ruling): the `%TEMP%\sdlc\memo_cache` base now carries a namespace segment derived from the resolved checkout root, so pure-content keys can no longer be satisfied by another checkout's runs. Folded in the ruled hardening: an unreadable cache entry reads as a miss, never a crash.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/sdlc/memoization/cache.py` | modified | `_checkout_root()` (walk up from CWD to first `.git` — dir or file, so linked worktrees count, keyed on the working-tree path never the shared gitdir; outside a repo, the resolved CWD); `_cache_root()` env override with blank-as-unset, else `%TEMP%/sdlc/memo_cache/<sha256(checkout)[:16]>/`; `get()` returns None on `OSError`/`UnicodeDecodeError`. `put()`, all four key functions, and the env-hatch semantics untouched. |
| `tests/test_memoization_cache_root.py` | adopted (qa-happy's draft, uncommitted until now) | happy-path contracts: cross-checkout invisibility at cache/risk/discover level, same-checkout second-run hit against the default root from a second process, env-override pinning |
| `tests/test_memoization_cache_root_chaos.py` | adopted (already committed c3cf8e4) | chaos edges: clone/worktree kinship both leak directions, empty-env never scatters into CWD, unreadable entry is a miss |

## Diff Highlights

```python
def _cache_root() -> Path:
    override = os.environ.get("SDLC_MEMOIZATION_CACHE_ROOT")
    if override:  # blank is unset, not a root
        return Path(override)
    identity = hashlib.sha256(str(_checkout_root()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "sdlc" / "memo_cache" / identity
```

## Tests Added or Updated

None written new — the orchestrator ruled ADOPT of the two seat drafts, verified RED on the pre-fix tree by both seats and by the lead (`8 failed / 3 green-by-design`), GREEN post-fix (`11 passed`). No test edits were needed; the drafts were mechanism-neutral by construction and the fix satisfied them as-is.

## Local Verification

- RED (pre-fix, seats + lead): `.venv\Scripts\python.exe -m pytest tests/test_memoization_cache_root.py tests/test_memoization_cache_root_chaos.py -q` → 8 failed (3 cross-checkout happy, 2 kinship, empty-env scatter, 2 unreadable-entry), 3 passed (the DD10-core and env-hatch guards). qa-happy log: `.workspace/tmp/red-reverify.log`; qa-chaos RED line: `test_memoization_cache_root_chaos.py:104`.
- GREEN (post-fix): same command → **11 passed**.
- Fast tier: `pytest` → **5186 passed, 13 skipped, 221 deselected** (0:05:09).
- DD10 (binding constraint, temporal tier, per-file, 600 s bounded wrapper, temporal-test-server killed before/after): `pytest tests/test_assessment_workflow_e2e.py::test_a_second_assessment_of_the_same_tree_hits_the_memo -m temporal` → `.[100%]`, **passed**.
- `ruff check` (touched files) + `ruff format --check` → clean; `mypy` → *Success: no issues found in 375 source files*.
- Replay goldens unaffected by construction (`fake_cache_get/put` activities; temporal tier) — and the fast tier that includes `tests/test_memoization_cache.py` and all phase-memo unit tests (env-pinned roots) passed.

## Deviations from Assessment

None. Scope followed the cause-gate ruling exactly: direction (c) + the folded-in `get()` miss-not-crash hardening; `put()` and everything else untouched.

## Follow-ups

- The `%TEMP%\sdlc\memo_cache/<digest>/` namespaces accumulate per checkout path; old machine-global entries under `%TEMP%\sdlc\memo_cache/*.json` are now unreachable (stale but inert). Optional hygiene: a one-off cleanup note in docs — not part of this fix.
- ARCHITECTURE.md §ADR-5 discusses memoization conceptually and does not state the root location; no living doc referenced the old default, so no doc clause needed updating in this diff (module docstring now carries the per-checkout contract).
