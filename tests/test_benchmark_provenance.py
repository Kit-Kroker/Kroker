"""012 T006 (RED): provenance on every record (FR-014 to FR-016, R-7).

The module under test, ``sdlc.benchmarks.provenance``, does not exist
yet -- its absence fails collection of this file, which IS this task's
red state. Names are data-model §2.2; behaviour is contract §2.5/§2.7:
resolve_provenance resolves git in the given source root, then the
environment, then ``unknown``/``None`` -- never raising -- and
prompt_sha_for branches on registry-prompt presence and the literal
model ``deterministic``.
"""

import asyncio
import hashlib
import subprocess
from pathlib import Path

from sdlc.agents.roles import REGISTRY
from sdlc.benchmarks.provenance import (
    PROMPTED_ROLES,
    UNKNOWN_COMMIT,
    Provenance,
    resolve_provenance,
)


def _git(args, cwd):
    subprocess.run(
        ["git", "-c", "safe.directory=*", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "srcrepo"
    repo.mkdir()
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _git(["add", "tracked.txt"], repo)
    _git(["commit", "-q", "-m", "init"], repo)
    return repo


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


# --- resolve_provenance: git layer -------------------------------------------


def test_resolve_provenance_reads_git_head_of_the_source_root(tmp_path, monkeypatch):
    monkeypatch.delenv("KROKER_COMMIT", raising=False)
    monkeypatch.delenv("KROKER_TREE_DIRTY", raising=False)
    repo = _init_repo(tmp_path)
    prov = asyncio.run(resolve_provenance(repo))
    assert isinstance(prov, Provenance)
    assert prov.kroker_commit == _head(repo)
    assert prov.tree_dirty is False


def test_resolve_provenance_flags_dirty_tree_in_the_source_root(tmp_path, monkeypatch):
    monkeypatch.delenv("KROKER_COMMIT", raising=False)
    monkeypatch.delenv("KROKER_TREE_DIRTY", raising=False)
    repo = _init_repo(tmp_path)
    with open(repo / "tracked.txt", "a", encoding="utf-8") as f:
        f.write("uncommitted\n")
    prov = asyncio.run(resolve_provenance(repo))
    assert prov.kroker_commit == _head(repo), "the commit is unchanged by the edit"
    assert prov.tree_dirty is True


# --- resolve_provenance: environment layer -----------------------------------


def test_resolve_provenance_falls_back_to_env_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("KROKER_COMMIT", "abc")
    monkeypatch.delenv("KROKER_TREE_DIRTY", raising=False)
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    prov = asyncio.run(resolve_provenance(not_a_repo))
    assert prov.kroker_commit == "abc"
    assert prov.tree_dirty is None


def test_resolve_provenance_parses_the_tree_dirty_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KROKER_COMMIT", "abc")
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    for raw, expected in (("1", True), ("true", True), ("0", False), ("false", False)):
        monkeypatch.setenv("KROKER_TREE_DIRTY", raw)
        prov = asyncio.run(resolve_provenance(not_a_repo))
        assert prov.tree_dirty is expected, f"KROKER_TREE_DIRTY={raw!r}"
        assert prov.kroker_commit == "abc"


# --- resolve_provenance: unknown layer ---------------------------------------


def test_resolve_provenance_unknown_without_git_or_env(tmp_path, monkeypatch):
    """FR-016: undeterminable provenance is explicitly ``unknown``, never
    an empty value indistinguishable from not-recorded."""
    monkeypatch.delenv("KROKER_COMMIT", raising=False)
    monkeypatch.delenv("KROKER_TREE_DIRTY", raising=False)
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    prov = asyncio.run(resolve_provenance(not_a_repo))
    assert prov.kroker_commit == UNKNOWN_COMMIT
    assert UNKNOWN_COMMIT == "unknown"
    assert prov.tree_dirty is None


# --- prompt_sha_for -----------------------------------------------------------


def test_prompt_sha_for_hashes_the_registry_instructions():
    import sdlc.benchmarks.provenance as prov_mod

    role = "architect"
    expected = hashlib.sha256(REGISTRY[role].instructions.encode()).hexdigest()
    got = prov_mod.prompt_sha_for(role, "anthropic:claude-sonnet-4-6")
    assert got == expected
    assert len(got) == 64
    int(got, 16)  # 64 hex characters
    assert got == prov_mod.prompt_sha_for(role, "anthropic:claude-sonnet-4-6"), (
        "identical prompt content hashes identically"
    )


def test_prompt_sha_for_deterministic_model_beats_the_role():
    import sdlc.benchmarks.provenance as prov_mod

    assert prov_mod.prompt_sha_for("architect", "deterministic") == "none:deterministic"
    assert prov_mod.prompt_sha_for("no-such-role", "deterministic") == ("none:deterministic")


def test_prompt_sha_for_role_without_registry_prompt():
    """`dev` is a harness-kind registry role with instructions None; its
    records carry the explicit no-registry-prompt marker, not a hash."""
    import sdlc.benchmarks.provenance as prov_mod

    assert REGISTRY["dev"].instructions is None
    assert prov_mod.prompt_sha_for("dev", "anthropic:claude-sonnet-4-6") == (
        "none:no-registry-prompt"
    )


# --- chaos seat: adversarial cases (012 T006) --------------------------------


def test_resolve_provenance_never_raises_when_git_is_absent_from_path(tmp_path, monkeypatch):
    """Contract §2.7 / data-model §2.2 'never raises': with no git binary
    reachable (PATH pointing at an empty dir) and no repository at the
    source root, resolution falls through to the environment layer and
    then unknown -- no FileNotFoundError, no CalledProcessError."""
    monkeypatch.setenv("PATH", str(tmp_path))  # an empty dir: no git on it
    monkeypatch.delenv("KROKER_COMMIT", raising=False)
    monkeypatch.delenv("KROKER_TREE_DIRTY", raising=False)
    plain = tmp_path / "plain-dir"
    plain.mkdir()
    prov = asyncio.run(resolve_provenance(plain))
    assert isinstance(prov, Provenance)
    assert prov.kroker_commit == UNKNOWN_COMMIT
    assert prov.tree_dirty is None


def test_resolve_provenance_env_layer_still_works_without_git_on_path(tmp_path, monkeypatch):
    """The same absent-git setup with KROKER_COMMIT set: the environment
    layer must carry the record on its own."""
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("KROKER_COMMIT", "env-only-commit")
    monkeypatch.delenv("KROKER_TREE_DIRTY", raising=False)
    plain = tmp_path / "plain-dir"
    plain.mkdir()
    prov = asyncio.run(resolve_provenance(plain))
    assert prov.kroker_commit == "env-only-commit"
    assert prov.tree_dirty is None


def test_resolve_provenance_nonexistent_source_root_behaves_like_no_repository(
    tmp_path, monkeypatch
):
    """A source root that is not a directory at all is not a crash: it is
    'no repository', so resolution falls to env or unknown, never raises."""
    monkeypatch.delenv("KROKER_COMMIT", raising=False)
    monkeypatch.delenv("KROKER_TREE_DIRTY", raising=False)
    ghost = tmp_path / "does" / "not" / "exist"
    prov = asyncio.run(resolve_provenance(ghost))
    assert prov.kroker_commit == UNKNOWN_COMMIT
    assert prov.tree_dirty is None

    monkeypatch.setenv("KROKER_COMMIT", "abc")
    prov = asyncio.run(resolve_provenance(ghost))
    assert prov.kroker_commit == "abc"


def test_prompt_sha_for_differs_across_prompted_roles():
    """Angle 3, second half: two DIFFERENT prompted roles hash differently.
    This can only fail legitimately if two roles shipped byte-identical
    instructions.md -- if that assertion fires, report the collision to the
    orchestrator instead of loosening the test."""
    import sdlc.benchmarks.provenance as prov_mod

    model = "anthropic:claude-sonnet-4-6"
    roles = sorted(r for r in PROMPTED_ROLES)
    seen: dict[str, str] = {}
    for role in roles:
        sha = prov_mod.prompt_sha_for(role, model)
        owner = seen.get(sha)
        assert owner is None, (
            f"roles {owner!r} and {role!r} ship identical instructions.md "
            "(same prompt_sha); report this collision rather than asserting it away"
        )
        seen[sha] = role


# --- PROMPTED_ROLES ------------------------------------------------------------


def test_prompted_roles_is_the_registry_instruction_set():
    """PROMPTED_ROLES pins the REGISTRY-instruction set -- prompt_sha_for
    branches on registry presence. Orchestrator ruling: this 14-role set is
    NOT the record-writer inventory; that stage vocabulary is pinned by the
    CELL_STAGE_ORDER check in tests/test_benchmark_models.py (T002). The
    14 roles whose agents/<role>/instructions.md ships today:"""
    assert isinstance(PROMPTED_ROLES, frozenset)
    assert PROMPTED_ROLES == frozenset(r for r in REGISTRY if REGISTRY[r].instructions is not None)
    assert PROMPTED_ROLES == frozenset(
        {
            "adversary",
            "analyst",
            "architect",
            "clarify",
            "deep_review",
            "devops_planner",
            "discover",
            "handoff",
            "merge_verdict",
            "planner",
            "qa",
            "research",
            "reviewer",
            "risk",
        }
    )
