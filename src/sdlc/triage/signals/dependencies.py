"""FR-902 dependency health (E-41a). Pure logic over parsed manifests.

The advisory half arrives as an AdvisoryResult the activity fetched: this
module never performs I/O, so "we did not look" reaches it as a Measurement
rather than as an empty list (spec D11/D16).
"""
from __future__ import annotations

import posixpath
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence

from pydantic import BaseModel

from ...measurement import Measurement
from ..advisories import AdvisoryResult
from ..models import FixClass, SignalResult, TriageFinding

SIGNAL_ID = "dependencies"
VERSION = 1

M_DIRECT = "direct_dependencies"
M_VULNERABLE = "known_vulnerable"

# Distribution name -> the module(s) it actually provides. Hand-maintained and
# deliberately SHORT: every entry is a false positive worth pre-empting, not a
# catalogue of PyPI. The table cannot be complete, which is exactly why
# unused_dependency is low severity and influences no readiness dimension.
IMPORT_ALIASES: dict[str, tuple[str, ...]] = {
    "pillow": ("PIL",),
    "beautifulsoup4": ("bs4",),
    "pyyaml": ("yaml",),
    "python-dateutil": ("dateutil",),
    "python-dotenv": ("dotenv",),
    "scikit-learn": ("sklearn",),
    "opencv-python": ("cv2",),
    "attrs": ("attr", "attrs"),
    "protobuf": ("google",),
    "psycopg2-binary": ("psycopg2",),
    "python-multipart": ("multipart",),
}

# Packages that are legitimately never imported: runners, linters, build
# backends, and plugins loaded through entry points.
TOOLING_NAMES = frozenset({
    "pytest", "ruff", "mypy", "coverage", "black", "flake8", "isort", "tox",
    "hatchling", "setuptools", "wheel", "build", "twine", "pre-commit",
    "pip", "uv", "poetry", "nox", "bandit", "pylint",
})
TOOLING_PREFIXES = ("pytest-", "types-", "flake8-", "sphinx", "mypy-",
                    "pytest_")


class Declared(BaseModel):
    """One direct dependency as a manifest declares it."""
    name: str                 # PEP 503 normalized
    raw: str                  # the declaration verbatim -- used as evidence
    manifest: str             # repo-relative path it came from
    constraint: str = ""      # "" when unconstrained
    line: int | None = None


