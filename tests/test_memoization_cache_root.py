"""The memo cache's default root is scoped per checkout, never machine-global.

Bug: .specify/bugs/e2e-proposer-hang/follow-up-machine-global-memo-cache.md.
`memoization/cache.py::_cache_root()` defaulted to %TEMP%/sdlc/memo_cache —
ONE root shared by every checkout, worktree, and run on the machine — while
the phase memo keys (risk_key, discover_key) are pure content. Two
byte-identical checkouts of the same project compute the same key, so a run
in one checkout consumes a judged entry stored by a run in another and never
awaits its own proposer. That is what made the e2e-proposer-hang
cold-cache-only and cache-temperature dependent
(.specify/bugs/e2e-proposer-hang/chaos-qa-findings.md, Mechanism 2).

The cross-checkout tests here deliberately do NOT set
SDLC_MEMOIZATION_CACHE_ROOT — the whole existing suite does, which is how
the default went untested — because the override hides exactly this defect.
Every key is salted with a per-run uuid, so no entry an earlier run left on
this machine can flip a result either way: the tests are deterministic on
any machine, cold or warm, which is the property the bug card demands of
the post-fix contracts.

The contracts pin the intentional behavior the card says any fix must keep:
rerunning the same tree within ONE checkout still hits the memo (DD10's
module-level core), and the env override remains THE root from every
checkout (the determinism hatch the rest of the suite leans on).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from sdlc.assessment.discover import memo as discover_memo
from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.risk import memo as risk_memo
from sdlc.assessment.risk.models import SystemRisk, UnifiedRiskMap
from sdlc.measurement import Measurement
from sdlc.memoization import cache

# The subprocess rerun must import THIS worktree's sdlc, not whatever the
# invoking environment's editable install points at.
REPO_SRC = Path(__file__).resolve().parents[1] / "src"

# A "second run" is a second process: assert the memo hit from outside this
# interpreter, with only the checkout's directory to identify it.
SUBPROCESS_RERUN = (
    "import json, sys; "
    "from sdlc.assessment.risk import memo; "
    "assert memo.load(**json.loads(sys.argv[1])) is not None"
)


@pytest.fixture(autouse=True)
def _default_root_writes(monkeypatch):
    """Run against the DEFAULT root (the override hides the defect) and
    leave the machine's cache exactly as found: each test records every
    file it causes to be written through the default root, and teardown
    unlinks it wherever the current root layout put it."""
    monkeypatch.delenv("SDLC_MEMOIZATION_CACHE_ROOT", raising=False)
    written: list[Path] = []
    yield written
    for path in written:
        try:
            path.unlink()
        except OSError:
            pass


def _checkout(parent: Path, name: str) -> Path:
    """One checkout of the same project: a git repo with a byte-identical
    tree. The e2e harness builds one of these per run on the same machine —
    the defect is precisely that their memo entries collide."""
    repo = parent / name
    repo.mkdir()
    (repo / "README.md").write_text("# acme-payments\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def _record(written: list[Path], key: str) -> None:
    """Track the file `put` just wrote, under the root current at put time
    (a per-checkout fix makes that root depend on cwd)."""
    written.append(cache._cache_root() / f"{key}.json")


def test_the_default_root_does_not_cross_checkouts(tmp_path, monkeypatch, _default_root_writes):
    """The fix surface itself: identical content in two checkouts, one key.
    Whichever way the scoping lands (per-checkout root, checkout identity
    in the key, per-repo namespace), a checkout must only ever see entries
    written under itself."""
    key = f"cross-checkout-{uuid.uuid4().hex}"
    primary = _checkout(tmp_path, "primary")
    worktree = _checkout(tmp_path, "worktree")

    monkeypatch.chdir(primary)
    cache.put(key, '{"written_by": "primary"}')
    _record(_default_root_writes, key)
    assert cache.get(key) == '{"written_by": "primary"}'

    monkeypatch.chdir(worktree)
    assert cache.get(key) is None


def test_a_judged_risk_entry_from_one_checkout_is_invisible_to_another(
    tmp_path, monkeypatch, _default_root_writes
):
    """The reported symptom on valid inputs. Checkout A runs its risk
    proposer — judgment MEASURED — and stores the map; checkout B, a
    byte-identical tree of the same project, computes the identical
    risk_key and must not consume A's judgment, or B's _assess hits the
    memo and never awaits B's own proposer."""
    project = f"acme-{uuid.uuid4().hex}"
    key = cache.risk_key(project, "t" * 40, "d" * 64, "r" * 64, "p" * 64, "anthropic:x")
    kw = dict(
        project=project,
        tree_hash="t" * 40,
        map_digest="d" * 64,
        rules_sha="r" * 64,
        prompt_sha="p" * 64,
        model="anthropic:x",
    )
    judged = UnifiedRiskMap(
        system=SystemRisk(),
        collected=Measurement.measured(1.0),
        judgment=Measurement.measured(1.0),
    )
    primary = _checkout(tmp_path, "primary")
    worktree = _checkout(tmp_path, "worktree")

    monkeypatch.chdir(primary)
    assert risk_memo.store(**kw, out=judged) is True
    _record(_default_root_writes, key)
    assert risk_memo.load(**kw) == judged  # A sees its own entry (positive control)

    monkeypatch.chdir(worktree)
    assert risk_memo.load(**kw) is None  # B must await its own proposer


