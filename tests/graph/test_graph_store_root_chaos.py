# tests/graph/test_graph_store_root_chaos.py
"""root-store-write chaos edges: the CWD-anchored graph store root.

Bug: .specify/bugs/root-store-write/assessment.md. `store.py::default_root()`
resolved EVERY relative input -- SDLC_GRAPH_STORE, the SDLC_ARTIFACT_ROOT /
SDLC_EXPORT_ROOT derivation, the `./runs` fallback -- against the process
CWD, and `GraphStore.__init__` resolved an explicit relative `root=` the
same way, so store content (registry snapshots, run pointers, graphs)
landed in whatever directory each process happened to start in: the
respawning untracked `x/registry/<64-hex>.json` of the 2026-09-20
memo-cache-root session and the E-77 T043 relative-`x/` snapshot. The
sibling happy file (tests/graph/test_graph_store_root.py, qa-happy seat)
pins the straight regression -- one root per checkout from every CWD, one
store across CWDs, agree-or-refuse on relative env values. This file pins
the edge shapes around that surface:

- Refusal is LOUD and names the variable: a relative SDLC_GRAPH_STORE /
  artifact / export env value, or an explicit relative `root=`, raises
  ValueError instead of silently anchoring at the CWD (the assessment's
  fail-closed direction -- every remediation alternative shares it).
- Boundary values on "relative": `.`, `..`, `./graphs`, and the Windows
  drive-relative shapes (`D:x`, `\\graphs`) that `Path.resolve()` quietly
  anchors like any relative path. Refusal must classify them as relative;
  resolution-only tests -- neither side of the fix writes anything.
- A BLANK env value stays exactly "unset" (the memo-cache `Path("") == "."`
  scatter footgun must not reappear here), and no store operation may
  materialize a directory as a direct child of the process CWD.
- Stale state: the old world's relative-rooted store is dead weight -- a
  valid `<cwd>/x/registry/<sha>.json` squatter from a pre-fix run is never
  adopted, and deleting a respawned `x/` must not bring it back.
- Concurrency: cross-CWD concurrency is cross-PROCESS in production (the
  CLI and the dashboard are separate processes); two subprocesses started
  in two CWDs of one checkout must converge on the ONE store -- proven
  with real subprocesses, not monkeypatch.chdir, so the fix cannot pass
  by making the root a function of this process's own CWD bookkeeping.
- Hermeticity guard (green today by the bug's own CWD-splitting, green
  after a correct fix, RED only for the memo-cache over-correction): two
  different checkouts never share a store, in both clone and worktree
  kinship -- the worktree shares the commit sha AND the gitdir with its
  primary, so only path-derived checkout identity separates them.
- Outside any repo: a namespaced absolute root, never `<cwd>/graphs`,
  never a bare-CWD anchor, and never a new child of the CWD.

Determinism on any machine: every registry is uuid-salted per run, so
nothing an earlier run left in a real store can flip a result. Post-fix
GREEN runs write inert salted snapshots under the real default root
(unavoidable when testing the default); pre-fix RED runs write only under
pytest's tmp_path. The refusal tests write nothing on either side.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from sdlc.graph.node_types import NodeTypeSpec
from sdlc.graph.store import GraphStore, default_root, registry_sha, snapshot_registry
from tests.conftest import run_git

_ROOT_ENV = ("SDLC_GRAPH_STORE", "SDLC_ARTIFACT_ROOT", "SDLC_EXPORT_ROOT")

# Two processes of one run session, started in different CWDs. The child
# clears the root env itself so the probe holds even if the parent's
# environment hygiene ever regresses (tests/conftest.py pins
# SDLC_GRAPH_STORE for the whole suite -- exactly the hatch that hid this
# defect from every existing test).
_CHILD_STARTER = (
    "import os, sys\n"
    "for name in ('SDLC_GRAPH_STORE', 'SDLC_ARTIFACT_ROOT', 'SDLC_EXPORT_ROOT'):\n"
    "    os.environ.pop(name, None)\n"
    "from sdlc.graph.node_types import NodeTypeSpec\n"
    "from sdlc.graph.store import GraphStore\n"
    "name = sys.argv[1]\n"
    "registry = {name: NodeTypeSpec(type=name, kind='stage', role=None,"
    " canonical_stage=None, ports=())}\n"
    "store = GraphStore()\n"
    "store.put_registry(registry)\n"
    "print(store.root)\n"
)


@pytest.fixture(autouse=True)
def _unpinned_root_env(monkeypatch):
    """Exercise the DEFAULT root chain: the suite-wide SDLC_GRAPH_STORE pin
    in tests/conftest.py hides precisely this defect, so the three root
    env names come off for every test in this file (monkeypatch restores
    them afterwards)."""
    for name in _ROOT_ENV:
        monkeypatch.delenv(name, raising=False)


def _seed_repo(path: Path) -> Path:
    """A repo with one commit; byte-identical trees across call sites so
    the kinship tests differ ONLY in checkout identity."""
    path.mkdir()
    run_git(["init", "-b", "main"], path)
    run_git(["config", "user.email", "chaos@kroker.test"], path)
    run_git(["config", "user.name", "chaos"], path)
    (path / "README.md").write_text("identical tree in every checkout\n", encoding="utf-8")
    run_git(["add", "-A"], path)
    run_git(["commit", "-m", "seed"], path)
    return path


def _checkout(parent: Path, name: str) -> tuple[Path, Path, Path]:
    """One checkout with two working directories inside it: `git init` (a
    checkout-anchored resolution has something to anchor to) plus two
    subdirectories to be the two process CWDs."""
    repo = parent / name
    alpha, beta = repo / "alpha", repo / "beta"
    alpha.mkdir(parents=True)
    beta.mkdir()
    run_git(["init", "-b", "main"], repo)
    return repo, alpha, beta


def _unique_registry() -> dict[str, NodeTypeSpec]:
    """A one-entry registry no earlier run can have stored: unique content,
    unique snapshot sha."""
    name = f"rootchaos{uuid.uuid4().hex}"
    return {name: NodeTypeSpec(type=name, kind="stage", role=None, canonical_stage=None, ports=())}


@pytest.mark.parametrize("value", ["x", ".", "..", "./graphs"])
def test_a_relative_store_env_is_refused_loudly(tmp_path, monkeypatch, value):
    """Error path on the primary env input: the assessment's fail-closed
    direction. Today `Path(value).resolve()` silently anchors the store at
    `<cwd>/value` (the literal `x` of the worktree sightings); the contract
    is a ValueError naming SDLC_GRAPH_STORE. Resolution-only: neither side
    of the fix writes anything in this test."""
    _, alpha, _ = _checkout(tmp_path, "refusal-checkout")
    monkeypatch.chdir(alpha)
    monkeypatch.setenv("SDLC_GRAPH_STORE", value)
    with pytest.raises(ValueError, match="SDLC_GRAPH_STORE"):
        default_root()


@pytest.mark.skipif(os.name != "nt", reason="drive-relative path shapes are Windows-specific")
def test_a_windows_drive_relative_env_is_refused_like_any_relative(tmp_path, monkeypatch):
    """Boundary value the assessment calls out: `Path('\\graphs')` (anchored
    to the current DRIVE, not CWD) and `D:x` (drive-relative) are NOT
    absolute by pathlib's own rule, yet `Path.resolve()` quietly anchors
    both. The refusal must classify them as relative. Resolution-only; the
    drive-rooted shape must never be an excuse to touch `<drive>\\`."""
    _, alpha, _ = _checkout(tmp_path, "windows-refusal")
    monkeypatch.chdir(alpha)
    for value in (f"{alpha.drive}x", os.sep + "graphs"):
        monkeypatch.setenv("SDLC_GRAPH_STORE", value)
        with pytest.raises(ValueError, match="SDLC_GRAPH_STORE"):
            default_root()


@pytest.mark.parametrize("env_name", ["SDLC_ARTIFACT_ROOT", "SDLC_EXPORT_ROOT"])
def test_a_relative_artifact_or_export_env_is_refused_for_the_store(
    tmp_path, monkeypatch, env_name
):
    """Error path on the derivation inputs: a relative run-artifact or
    export root must not silently place the store's `graphs` sibling in
    the CWD (probe 4: SDLC_ARTIFACT_ROOT=runs -> `<cwd>/graphs`). The
    sibling READERS of these vars are out of scope; the store's own
    derivation refuses, naming the variable it refused."""
    _, alpha, _ = _checkout(tmp_path, "derive-refusal")
    monkeypatch.chdir(alpha)
    monkeypatch.setenv(env_name, "x")
    with pytest.raises(ValueError, match=env_name):
        default_root()


@pytest.mark.parametrize("value", ["x", "."])
def test_an_explicit_relative_root_is_refused(tmp_path, monkeypatch, value):
    """Error path on the constructor: an explicit relative `root=` resolves
    against the CWD today (probe 6); every existing caller passes an
    absolute tmp_path, so refusing is the contract. The constructor
    resolves but never writes, so this test is side-effect-free pre-fix
    and post-fix alike."""
    _, alpha, _ = _checkout(tmp_path, "ctor-refusal")
    monkeypatch.chdir(alpha)
    with pytest.raises(ValueError):
        GraphStore(value)


@pytest.mark.skipif(os.name != "nt", reason="drive-relative path shapes are Windows-specific")
def test_an_explicit_windows_drive_relative_root_is_refused(tmp_path, monkeypatch):
    _, alpha, _ = _checkout(tmp_path, "ctor-windows-refusal")
    monkeypatch.chdir(alpha)
    with pytest.raises(ValueError):
        GraphStore(f"{alpha.drive}x")


@pytest.mark.parametrize("env_name", _ROOT_ENV)
def test_a_blank_env_value_stays_unset_and_never_litters_the_cwd(tmp_path, monkeypatch, env_name):
    """Boundary value shared with the memo-cache bug: os.environ.get treats
    `""` as a SET value, and a naive fix that does `Path(explicit)` on it
    gets `Path("") == Path(".")` -- the store root becomes the CWD itself.
    Today the truthiness checks already skip blanks (assessment probe 5,
    a negative finding pinned here); the contract is that this keeps
    holding AND that resolving-and-writing under the default never leaves
    a new direct child of the process CWD (today the `./runs` fallback
    drops `<cwd>/graphs/registry/...` there)."""
    _, alpha, beta = _checkout(tmp_path, "blank-checkout")
    monkeypatch.chdir(alpha)
    unset = default_root()
    monkeypatch.setenv(env_name, "")
    assert default_root() == unset, "a blank value must behave exactly as unset"

    monkeypatch.chdir(beta)
    before = set(os.listdir(beta))
    try:
        GraphStore().put_registry(_unique_registry())
    except ValueError:
        pass  # a loud refusal is a compliant outcome; a CWD child is not
    assert set(os.listdir(beta)) == before, (
        "no store directory may materialize as a direct child of the process CWD"
    )


def test_a_relative_store_env_never_materializes_or_respawns_a_cwd_child(tmp_path, monkeypatch):
    """Stale state -- the incident itself: SDLC_GRAPH_STORE=x made every
    client start write `<cwd>/x/registry/<sha>.json`, and deleting the
    tree only invited the next start to respawn it (put_registry is
    per-hash idempotent; the DIRECTORY was never guarded). Whichever way
    the ruled refusal fires, `x` must never exist as a direct child of
    the CWD -- before and after the seats' whack-a-mole deletion."""
    _, alpha, _ = _checkout(tmp_path, "respawn-checkout")
    monkeypatch.chdir(alpha)
    monkeypatch.setenv("SDLC_GRAPH_STORE", "x")
    for _attempt in range(2):
        try:
            GraphStore().put_registry(_unique_registry())
        except ValueError:
            pass  # the ruled refusal is the compliant outcome
        assert "x" not in os.listdir(alpha), (
            "a relative store env must not materialize `x/` in the CWD (the "
            "respawning untracked-directory nuisance this bug opened with)"
        )
        shutil.rmtree(alpha / "x", ignore_errors=True)  # the seats' deletion


