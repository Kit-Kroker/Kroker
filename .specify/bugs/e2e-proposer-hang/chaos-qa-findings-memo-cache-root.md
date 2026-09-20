# memo-cache-root — REGRESSION QA (chaos) findings

Seat: qa-chaos. Deliverable:
`tests/test_memoization_cache_root_chaos.py` (6 tests: 5 verified RED on
this worktree 2026-09-20, 1 green-by-design guard). Fix surface: the
deferred Mechanism 2 card
(`follow-up-machine-global-memo-cache.md`, same directory).

## Sibling file (not mine)

`tests/test_memoization_cache_root.py` — the happy-path RED deliverable
from the qa-happy seat — was present but UNCOMMITTED at my verification
time (15:0x), and a scratch `x/registry/` directory appeared mid-run:
another seat is active on this worktree concurrently. I did not touch,
run, or commit either. Overlap between the files is deliberate and
complementary: the happy file pins the straight regression (cross-checkout
miss at cache, risk-memo, and discover-memo level; subprocess-based
second-run hit; env-override pinning); the chaos file pins the edge
shapes listed below.

## Chaos test inventory

| Test | Axis | RED today because | Post-fix contract |
|---|---|---|---|
| `...invisible_to_another_checkout[clone]` | stale state across checkouts | machine-global root: B's `get` returns A's payload | B sees `None`; B's own entry round-trips; B's write never leaks back into A |
| `...invisible_to_another_checkout[worktree]` | same + identity pin | same | same — and checkout identity must be **path-derived**: the worktree shares the commit sha AND the `.git` dir with A, differing only in working-tree path |
| `test_a_second_run_in_the_same_checkout_still_hits_the_memo` | DD10 guard | — (green by design, today and post-fix) | the hit must come from THIS checkout's own earlier run, never from machine temperature; a fix that over-scopes to per-run/per-process roots turns this RED |
| `test_an_empty_cache_root_env_never_scatters_memo_files_into_the_cwd` | boundary value | `os.environ.get` treats `""` as set → `Path("") == "."` → `put` drops `<key>.json` into the CWD | no entry file may appear as a direct child of the process CWD; refusing the store on `""` is acceptable, littering is not |
| `test_an_unreadable_cache_entry_is_a_miss_not_a_crash[garbage-bytes]` | error path | `UnicodeDecodeError` propagates out of `cache.get` | an entry that cannot be read is a miss — a memo may cost a recompute, never the run |
| `...[directory]` | error path | `PermissionError` (Windows' open-a-directory error) propagates | same |

## Why the worktree kinship matters (the fix-direction trap)

The card's three candidate directions all satisfy these tests, but a
FOURTH, wrong direction does not: keying checkout identity on anything
the checkouts share. The clone variant (same commit sha, separate
`.git`) catches sha-keyed identity; the worktree variant (same sha AND
same `.git`, different path — literally the primary-checkout-vs-worktree
shape that evidenced this bug) catches gitdir-keyed identity. Only
path-derived isolation (or per-checkout storage) passes both. The happy
file's two bare `git init` dirs cannot make this distinction — that is
this file's main contribution over it.

## Determinism on any machine

Every key is uuid-salted per run, in both files' spirit: no entry an
earlier run left on the machine can flip a result either way. The RED
runs of the two-checkout tests do write unique-key, inert entries into
the real `%TEMP%/sdlc/memo_cache` (unavoidable: testing the default root
means using it); the keys are never consulted again by anything.

## Why no threads (the concurrency axis)

CWD is process-global, so cross-checkout concurrency is per-process in
production — each assessment worker runs in its own checkout. The
sequential A-put / B-read / B-put / A-read interleave is the
deterministic form of two concurrent runs; threading it would only
re-test one CWD.

## SCOPE RULING REQUESTED before the fix lands

`test_an_unreadable_cache_entry_is_a_miss_not_a_crash` is an adjacent
hardening edge on the same two functions the fix must touch
(`cache.get`), not one of the card's three candidate directions. If the
orchestrator rules this bug root-scoping-only, that test stays RED after
a legitimate fix and will wedge the /speckit-bug-test verdict. Rule it
one way now: ride-along (fixer adds the miss-on-unreadable handling in
the same diff — it is a two-line `except OSError, UnicodeDecodeError`)
or split (I re-file it as an inbox task and it moves out of this bug's
gate).