def normalize(name: str) -> str:
    """PEP 503 normalization: runs of -, _ and . collapse to a single -."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


# name, optional [extras], then everything up to a marker or comment.
_REQ = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"\s*(?:\[[^\]]*\])?"
    r"\s*(?P<spec>[^;#]*)")


def _declared(name: str, raw: str, manifest: str, spec: str,
              line: int | None = None) -> Declared:
    return Declared(name=normalize(name), raw=raw.strip(), manifest=manifest,
                    constraint=spec.strip(), line=line)


def parse_requirements(manifest: str, text: str) -> list[Declared]:
    """Direct dependencies from a requirements.txt.

    Skips comments, blank lines, option lines (-r/-e/--index-url) and URLs:
    an included file is a different manifest, and a VCS or path install has
    no name we can normalize honestly.
    """
    out: list[Declared] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if "://" in line:
            continue
        match = _REQ.match(line)
        if match:
            out.append(_declared(match.group("name"), line, manifest,
                                 match.group("spec"), lineno))
    return out


def _poetry_constraint(spec: object) -> str:
    """Extract a version constraint from a Poetry dependency spec.

    Poetry uses ``"^2.0"`` (caret) or ``{version = ">=7.0", extras = [...]}``.
    The caret/tilde form floats and is correctly reported as unpinned by
    _is_pinned (which looks for ``==``). A local path (``{path = "..."}``)
    has no version and is reported as unconstrained."""
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        return str(spec.get("version", ""))
    return ""


def parse_pyproject(manifest: str, text: str) -> list[Declared]:
    """Direct dependencies from [project] and [project.optional-dependencies].

    A malformed pyproject yields no declarations rather than raising: the
    activity turns a raise into not_collected for the whole signal, and one
    unparseable manifest should not erase a sibling requirements.txt.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    out: list[Declared] = []

    # PEP 621: [project.dependencies] and [project.optional-dependencies]
    project = data.get("project") or {}
    specs: list[str] = list(project.get("dependencies") or [])
    for group in (project.get("optional-dependencies") or {}).values():
        specs.extend(group or [])
    for spec in specs:
        match = _REQ.match(str(spec))
        if match:
            out.append(_declared(match.group("name"), str(spec), manifest,
                                 match.group("spec")))

    # Poetry: [tool.poetry.dependencies] is a dict, not a list. poetry.lock
    # is in PythonToolchain.lockfiles, so Poetry repos are in scope, and a
    # silent MEASURED 0 here is the conflation this signal exists to prevent.
    # tomllib gives parsed values, not verbatim text, so raw="" and evidence
    # is not set: _verified keeps findings without evidence, and the drift
    # guard is a no-op for rules whose quote is not verbatim-reconstructable.
    poetry = (data.get("tool") or {}).get("poetry") or {}
    poetry_deps = poetry.get("dependencies") or {}
    if isinstance(poetry_deps, dict):
        for name, spec in poetry_deps.items():
            if name == "python":
                continue                  # Python version constraint, not a dep
            constraint = _poetry_constraint(spec)
            out.append(Declared(
                name=normalize(name), raw="", manifest=manifest,
                constraint=constraint))
    for group in (poetry.get("group") or {}).values():
        group_deps = (group or {}).get("dependencies") or {}
        if isinstance(group_deps, dict):
            for name, spec in group_deps.items():
                constraint = _poetry_constraint(spec)
                out.append(Declared(
                    name=normalize(name), raw="", manifest=manifest,
                    constraint=constraint))

    return out


PARSERS = {
    "pyproject.toml": parse_pyproject,
    "requirements.txt": parse_requirements,
}


def parse_manifests(blobs: Mapping[str, str]) -> list[Declared]:
    """Every declaration across the manifests we recognize, keyed by the
    manifest's BASENAME so a monorepo's apps/web/requirements.txt parses too."""
    out: list[Declared] = []
    for path in sorted(blobs):
        parser = PARSERS.get(posixpath.basename(path))
        if parser is not None:
            out.extend(parser(path, blobs[path]))
    return out


_FROM_IMPORT = re.compile(
    r"^[ \t]*from[ \t]+(?P<path>[\w.]+)[ \t]+import[ \t]+(?P<names>[^\n#]+)",
    re.MULTILINE)

_PLAIN_IMPORT = re.compile(
    r"^[ \t]*import[ \t]+(?P<names>[^\n#]+)",
    re.MULTILINE)


def _add_name(out: set[str], raw: str) -> None:
    """Extract the first identifier from `raw`, handling aliases and dots.

    `A as B` yields A; `A.B` yields A then B; `*` and non-identifier tokens
    are skipped."""
    first = raw.strip().strip("()").split()
    if not first or first[0] == "as":
        return
    for seg in first[0].split("."):
        if seg and seg[0].isalpha() and seg != "*":
            out.add(seg)


def imported_modules(texts: Iterable[str]) -> set[str]:
    """Module names imported anywhere in the given source.

    Captures ALL segments of dotted import paths (``from sdlc.triage import
    models`` yields sdlc, triage, AND models), not just the root segment. The
    root-only behaviour caused scaffold's unreferenced_module to flag 97 of
    128 files in a real repo: ``from sdlc.triage.signals import scaffold``
    yielded only "sdlc", so "scaffold" never appeared in the imported set.

    Regex, not AST, deliberately: this runs over every source file and must
    survive a file that does not parse, which is common in the repositories
    Tier 0 triages. Relative imports (``from .models import X``) are handled
    to the extent a pathless regex allows: the module segments after the
    leading dots are captured.
    """
    out: set[str] = set()
    for text in texts:
        for match in _FROM_IMPORT.finditer(text):
            # All segments of the from-path (strip leading dots for relative)
            for seg in match.group("path").lstrip(".").split("."):
                if seg and seg[0].isalpha():
                    out.add(seg)
            # Names imported from the module
            for name in match.group("names").split(","):
                _add_name(out, name)
        for match in _PLAIN_IMPORT.finditer(text):
            for name in match.group("names").split(","):
                _add_name(out, name)
    return out


