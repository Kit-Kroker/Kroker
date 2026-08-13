"""E-47b D6: import-edge extraction and resolution.

Broad and shallow by decision: one regex table keyed by import FORM, covering
the 18 languages in SOURCE_EXTENSIONS, rather than a per-language AST. The
accepted cost is that dynamic references (DI containers, reflection,
string-keyed module loading) are invisible; the dead guard (D7, attribution.py)
bounds what that costs, and test_discover_mutation_corpus pins the known false
positive rather than leaving it a docstring caveat.

Pure: text and paths in, a graph out. No disk, no subprocess (NFR-9).
"""
from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from typing import NamedTuple

from ...measurement import Measurement
from ..scan.sources import SOURCE_EXTENSIONS
from .models import ReferenceGraph, UnresolvedEdge


class ImportForm(NamedTuple):
    name: str
    extensions: frozenset[str]
    pattern: re.Pattern[str]        # group 1 is the target
    relative: bool | None = None    # None: decide from the target string


_PY = frozenset({".py"})
_JS = frozenset({".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"})
_JVM = frozenset({".java", ".kt", ".scala"})
_RB = frozenset({".rb"})
_PHP = frozenset({".php"})
_CS = frozenset({".cs"})
_RS = frozenset({".rs"})
_EX = frozenset({".ex", ".exs"})
_SWIFT = frozenset({".swift"})
_GO = frozenset({".go"})