def test_a_stale_relative_rooted_store_is_never_adopted(tmp_path, monkeypatch):
    """Stale state, the other direction: a VALID snapshot left at
    `<cwd>/x/registry/<sha>.json` by a pre-fix run must be dead weight --
    never a source the fixed store consults. Today the CWD-anchored root
    makes get_registry happily return the squatter's content; the fixed
    store either refuses the relative env or cannot see the file."""
    _, alpha, _ = _checkout(tmp_path, "squatter-checkout")
    monkeypatch.chdir(alpha)
    registry = _unique_registry()
    sha = registry_sha(registry)
    squatter = alpha / "x" / "registry" / f"{sha}.json"
    squatter.parent.mkdir(parents=True)
    squatter.write_text(snapshot_registry(registry), encoding="utf-8")
    monkeypatch.setenv("SDLC_GRAPH_STORE", "x")
    try:
        seen = GraphStore().get_registry(sha)
    except ValueError:
        seen = None  # the ruled refusal is a compliant outcome
    assert seen is None, (
        "a snapshot squatting under a relative root must not be adopted by "
        "the store -- the old world's placement is not this run's store"
    )


def test_concurrent_starters_from_two_cwds_converge_on_one_store(tmp_path, monkeypatch):
    """Concurrency: the CLI and the dashboard are separate processes, so
    the one-store contract must hold across PROCESS boundaries -- two real
    subprocesses started (unjoined, genuinely concurrent) in two CWDs of
    one checkout each snapshot their own uuid-salted registry, then a
    third opener from a third CWD must see both. Today each child roots
    its store at its own `<cwd>/graphs` and the roots differ; threads
    would prove nothing here (CWD is process-global, so cross-CWD
    concurrency IS cross-process in production)."""
    repo, alpha, beta = _checkout(tmp_path, "converge-checkout")
    gamma = repo / "gamma"
    gamma.mkdir()
    reg_a, reg_b = _unique_registry(), _unique_registry()

    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _CHILD_STARTER, next(iter(reg))],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for reg, cwd in ((reg_a, alpha), (reg_b, beta))
    ]
    try:
        roots = []
        for proc in procs:
            out, err = proc.communicate(timeout=120)
            assert proc.returncode == 0, f"starter subprocess failed: {err}"
            roots.append(Path(out.strip().splitlines()[-1]))
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()

    assert roots[0] == roots[1], (
        "two processes started in different CWDs of ONE checkout resolved "
        "different store roots -- the store silently forked on the CWD"
    )
    monkeypatch.chdir(gamma)
    store = GraphStore()
    assert store.get_registry(registry_sha(reg_a)) == reg_a
    assert store.get_registry(registry_sha(reg_b)) == reg_b


