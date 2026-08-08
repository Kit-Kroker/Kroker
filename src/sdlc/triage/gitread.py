"""Batched blob reads at a pinned commit (E-41a-d, spec D10).

`read_blob` spawns two git subprocesses per file -- `cat-file -t` to guard
against a tree path, then `show`. `secrets` calls it over every tracked path,
and three of the four signals added by E-41a-d also need whole-tree content,
so the naive extension takes a 5,000-file repository from roughly 10,000
spawns to roughly 40,000. One long-lived `git cat-file --batch` process
replaces the pair: the type guard arrives in the response header instead of
costing a spawn.

Pure of temporalio, like the signal modules. The single-blob `read_blob` in
activities.py survives for the genuinely single-file case (baseline's
.gitignore).
"""
from __future__ import annotations

import subprocess
from collections.abc import Iterator, Sequence

# The bound `secrets` applied per blob, hoisted here so every consumer of the
# reader inherits it rather than re-deciding. A minified bundle or a
# checked-in asset costs more to scan than the finding is worth, and E-41d
# owns size outliers.
MAX_BLOB_BYTES = 1_000_000


def is_over_size_limit(text: str) -> bool:
    """True when the text's UTF-8 byte length exceeds MAX_BLOB_BYTES.

    Compares bytes, not ``len(str)`` characters, so multibyte content is
    bounded honestly (a minified CJK bundle is far larger in bytes than in
    characters). `TreeReader` applies the same bound from cat-file's header,
    which is already a byte count; this function is for callers holding text.
    """
    return len(text.encode("utf-8")) > MAX_BLOB_BYTES


class TreeReader:
    """Reads blobs at one commit through a single `git cat-file --batch`.

    Carries `_git`'s ``-c safe.directory=*`` bypass forward: git's ownership
    check fires whenever the worker's SID differs from the worktree's owner,
    and that does not stop being true because the process is long-lived.

    Unlike `_git`, stdin is a PIPE rather than DEVNULL -- this is the one git
    invocation in the codebase that genuinely reads it.

    Use as a context manager; `read` outside one raises.
    """

    def __init__(self, repo_dir: str, commit_sha: str) -> None:
        self._repo_dir = repo_dir
        self._commit_sha = commit_sha
        self._proc: subprocess.Popen | None = None

    def __enter__(self) -> "TreeReader":
        self._proc = subprocess.Popen(
            ["git", "-c", "safe.directory=*", "cat-file", "--batch"],
            cwd=self._repo_dir,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)
        return self

    def __exit__(self, *exc) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.stdin.close()
            proc.wait(timeout=30)
        except Exception:                          # noqa: BLE001
            proc.kill()
            proc.wait()

    def read(self, path: str) -> str | None:
        """The file's text at the pinned commit, or None when the path does
        not resolve to a readable blob.

        Matches `read_blob`'s contract exactly -- a directory answers type
        `tree`, an absent path answers `missing`, and both yield None. That
        equivalence is what makes the `secrets` migration safe, and it is
        asserted in tests rather than assumed.

        An over-size blob yields None, but its payload is still consumed:
        leaving bytes in the pipe would desynchronise every later read.
        """
        proc = self._proc
        if proc is None:
            raise RuntimeError("TreeReader used outside its context manager")
        proc.stdin.write(f"{self._commit_sha}:{path}\n".encode())
        proc.stdin.flush()
        header = proc.stdout.readline().decode(errors="replace").strip()
        parts = header.split()
        # "<oid> SP blob SP <size>" on success; "<input> SP missing" and
        # "<input> SP ambiguous" carry no payload; a tree/tag/commit object
        # is a well-formed header we still refuse.
        if len(parts) != 3 or parts[1] != "blob":
            return None
        size = int(parts[2])
        payload = proc.stdout.read(size)
        proc.stdout.read(1)                        # the trailing LF
        if size > MAX_BLOB_BYTES:
            return None
        return payload.decode(errors="replace")


def read_tree(repo_dir: str, commit_sha: str,
              paths: Sequence[str]) -> Iterator[tuple[str, str]]:
    """(path, text) for every path resolving to a readable text blob.

    Skips non-blobs, over-size blobs and binary content -- the three skips
    `secrets` applies today, hoisted so every signal inherits them instead of
    re-deciding. Paths are read in the order given, so a caller's sorted input
    yields deterministic output.
    """
    with TreeReader(repo_dir, commit_sha) as reader:
        for path in paths:
            text = reader.read(path)
            if text is None or "\x00" in text:     # binary; nothing to quote
                continue
            yield path, text