def _is_pinned(constraint: str) -> bool:
    """A constraint pins iff it fixes an exact version. `>=`, `~=` and a bare
    name all float; `!=` alone excludes without fixing."""
    return "==" in constraint


def _is_tooling(name: str) -> bool:
    return name in TOOLING_NAMES or name.startswith(TOOLING_PREFIXES)


def _provides(name: str) -> tuple[str, ...]:
    """The module names a distribution may supply: its alias-table entry if it
    has one, otherwise both the dashed and underscored forms of its name."""
    if name in IMPORT_ALIASES:
        return IMPORT_ALIASES[name]
    return (name, name.replace("-", "_"))


def _finding(rule: str, severity: str, detail: str, fix_class: FixClass,
             path: str = "", line: int | None = None,
             evidence: str = "") -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class, path=path,
                         line=line, evidence=evidence)


def evaluate(declared: Sequence[Declared], lockfile_present: bool,
             imported: set[str],
             advisories: AdvisoryResult) -> SignalResult:
    """Dependency health over parsed declarations.

    `imported` is the top-level module set from `imported_modules`.
    `advisories` carries its own Measurement, which becomes the
    known_vulnerable metric unchanged -- this function never converts a
    not_collected lookup into a zero.
    """
    findings: list[TriageFinding] = []

    for d in sorted(declared, key=lambda d: (d.manifest, d.name)):
        if not _is_pinned(d.constraint):
            mitigation = ("a lockfile is tracked, so resolution is still "
                          "reproducible" if lockfile_present
                          else "no lockfile is tracked, so two installs can "
                               "resolve to different versions")
            findings.append(_finding(
                "unpinned_dependency", "medium",
                f"{d.name} is declared without an exact version and "
                f"{mitigation}.",
                FixClass.MECHANICAL, d.manifest, d.line, d.raw))

    by_name: dict[str, set[str]] = {}
    origin: dict[str, Declared] = {}
    for d in declared:
        by_name.setdefault(d.name, set()).add(d.constraint)
        origin.setdefault(d.name, d)
    for name in sorted(by_name):
        if len(by_name[name]) > 1:
            constraints = ", ".join(sorted(c or "(none)"
                                           for c in by_name[name]))
            findings.append(_finding(
                "duplicate_dependency", "medium",
                f"{name} is declared more than once with conflicting "
                f"constraints ({constraints}); which one wins depends on "
                f"install order.",
                FixClass.MECHANICAL, origin[name].manifest))

    for adv in advisories.advisories:
        d = origin.get(normalize(adv.package))
        findings.append(_finding(
            "known_vulnerable", adv.severity,
            f"{adv.package} matches {adv.advisory_id}"
            f"{': ' + adv.summary if adv.summary else ''}. Upgrading is a "
            f"one-line edit; deciding the upgrade is safe is not.",
            # JUDGEMENT per spec D7's shape -- E-44 promises a MECHANICAL
            # finding can be closed by a PR without judgement, and a version
            # bump can break the build.
            FixClass.JUDGEMENT,
            d.manifest if d else "", d.line if d else None,
            d.raw if d else ""))

    for name in sorted(by_name):
        if _is_tooling(name):
            continue
        if any(module in imported for module in _provides(name)):
            continue
        d = origin[name]
        findings.append(_finding(
            "unused_dependency", "low",
            f"{name} is declared but no source file imports it. Distribution "
            f"names and import names diverge, so confirm before removing.",
            FixClass.MECHANICAL, d.manifest, d.line, d.raw))

    return SignalResult(
        signal=SIGNAL_ID, version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={
            M_DIRECT: Measurement.measured(float(len(by_name))),
            # Passed through unchanged: a not_collected lookup stays
            # not_collected here (D16).
            M_VULNERABLE: advisories.collected,
        })
