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
from typing import NamedTuple


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
