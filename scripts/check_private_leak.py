"""Private-store leak guard (016 T010, plan D-10, rule 1).

Two layers: the pre-commit hook (``--staged``) scans the ADDED lines of
the index on every commit; ``--tracked`` scans the content of every
``git ls-files`` entry (the test mode). Tokens come from the private
store configured at SDLC_PRIVATE_CASES_ROOT (the same variable the
resolver reads): oracle test node ids and function names, requirement
ids and feature values, reference module/function/class names, and
8-word shingles of the case description and rubrics. The six fixed
error-class names and the domain words of spec ruling R5 ("the domain
is a theatre box office") are excluded, so the public spec and the
generic vocabulary never fire the guard. Exit 1 on any finding; exit 0
with the note ``private store absent; skipped`` when no store is
configured or the directory is absent.

Stdlib only on purpose: the hook runs under ``language: system`` (the
host python, where the sdlc package is not installed).
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PRIVATE_CASES_ENV = "SDLC_PRIVATE_CASES_ROOT"
ABSENT_NOTE = "private store absent; skipped"

# ERROR_CLASSES of sdlc/benchmarks/tasks.py: fixed vocabulary, never a
# private token.
ERROR_CLASS_NAMES = {
    "functional",
    "security",
    "performance",
    "data_integrity",
    "error_handling",
    "api_contract",
}

# Spec 016 ruling R5: "the domain is a theatre box office." The domain
# words are public by construction (the spec names them); they are not
# tokens.
DOMAIN_WORDS = {"theatre", "box", "office"}

# Memoized token set of the last collect_tokens() call, so scan() works
# in-process against a synthetic store the test just built (the CLI
# subprocesses always re-read the env-configured store).
_TOKENS: set[str] = set()


@dataclass(frozen=True)
class Finding:
    path: str
    line: int | None
    token: str


def _keeps_identifier(name: str) -> bool:
    """Names' id-token filter: keep only identifiers that carry an
    underscore or are at least 8 characters (short bare words are noise)."""
    return "_" in name or len(name) >= 8


def _shingles(text: str, *, window: int = 8) -> set[str]:
    words = text.split()
    return {" ".join(words[i : i + window]) for i in range(0, max(0, len(words) - window + 1))}


def _description_lines(case_yaml: Path) -> list[str]:
    """The lines of the manifest's ``description`` VALUE — a block scalar
    (``description: |`` followed by deeper-indented lines) or a plain
    folded scalar (first line on the key, continuations indented under
    it; what ``yaml.safe_dump`` writes for long strings). Names: the
    shingle source is the description, never the manifest boilerplate
    around it (a private manifest structurally mirrors the public one,
    so whole-file shingling would flag the public corpus itself)."""
    lines = case_yaml.read_text(encoding="utf-8").splitlines()
    value: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^( *)description:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key_indent = len(m.group(1))
        rest = m.group(2).strip()
        if rest in ("|", "|-", ">", ">-", "|+", ">+"):
            i += 1
            while i < len(lines):
                cont = lines[i]
                if not cont.strip():
                    value.append("")
                    i += 1
                    continue
                indent = len(cont) - len(cont.lstrip())
                if indent > key_indent:
                    value.append(cont)
                    i += 1
                    continue
                break
        elif rest:
            value.append(rest)
            i += 1
            while i < len(lines):
                cont = lines[i]
                if not cont.strip():
                    break
                indent = len(cont) - len(cont.lstrip())
                if indent > key_indent:
                    value.append(cont.strip())
                    i += 1
                    continue
                break
        break
    return value


def _case_tokens(case_dir: Path) -> set[str]:
    tokens: set[str] = set()

    oracle_dir = case_dir / "oracle"
    if oracle_dir.is_dir():
        for py in sorted(oracle_dir.rglob("*.py")):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            rel = py.relative_to(oracle_dir).as_posix()
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not node.name.startswith("test"):
                    continue
                tokens.add(f"{rel}::{node.name}")
                if _keeps_identifier(node.name):
                    tokens.add(node.name)

    tasks_yaml = case_dir / "tasks.yaml"
    if tasks_yaml.is_file():
        # Minimal line parse (stdlib only): `id:` and `feature:` values.
        # Authoring keeps both on one line each.
        for raw in tasks_yaml.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*-?\s*id:\s*(\S+)\s*$", raw)
            if m and _keeps_identifier(m.group(1)):
                tokens.add(m.group(1))
            m = re.match(r"\s*feature:\s*(.+?)\s*$", raw)
            if m and m.group(1):
                tokens.add(m.group(1))

    ref_dir = case_dir / "reference"
    if ref_dir.is_dir():
        for py in sorted(ref_dir.rglob("*.py")):
            tokens.add(py.stem)  # module names: few, high-signal
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _keeps_identifier(
                    node.name
                ):
                    tokens.add(node.name)
                elif isinstance(node, ast.ClassDef) and _keeps_identifier(node.name):
                    tokens.add(node.name)

    # Description (the manifest's description VALUE, whitespace-normalised:
    # YAML folding wraps long strings, and shingles must span the folds)
    # and every rubric file.
    case_yaml = case_dir / "case.yaml"
    if case_yaml.is_file():
        description = " ".join(" ".join(_description_lines(case_yaml)).split())
        if description:
            tokens |= _shingles(description)
    for rubric in sorted(case_dir.glob("rubric-*.md")):
        if rubric.is_file():
            tokens |= _shingles(" ".join(rubric.read_text(encoding="utf-8").split()))

    return tokens - ERROR_CLASS_NAMES - DOMAIN_WORDS


def _configured_store() -> Path | None:
    value = os.environ.get(PRIVATE_CASES_ENV, "")
    return Path(value) if value else None


def collect_tokens(store_cases: Path) -> set[str]:
    """Every token of every case under the store's cases root (Names,
    Leak guard). Also memoized for in-process scan() use."""
    global _TOKENS
    tokens: set[str] = set()
    for case_yaml in sorted(Path(store_cases).glob("*/case.yaml")):
        tokens |= _case_tokens(case_yaml.parent)
    _TOKENS = tokens
    return tokens


def _active_tokens() -> set[str]:
    store = _configured_store()
    if store is not None and store.is_dir():
        return collect_tokens(store)
    return _TOKENS


def scan(paths_or_text) -> list[Finding]:
    """Find private tokens in a text string, a Path, or an iterable of
    Paths. Uses the env-configured store when present, else the tokens
    of the last collect_tokens() call."""
    tokens = _active_tokens()
    if not tokens:
        return []
    findings: list[Finding] = []

    def _scan_text(text: str, path: str) -> None:
        for no, line in enumerate(text.splitlines(), start=1):
            for token in tokens:
                if token in line:
                    findings.append(Finding(path=path, line=no, token=token))

    if isinstance(paths_or_text, str):
        _scan_text(paths_or_text, "<text>")
        return findings
    paths = [paths_or_text] if isinstance(paths_or_text, Path) else list(paths_or_text)
    for p in paths:
        p = Path(p)
        if p.is_file():
            try:
                _scan_text(p.read_text(encoding="utf-8", errors="replace"), p.as_posix())
            except OSError:
                continue
    return findings


def _staged_findings() -> list[Finding]:
    diff = subprocess.run(
        ["git", "diff", "--cached", "--unified=0"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    tokens = _active_tokens()
    if not tokens:
        return []
    findings: list[Finding] = []
    path = ""
    line_no = 0
    for raw in diff.splitlines():
        m = re.match(r"^\+\+\+ b/(.+)$", raw)
        if m:
            path = m.group(1)
            continue
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
        if m:
            line_no = int(m.group(1))
            continue
        if raw.startswith("+++") or raw.startswith("---") or raw.startswith("@@"):
            continue
        if raw.startswith("+"):
            line = raw[1:]
            for token in tokens:
                if token in line:
                    findings.append(Finding(path=path, line=line_no, token=token))
            line_no += 1
    return findings


def _tracked_findings() -> list[Finding]:
    files = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=False
    ).stdout.splitlines()
    return scan([Path(f) for f in files])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="private-store leak guard")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true", help="scan added lines of the index")
    mode.add_argument("--tracked", action="store_true", help="scan git ls-files content")
    args = parser.parse_args(argv)

    store = _configured_store()
    if store is None or not store.is_dir():
        print(ABSENT_NOTE)
        return 0

    findings = _staged_findings() if args.staged else _tracked_findings()
    for f in findings:
        loc = f"{f.path}:{f.line}" if f.line is not None else f.path
        print(f"{loc}: private token {f.token!r}")
    if findings:
        print(
            f"check-private-leak: {len(findings)} finding(s); "
            "never commit private store content (round 016 rule 1)"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
