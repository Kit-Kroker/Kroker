# tests/graph/test_graph_store_root.py
"""The graph store's default root never follows the process CWD.

Bug: .specify/bugs/root-store-write/ (brief:
.workspace/tmp/root-store-write-bug-brief.md). `store.py::default_root()`
resolved its `./runs` fallback -- and any relative env value -- against the
CURRENT DIRECTORY, and `GraphStore.__init__` resolved an explicit relative
`root=` the same way, so store content (graphs, registry snapshots, run
pointers) landed in whatever directory each process happened to start in:
an untracked `x/registry/<64-hex>.json` respawning in the worktree during
the 2026-09-20 memo-cache-root run, and a registry snapshot under relative
`x/` in the E-77 T043 run. Two runs from different CWDs silently got two
different stores.

These tests deliberately do NOT set SDLC_GRAPH_STORE -- tests/conftest.py
pins it for the whole suite, which is exactly how a CWD-following default
went untested -- because the override hides precisely this defect. Every
piece of stored content is salted with a per-run uuid, so nothing an
earlier run left in a real store can flip a result: the tests are
deterministic on any machine, which is what the bug card demands of the
post-fix contracts.

The contracts are mechanism-neutral on purpose: whether the fix anchors
the default to the checkout, to a stable machine location, or refuses
relative inputs outright, two processes inside ONE checkout must resolve
to the ONE store (never silently fork on CWD), a rerun in the same
checkout must still see its own store (the DD10-style constraint), and an
absolute env override must remain THE root from every CWD -- the
determinism hatch the rest of the suite leans on.
"""

from __future__ import annotations

import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sdlc.graph.node_types import NodeTypeSpec
from sdlc.graph.store import GraphStore, RunGraphPointer, default_root

# The two CWDs of a single run session: subdirectories of this test file's
# own worktree (`.git` is a FILE here -- linked-worktree kinship, the
# incident's actual environment).
THIS_WORKTREE = Path(__file__).resolve().parents[1]
WORKTREE_SUBDIR = Path(__file__).resolve().parent

_ROOT_ENV = ("SDLC_GRAPH_STORE", "SDLC_ARTIFACT_ROOT", "SDLC_EXPORT_ROOT")


@pytest.fixture(autouse=True)
def _default_root_writes(monkeypatch):
    """Run against the DEFAULT root (the env override hides the defect) and
    leave every store exactly as found: each test records the files it
    causes to be written together with the root that was current at write
    time (the write location itself is what the bug moves), and teardown
    unlinks them and prunes their now-empty directories -- never above the
    store root."""
    for name in _ROOT_ENV:
        monkeypatch.delenv(name, raising=False)
    written: list[tuple[Path, Path]] = []
    yield written
    for root, path in written:
        try:
            path.unlink()
        except OSError:
            pass
        for directory in (path.parent, root):
            try:
                directory.rmdir()
            except OSError:
                pass


def _checkout(parent: Path) -> tuple[Path, Path]:
    """One checkout with two working directories inside it: `git init` (a
    checkout-anchored resolution has something to anchor to), plus two
    subdirectories to be the two process CWDs."""
    repo = parent / "store-checkout"
    alpha, beta = repo / "alpha", repo / "beta"
    alpha.mkdir(parents=True)
    beta.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return alpha, beta


def _unique_registry() -> dict[str, NodeTypeSpec]:
    """A one-entry registry no earlier run can have stored: unique content,
    unique snapshot sha."""
    name = f"rootwrite{uuid.uuid4().hex}"
    return {name: NodeTypeSpec(type=name, kind="stage", role=None, canonical_stage=None, ports=())}


def _unique_pointer() -> RunGraphPointer:
    return RunGraphPointer(
        run_id=f"rootwrite-{uuid.uuid4().hex}",
        graph_sha="a" * 64,
        layout_sha="b" * 64,
        registry_sha=None,
        roles={},
        started_at=datetime.now(UTC),
    )


def _record(written: list[tuple[Path, Path]], store: GraphStore, *paths: Path) -> None:
    written.extend((store.root, path) for path in paths)


def test_the_default_root_is_the_same_from_every_cwd_of_a_checkout(tmp_path, monkeypatch):
    """The fix surface itself: with no env inputs, the default root must not
    be a function of the process CWD. Whichever way the anchoring lands
    (checkout-anchored, stable machine location), two directories of ONE
    checkout resolve to ONE root -- today each CWD grows its own
    `<cwd>/graphs`."""
    alpha, beta = _checkout(tmp_path)

    monkeypatch.chdir(alpha)
    from_alpha = default_root()
    monkeypatch.chdir(beta)
    from_beta = default_root()

    assert from_alpha.is_absolute()
    assert from_alpha == from_beta


def test_the_default_root_is_the_same_from_every_cwd_of_this_worktree(monkeypatch):
    """The incident's environment: this very worktree, where `.git` is a
    file (linked worktree). The store root must not depend on whether a
    seat started in the worktree root or a subdirectory."""
    monkeypatch.chdir(THIS_WORKTREE)
    from_root = default_root()
    monkeypatch.chdir(WORKTREE_SUBDIR)
    from_subdir = default_root()

    assert from_root.is_absolute()
    assert from_root == from_subdir