@pytest.mark.parametrize("kinship", ["clone", "worktree"])
def test_two_different_checkouts_keep_two_different_stores(tmp_path, monkeypatch, kinship):
    """Hermeticity guard: green today only because the bug SPLITS stores
    by CWD; green after a correct fix because the checkout identity
    differs; RED for the memo-cache over-correction (a machine-global
    root would reunite them). The kinship argument is the memo-cache
    precedent's: a clone shares the commit sha but not the .git dir; a
    linked worktree shares the sha AND the gitdir and differs only in
    working-tree path -- so identity keyed on anything the checkouts
    share contaminates real worktree runs. No consumer anywhere depends
    on cross-checkout store sharing (assessment consumer map)."""
    a = _seed_repo(tmp_path / "checkout-a")
    b = tmp_path / f"checkout-b-{kinship}"
    if kinship == "clone":
        run_git(["clone", str(a), str(b)], tmp_path)
    else:
        run_git(["worktree", "add", "-b", "chaos-b", str(b)], a)
    reg_a, reg_b = _unique_registry(), _unique_registry()
    sha_a, sha_b = registry_sha(reg_a), registry_sha(reg_b)

    monkeypatch.chdir(a)
    assert GraphStore().put_registry(reg_a) == sha_a

    monkeypatch.chdir(b)
    assert GraphStore().get_registry(sha_a) is None, (
        "checkout B must not see checkout A's snapshot: cross-checkout "
        "sharing is uncontracted machine history"
    )
    assert GraphStore().put_registry(reg_b) == sha_b
    assert GraphStore().get_registry(sha_b) == reg_b

    monkeypatch.chdir(a)
    assert GraphStore().get_registry(sha_b) is None, (
        "checkout B's write must not leak into checkout A either"
    )


