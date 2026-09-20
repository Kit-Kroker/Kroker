"""memo-cache-root chaos edges: the machine-global cache root (deferred
Mechanism 2 of e2e-proposer-hang, follow-up card
`.specify/bugs/e2e-proposer-hang/follow-up-machine-global-memo-cache.md`).

The defect: `_cache_root()` defaults to %TEMP%/sdlc/memo_cache --
machine-global, shared across checkouts, branches, and runs -- while the
memo keys are pure content (project|tree_hash|digests|shas|model). Any
earlier run of the same scenario anywhere on the machine leaves a judged
entry under the exact key a later run computes, so a hit can arrive from
machine history instead of from this checkout's own prior run (that is
how a warm cache masked the proposer hang).

The contract these tests encode, deliberately mechanism-neutral so any
of the card's candidate directions satisfies them (per-checkout root,
checkout identity in the key, or per-repo-path namespace under the root):

- An entry written in one checkout is invisible to another checkout of
  the SAME repository computing the same content key -- both leak
  directions, because B poisoning A is as wrong as A poisoning B.
- A second run in the SAME checkout still hits the memo (DD10 restated
  machine-history-free: the hit must be attributable to this checkout's
  own earlier run, never to machine temperature).
- An empty SDLC_MEMOIZATION_CACHE_ROOT never silently degrades to the
  process CWD as the cache root (`Path("")` is `.`, so today it
  scatters <key>.json files into whatever directory is current).
- A cache entry that cannot be read (garbage bytes, a directory squatting
  on the entry path) is a miss, never a crash: a memo may cost a
  recompute, it may never cost the run.

Why the "two checkouts" are git repositories at different paths with
IDENTICAL history: the fix must isolate on the checkout's location (or
per-checkout storage), not on anything the two checkouts share. A clone
shares the commit sha but not the .git dir; a linked worktree shares
both the commit sha AND the git dir and differs only in working-tree
path. Identity keyed on either shared thing passes the clone variant and
still contaminates real worktree runs, so the worktree variant is the
one that pins the fix to path-derived isolation.

Why no threads: CWD is process-global, so cross-checkout concurrency is
per-process in production (each worker runs in its own checkout). The
sequential A-put / B-read interleave below is the deterministic form of
two concurrent runs; threading it would only re-test one CWD.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from sdlc.memoization import cache
from sdlc.memoization.cache import risk_key
from tests.conftest import run_git


def _seed_repo(path: Path) -> Path:
    """A repo with one commit; byte-identical trees across call sites."""
    path.mkdir()
    run_git(["init", "-b", "main"], path)
    run_git(["config", "user.email", "chaos@kroker.test"], path)
    run_git(["config", "user.name", "chaos"], path)
    (path / "README.md").write_text("identical tree in every checkout\n", encoding="utf-8")
    run_git(["add", "-A"], path)
    run_git(["commit", "-m", "seed"], path)
    return path


def _risk_key(run_tag: str) -> str:
    """The evidenced contamination key shape: pure content, no checkout
    term. Computed fresh at each call site so a fix that folds checkout
    identity into the key applies per context, exactly as production
    would when each worker computes the key in its own checkout."""
    return risk_key(
        project=f"chaos-memo-root-{run_tag}",
        tree_hash="0" * 40,
        map_digest="d" * 64,
        rules_sha="r" * 64,
        prompt_sha="p" * 64,
        model_id="anthropic:claude-sonnet-4-5",
    )


@pytest.mark.parametrize("kinship", ["clone", "worktree"])
def test_a_memo_entry_written_in_one_checkout_is_invisible_to_another_checkout(
    tmp_path, monkeypatch, kinship
):
    monkeypatch.delenv("SDLC_MEMOIZATION_CACHE_ROOT", raising=False)
    a = _seed_repo(tmp_path / "checkout-a")
    b = tmp_path / f"checkout-b-{kinship}"
    if kinship == "clone":
        run_git(["clone", str(a), str(b)], tmp_path)
    else:
        run_git(["worktree", "add", "-b", "chaos-b", str(b)], a)

    run_tag = uuid.uuid4().hex[:12]
    payload_a = '{"judgment":"MEASURED","by":"checkout-a"}'
    payload_b = '{"judgment":"MEASURED","by":"checkout-b"}'

    monkeypatch.chdir(a)
    cache.put(_risk_key(run_tag), payload_a)

    monkeypatch.chdir(b)
    assert cache.get(_risk_key(run_tag)) is None, (
        "checkout B must not see checkout A's memo entry: a hit here means "
        "the default cache root (or key namespace) is shared across checkouts"
    )
    cache.put(_risk_key(run_tag), payload_b)
    assert cache.get(_risk_key(run_tag)) == payload_b, (
        "checkout B must be able to build and read back its own entry"
    )

    monkeypatch.chdir(a)
    assert cache.get(_risk_key(run_tag)) == payload_a, (
        "checkout B's write must not leak into checkout A either"
    )


def test_a_second_run_in_the_same_checkout_still_hits_the_memo(tmp_path, monkeypatch):
    """DD10's constraint, restated so it cannot depend on machine history:
    within one checkout, run 2 of the same tree hits run 1's entry. Guards
    the fix against over-scoping (per-run or per-process roots would turn
    every hit into a miss and quietly delete memoization)."""
    monkeypatch.delenv("SDLC_MEMOIZATION_CACHE_ROOT", raising=False)
    a = _seed_repo(tmp_path / "checkout-a")
    run_tag = uuid.uuid4().hex[:12]
    payload = '{"judgment":"MEASURED","by":"checkout-a"}'

    monkeypatch.chdir(a)
    cache.put(_risk_key(run_tag), payload)
    assert cache.get(_risk_key(run_tag)) == payload


def test_an_empty_cache_root_env_never_scatters_memo_files_into_the_cwd(git_repo, monkeypatch):
    """Boundary value on the env override: os.environ.get treats "" as a
    SET value, so today _cache_root() returns Path("") == Path(".") and
    put() drops <key>.json directly into whatever directory is current.
    Refusing the store is a defensible reading of ""; littering the CWD
    is not, so whichever way the fix goes, no entry file may appear as a
    direct child of the process CWD."""
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", "")
    key = f"chaos-empty-root-{uuid.uuid4().hex[:12]}"
    monkeypatch.chdir(git_repo)
    try:
        cache.put(key, '{"judgment":"MEASURED"}')
    except Exception:
        pass
    assert not (Path(git_repo) / f"{key}.json").exists()


@pytest.mark.parametrize("poison", ["garbage-bytes", "directory"])
def test_an_unreadable_cache_entry_is_a_miss_not_a_crash(tmp_path, monkeypatch, poison):
    """Error path on get(): %TEMP% is shared machine space that anything may
    corrupt (a crashed writer, an unrelated tool, a stray mkdir). A cache
    exists to save a recompute; an unreadable entry must therefore read as
    a miss, never propagate the decode/OS error into the activity."""
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / "memo"))
    key = f"chaos-poison-{uuid.uuid4().hex[:12]}"
    (tmp_path / "memo").mkdir()
    entry = tmp_path / "memo" / f"{key}.json"
    if poison == "garbage-bytes":
        entry.write_bytes(b'\xff\xfe\x00 {"judgment":')
    else:
        entry.mkdir()
    assert cache.get(key) is None