def test_two_runs_from_different_cwds_see_the_one_store(
    tmp_path, monkeypatch, _default_root_writes
):
    """The reported symptom on valid inputs. Run A (CWD alpha) snapshots its
    registry and writes its run pointer; run B (CWD beta, same checkout,
    no env inputs) opens its own default store and must see A's snapshot
    and pointer -- not a second, silently different store."""
    alpha, beta = _checkout(tmp_path)
    registry = _unique_registry()
    pointer = _unique_pointer()

    monkeypatch.chdir(alpha)
    store_a = GraphStore()
    sha = store_a.put_registry(registry)
    store_a.put_pointer(pointer)
    _record(
        _default_root_writes,
        store_a,
        store_a.root / "registry" / f"{sha}.json",
        store_a.root / "runs" / f"{pointer.run_id}.json",
    )

    monkeypatch.chdir(beta)
    store_b = GraphStore()
    assert store_b.root == store_a.root
    assert store_b.get_registry(sha) == registry
    seen = store_b.get_pointer(pointer.run_id)
    assert seen is not None and seen.run_id == pointer.run_id


def test_a_rerun_in_the_same_checkout_still_sees_its_own_store(
    tmp_path, monkeypatch, _default_root_writes
):
    """The reuse production intentionally provides (the brief's DD10-style
    constraint): a LATER store opened from the same checkout -- a fresh
    GraphStore resolving the default root again -- still sees what the
    earlier one wrote. Green today via the CWD-resolved root; a fix that
    scopes the root per run or per process instead of per checkout turns
    this RED, which is what it is here to catch."""
    alpha, _ = _checkout(tmp_path)
    registry = _unique_registry()

    monkeypatch.chdir(alpha)
    store_a = GraphStore()
    sha = store_a.put_registry(registry)
    _record(_default_root_writes, store_a, store_a.root / "registry" / f"{sha}.json")

    store_b = GraphStore()  # the rerun: resolves the default root anew
    assert store_b.get_registry(sha) == registry


def test_the_env_override_pins_the_root_from_every_cwd(tmp_path, monkeypatch):
    """SDLC_GRAPH_STORE is the determinism hatch the whole suite (and
    tests/conftest.py) depends on: when set to an absolute path, it is THE
    root -- the same from every CWD -- and content lands exactly there."""
    pinned = tmp_path / "pinned-store"
    monkeypatch.setenv("SDLC_GRAPH_STORE", str(pinned))
    alpha, beta = _checkout(tmp_path)
    registry = _unique_registry()

    monkeypatch.chdir(alpha)
    sha = GraphStore().put_registry(registry)

    monkeypatch.chdir(beta)
    assert GraphStore().root == pinned.resolve()
    assert GraphStore().get_registry(sha) == registry
    assert (pinned / "registry" / f"{sha}.json").is_file()


@pytest.mark.parametrize("env_name", ["SDLC_ARTIFACT_ROOT", "SDLC_EXPORT_ROOT"])
def test_absolute_artifact_and_export_roots_are_cwd_independent(tmp_path, monkeypatch, env_name):
    """The existing derivation contract (tests/graph/test_graph_store.py::
    test_default_root_resolution) extended across CWDs: an absolute run
    artifact root still yields its `graphs` sibling, identically from every
    CWD of a checkout."""
    runs_root = tmp_path / "runs-abs"
    monkeypatch.setenv(env_name, str(runs_root))
    alpha, beta = _checkout(tmp_path)

    monkeypatch.chdir(alpha)
    from_alpha = default_root()
    monkeypatch.chdir(beta)
    from_beta = default_root()

    assert from_alpha == (tmp_path / "graphs").resolve()
    assert from_alpha == from_beta


def _resolved_root_outcome() -> str:
    """The store a client would actually use, as a comparable tag: the
    resolved root, or the refusal. Resolving HERE keeps a lazy fix that
    returns an unresolved relative path from faking green -- such a path
    still lands in the CWD when written."""
    try:
        return f"root:{GraphStore().root.resolve()}"
    except Exception as exc:  # noqa: BLE001 -- a ruled refusal is an outcome
        return f"refused:{type(exc).__name__}"


@pytest.mark.parametrize("env_name", _ROOT_ENV)
def test_a_relative_root_value_never_silently_forks_the_store_on_cwd(
    tmp_path, monkeypatch, env_name
):
    """The E-77/x-registry incident restated: a relative env value (the
    literal `x` from the worktree sightings) must not make two runs from
    different CWDs silently use two different stores. Refusing it is a
    legitimate ruling; resolving it identically from every CWD of one
    checkout is another. Silently forking on the CWD is the bug, and this
    must stay RED against it either way."""
    monkeypatch.setenv(env_name, "x")
    alpha, beta = _checkout(tmp_path)

    monkeypatch.chdir(alpha)
    from_alpha = _resolved_root_outcome()
    monkeypatch.chdir(beta)
    from_beta = _resolved_root_outcome()

    assert from_alpha == from_beta