def test_a_non_repo_cwd_gets_a_namespaced_root_not_the_cwd(tmp_path, monkeypatch):
    """Outside any git repo there is no checkout to anchor to; the memo-
    cache ruling pattern is a digest-namespaced absolute location, never
    the bare process CWD (`<cwd>/graphs` is exactly the litter shape).
    Two different non-repo CWDs must also not land on one shared root."""
    nowhere_a, nowhere_b = tmp_path / "nowhere-a", tmp_path / "nowhere-b"
    nowhere_a.mkdir()
    nowhere_b.mkdir()
    assert not any((p / ".git").exists() for p in (nowhere_a, *nowhere_a.parents)), (
        "test premise broken: tmp_path lives inside a git repo"
    )

    monkeypatch.chdir(nowhere_a)
    root_a = default_root()
    monkeypatch.chdir(nowhere_b)
    root_b = default_root()

    assert root_a.is_absolute()
    assert root_a != (nowhere_a / "graphs").resolve(), (
        "outside a repo the default must not anchor at the CWD"
    )
    assert root_a != root_b

    monkeypatch.chdir(nowhere_a)
    before = set(os.listdir(nowhere_a))
    GraphStore().put_registry(_unique_registry())
    assert set(os.listdir(nowhere_a)) == before, (
        "no store directory may materialize as a direct child of the CWD"
    )