IMPORT_FORMS: tuple[ImportForm, ...] = (
    ImportForm("python_from", _PY,
               re.compile(r"(?m)^\s*from\s+([.\w]+)\s+import\b")),
    # `from <dots> import name` -- the bare relative form. python_from above
    # captures only the package dots (".") and drops the imported name, which
    # is the actual edge target; this form captures the name and treats it as
    # a sibling (correct for the common single-dot case). build() skips the
    # pure-dot target python_from emits, so it never pollutes the rate.
    ImportForm("python_from_bare", _PY,
               re.compile(r"(?m)^\s*from\s+\.+\s+import\s+(\w+)"),
               relative=True),
    ImportForm("python_import", _PY,
               re.compile(r"(?m)^\s*import\s+([\w.]+)")),
    ImportForm("js_from", _JS,
               re.compile(r"""(?m)\bfrom\s+['"]([^'"]+)['"]""")),
    ImportForm("js_bare", _JS,
               re.compile(r"""(?m)^\s*import\s+['"]([^'"]+)['"]""")),
    ImportForm("js_require", _JS,
               re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]""")),
    ImportForm("js_dynamic", _JS,
               re.compile(r"""\bimport\(\s*['"]([^'"]+)['"]""")),
    ImportForm("go_import", _GO,
               re.compile(r"""(?m)^\s*(?:import\s+)?_?\s*"([\w./-]+)"\s*$""")),
    ImportForm("jvm_import", _JVM,
               re.compile(r"(?m)^\s*import\s+(?:static\s+)?([\w.]+)"),
               relative=False),
    ImportForm("ruby_require_relative", _RB,
               re.compile(r"""(?m)^\s*require_relative\s+['"]([^'"]+)['"]"""),
               relative=True),
    ImportForm("ruby_require", _RB,
               re.compile(r"""(?m)^\s*require\s+['"]([^'"]+)['"]""")),
    ImportForm("php_use", _PHP,
               re.compile(r"(?m)^\s*use\s+([\w\\]+)"), relative=False),
    ImportForm("php_include", _PHP,
               re.compile(r"""\b(?:require|include)(?:_once)?\s*\(?\s*"""
                          r"""['"]([^'"]+)['"]""")),
    ImportForm("csharp_using", _CS,
               re.compile(r"(?m)^\s*using\s+([\w.]+)\s*;"), relative=False),
    ImportForm("rust_use", _RS,
               re.compile(r"(?m)^\s*(?:pub\s+)?use\s+([\w:]+)"),
               relative=False),
    ImportForm("rust_mod", _RS,
               re.compile(r"(?m)^\s*(?:pub\s+)?mod\s+(\w+)\s*;"),
               relative=True),
    ImportForm("elixir_alias", _EX,
               re.compile(r"(?m)^\s*(?:alias|import)\s+([\w.]+)"),
               relative=False),
    ImportForm("swift_import", _SWIFT,
               re.compile(r"(?m)^\s*import\s+(\w+)"), relative=False),
)

# D7 clause 1's "extractor table": a file whose extension is absent here was
# never parsed, so it can never be called dead.
EXTRACTOR_EXTENSIONS: frozenset[str] = frozenset(
    ext for form in IMPORT_FORMS for ext in form.extensions)

_BY_NAME: dict[str, ImportForm] = {f.name: f for f in IMPORT_FORMS}


def extension_of(path: str) -> str:
    return posixpath.splitext(path)[1].lower()


def extract(path: str, text: str) -> list[tuple[str, str]]:
    """(form_name, raw target) pairs, sorted and deduped (NFR-10)."""
    ext = extension_of(path)
    found: set[tuple[str, str]] = set()
    for form in IMPORT_FORMS:
        if ext not in form.extensions:
            continue
        for match in form.pattern.finditer(text):
            target = match.group(1).strip()
            if target:
                found.add((form.name, target))
    return sorted(found)


def is_relative(form_name: str, target: str) -> bool:
    """Relative imports are the ones whose failure is EXTRACTOR failure; a
    dotted import matching nothing is just an external package (D6)."""
    form = _BY_NAME[form_name]
    if form.relative is not None:
        return form.relative
    return target.startswith(".")


# A directory is referenced through one of these when it is imported by name.
_INDEX_NAMES: tuple[str, ...] = ("index", "__init__", "mod", "main")

# Segment separators across the dotted/namespaced forms: a.b.c, A\B,
# crate::a::b, example.com/pkg/svc.
_SEGMENTS = re.compile(r"[.\\/]+|::")

# Leading segments that name the current crate/package rather than a directory.
_ROOT_WORDS: frozenset[str] = frozenset({"crate", "self", "super"})


def _candidate_paths(fragment: str) -> tuple[str, ...]:
    """Repo paths a extension-free fragment could name."""
    if not fragment:
        return ()
    direct = tuple(f"{fragment}{ext}" for ext in SOURCE_EXTENSIONS)
    indexed = tuple(f"{fragment}/{name}{ext}"
                    for name in _INDEX_NAMES for ext in SOURCE_EXTENSIONS)
    return direct + indexed


def _relative_fragment(importer: str, target: str) -> str:
    base = posixpath.dirname(importer)
    if target.startswith("./") or target.startswith("../"):
        return posixpath.normpath(posixpath.join(base, target))
    if target.startswith("."):
        # Python: one dot is "this package", each extra dot walks up one.
        dots = len(target) - len(target.lstrip("."))
        rest = target[dots:].replace(".", "/")
        up = base
        for _ in range(dots - 1):
            up = posixpath.dirname(up)
        return posixpath.normpath(posixpath.join(up, rest)) if rest else up
    # rust `mod x;` and ruby require_relative: sibling of the importer.
    return posixpath.normpath(posixpath.join(base, target))


def _dotted_fragment(target: str) -> str:
    parts = [p for p in _SEGMENTS.split(target) if p]
    while parts and parts[0] in _ROOT_WORDS:
        parts = parts[1:]
    return "/".join(parts)


def _matches(fragment: str, inventory: Mapping[str, str],
             *, exact: bool) -> list[str]:
    """Paths the fragment names. `exact` for relative imports (the fragment
    is a full repo path); suffix matching for dotted ones."""
    candidates = _candidate_paths(fragment)
    if exact:
        return sorted(c for c in candidates if c in inventory)
    return sorted(
        path for path in inventory
        for candidate in candidates
        if path == candidate or path.endswith(f"/{candidate}"))


def build(inventory: Mapping[str, str]) -> ReferenceGraph:
    """The reference graph over one tree. Only files whose extension is in
    EXTRACTOR_EXTENSIONS are parsed; the rest are reported unparsed and can
    never be called dead (D7 clause 1)."""
    paths = sorted(inventory)
    parsed = tuple(p for p in paths
                   if extension_of(p) in EXTRACTOR_EXTENSIONS)
    unparsed = tuple(p for p in paths
                     if extension_of(p) not in EXTRACTOR_EXTENSIONS)

    edges: set[tuple[str, str]] = set()
    unresolved: list[UnresolvedEdge] = []
    relative_total = relative_failed = 0

    for path in parsed:
        for form_name, target in extract(path, inventory[path]):
            if target.strip(".") == "":
                # A pure-dot target names the package itself, not a module to
                # edge to (python_from's "." for `from . import name`); the
                # name is captured separately by python_from_bare.
                continue
            relative = is_relative(form_name, target)
            if relative:
                relative_total += 1
                fragment = _relative_fragment(path, target)
            else:
                fragment = _dotted_fragment(target)
            found = [m for m in _matches(fragment, inventory, exact=relative)
                     if m != path]
            if len(found) == 1:
                edges.add((path, found[0]))
                continue
            if len(found) > 1:
                reason = "ambiguous_suffix"
            elif relative:
                reason = "no_matching_path"
            else:
                continue        # external package: expected, not a failure
            if relative:
                relative_failed += 1
            unresolved.append(UnresolvedEdge(
                source_path=path, target=target, form=form_name,
                reason=reason, relative=relative))

    if relative_total:
        rate = Measurement.measured(relative_failed / relative_total)
    else:
        # P-D1: no relative imports is no EVIDENCE of extractor failure, not
        # evidence of failure. The dead guard trips only on MEASURED.
        rate = Measurement.not_collected(
            "no relative imports in the tree to check resolution against")

    return ReferenceGraph(
        edges=tuple(sorted(edges)),
        unresolved=tuple(sorted(
            unresolved,
            key=lambda u: (u.source_path, u.form, u.target, u.reason))),
        parsed=parsed, unparsed=unparsed, unresolved_relative_rate=rate)