def test_a_discover_map_from_one_checkout_is_invisible_to_another(
    tmp_path, monkeypatch, _default_root_writes
):
    """The _discover twin of the same defect (the bug card names both
    phases): a stored CapabilityMap must not skip discover for a different
    checkout of the same tree."""
    project = f"acme-{uuid.uuid4().hex}"
    key = cache.discover_key(project, "t" * 40, "c" * 64, 1, "p" * 64, "anthropic:x")
    kw = dict(
        project=project,
        tree_hash="t" * 40,
        context_digest="c" * 64,
        registry_version=1,
        prompt_sha="p" * 64,
        model="anthropic:x",
    )
    measured_map = CapabilityMap(collected=Measurement.measured(0.0))
    primary = _checkout(tmp_path, "primary")
    worktree = _checkout(tmp_path, "worktree")

    monkeypatch.chdir(primary)
    assert discover_memo.store(**kw, out=measured_map) is True
    _record(_default_root_writes, key)
    assert discover_memo.load(**kw) == measured_map

    monkeypatch.chdir(worktree)
    assert discover_memo.load(**kw) is None


def test_a_second_run_in_the_same_checkout_still_hits_the_memo(
    tmp_path, monkeypatch, _default_root_writes
):
    """The reuse production intentionally provides (the bug card: DD10 must
    stay green). A LATER RUN — a second process — of the same tree within
    ONE checkout hits the stored entry: cross-run reuse is the feature,
    only cross-checkout bleeding is the defect. Green today via the
    machine-global root; a fix that scopes the root per run or per process
    instead of per checkout turns this RED, which is what it is here to
    catch."""
    project = f"acme-{uuid.uuid4().hex}"
    key = cache.risk_key(project, "t" * 40, "d" * 64, "r" * 64, "p" * 64, "anthropic:x")
    kw = dict(
        project=project,
        tree_hash="t" * 40,
        map_digest="d" * 64,
        rules_sha="r" * 64,
        prompt_sha="p" * 64,
        model="anthropic:x",
    )
    judged = UnifiedRiskMap(
        system=SystemRisk(),
        collected=Measurement.measured(1.0),
        judgment=Measurement.measured(1.0),
    )
    primary = _checkout(tmp_path, "primary")
    elsewhere = _checkout(tmp_path, "worktree")

    monkeypatch.chdir(primary)
    assert risk_memo.store(**kw, out=judged) is True
    _record(_default_root_writes, key)

    # Other work happens elsewhere, then the same checkout runs again —
    # as its own process, identified only by its directory.
    monkeypatch.chdir(elsewhere)
    subprocess.run(
        [sys.executable, "-c", SUBPROCESS_RERUN, json.dumps(kw)],
        cwd=primary,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
        env={**os.environ, "PYTHONPATH": str(REPO_SRC)},
    )


def test_the_env_override_pins_the_root_regardless_of_checkout(tmp_path, monkeypatch):
    """SDLC_MEMOIZATION_CACHE_ROOT is the determinism hatch the whole suite
    (and the chaos file) depends on: when set, it is THE root — the same
    from every checkout — and entries land exactly there."""
    root = tmp_path / "pinned-root"
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(root))
    key = f"override-{uuid.uuid4().hex}"
    primary = _checkout(tmp_path, "primary")
    worktree = _checkout(tmp_path, "worktree")

    monkeypatch.chdir(primary)
    cache.put(key, '{"pinned": true}')

    monkeypatch.chdir(worktree)
    assert cache.get(key) == '{"pinned": true}'
    assert (root / f"{key}.json").read_text(encoding="utf-8") == '{"pinned": true}'
