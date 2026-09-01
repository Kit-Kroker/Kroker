"""The batched reader must match read_blob exactly (spec D10)."""

import subprocess

import pytest

from sdlc.triage.activities import read_blob, tracked_paths
from sdlc.triage.gitread import (
    MAX_BLOB_BYTES,
    TreeReader,
    is_over_size_limit,
    read_tree,
)


def _run(args, cwd):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, encoding="utf-8", check=True, stdin=subprocess.DEVNULL
    )


def _commit_repo(root, files: dict[str, str]) -> str:
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "t@example.com"], root)
    _run(["git", "config", "user.name", "T"], root)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-q", "-m", "one"], root)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        check=True,
        stdin=subprocess.DEVNULL,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    sha = _commit_repo(
        tmp_path,
        {
            "pyproject.toml": "[project]\nname = 'x'\n",
            "src/app.py": "x = 1\n",
            "empty.txt": "",
        },
    )
    return str(tmp_path), sha


def test_reader_matches_read_blob_on_blob_tree_and_missing(repo):
    repo_dir, sha = repo
    with TreeReader(repo_dir, sha) as reader:
        for path in ("pyproject.toml", "src/app.py", "empty.txt", "src", "nope.py"):
            assert reader.read(path) == read_blob(repo_dir, sha, path), path


def test_a_directory_reads_as_none_not_a_tree_listing(repo):
    repo_dir, sha = repo
    with TreeReader(repo_dir, sha) as reader:
        assert reader.read("src") is None


def test_an_empty_file_reads_as_empty_string_not_none(repo):
    repo_dir, sha = repo
    with TreeReader(repo_dir, sha) as reader:
        assert reader.read("empty.txt") == ""


def test_the_stream_stays_in_sync_after_a_missing_path(repo):
    # A missing path answers a one-line "<input> missing" with no payload.
    # Mis-handling it desynchronises every later read, which is the failure
    # mode a batched reader has and a per-file spawn cannot.
    repo_dir, sha = repo
    with TreeReader(repo_dir, sha) as reader:
        assert reader.read("nope.py") is None
        assert reader.read("src/app.py") == "x = 1\n"
        assert reader.read("also-nope") is None
        assert reader.read("pyproject.toml") == "[project]\nname = 'x'\n"


def test_read_tree_skips_binary_and_unreadable_paths(tmp_path):
    sha = _commit_repo(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01\x02")
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "two"], tmp_path)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        encoding="utf-8",
        check=True,
        stdin=subprocess.DEVNULL,
    ).stdout.strip()
    paths = tracked_paths(str(tmp_path), sha)
    got = dict(read_tree(str(tmp_path), sha, paths))
    assert got == {"a.py": "x = 1\n", "b.py": "y = 2\n"}


def test_is_over_size_limit_counts_bytes_not_characters():
    assert not is_over_size_limit("x" * MAX_BLOB_BYTES)
    assert is_over_size_limit("x" * (MAX_BLOB_BYTES + 1))
    # Three-byte characters exceed the byte limit at a third of the count.
    assert is_over_size_limit("\uffff" * 333334)


def test_a_tree_object_does_not_desync_the_stream(repo):
    # A directory resolves to a tree OBJECT, which cat-file --batch emits
    # with a payload. If that payload is not drained, the next read parses
    # the tree's bytes as a header and every later read is wrong. This is
    # the failure mode a batched reader has and a per-file spawn cannot.
    repo_dir, sha = repo
    with TreeReader(repo_dir, sha) as reader:
        assert reader.read("src") is None  # tree: payload drained
        assert reader.read("src/app.py") == "x = 1\n"  # must still read
        assert reader.read("pyproject.toml") == "[project]\nname = 'x'\n"


def test_a_tree_object_then_a_missing_path_stay_in_sync(repo):
    repo_dir, sha = repo
    with TreeReader(repo_dir, sha) as reader:
        assert reader.read("src") is None  # tree: drain payload
        assert reader.read("nope.py") is None  # missing: no payload
        assert reader.read("src/app.py") == "x = 1\n"  # must still read
