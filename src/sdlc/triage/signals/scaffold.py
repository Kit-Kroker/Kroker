"""FR-902 generator scaffolding and dead code (E-41b).

THE OWNER OF structure_discernible (spec D12). `compute_readiness` admits
exactly one signal per readiness key, so "E-41b sharpens the dimension"
cannot mean "E-41b also reports it" -- ownership moved here and baseline
dropped it. The consequence is deliberate: a scaffold signal that fails
leaves the dimension unmeasured, which forces INDETERMINATE, and "we could
not tell whether this is real code or a generator's output" is the honest
readiness verdict for that state.

Fingerprint-first, history-corroborating (spec D13). History alone misfires
hardest on exactly the repositories Tier 0 targets: a vibe-coded repo is
often one enormous initial commit, where "untouched since import" is true of
every file including the hand-written ones. As corroboration it is additive
and cannot invent a finding.
"""

from __future__ import annotations

import fnmatch
import posixpath
from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from ...measurement import Measurement
from ...toolchain.adapters import ToolchainAdapter
from ..models import M_STRUCTURE, FindingSeverity, FixClass, SignalResult, TriageFinding
from .dependencies import imported_modules

SIGNAL_ID = "scaffold"
VERSION = 1

M_HISTORY_BASIS = "history_basis"
M_SCAFFOLD_FILES = "scaffold_files"

# A repository whose source is this share of fingerprinted generator output
# is not structurally discernible. Not 1.0: a real project keeps its
# generator's manage.py, and one surviving default file is not scaffolding.
SCAFFOLD_RATIO_THRESHOLD = 0.9

# Language-agnostic source extensions for the STRUCTURE assessment. The
# adapter's source_extensions is language-specific and only PythonToolchain
# exists today, so gating structure on it would make the dimension
# permanently not_collected for the JS/TS repos most FINGERPRINTS target.
# Structure asks "does this repo have real code?", which is not a
# per-language question. Dead-code detection (unreferenced_module) DOES use
# the adapter's extensions, because import parsing is language-specific.
_SOURCE_EXTENSIONS = (
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".php",
    ".cs",
    ".kt",
    ".swift",
)

# Paths that are entrypoints by convention and therefore never "unreferenced"
# merely because nothing imports them.
_ENTRYPOINT_STEMS = frozenset(
    {
        "__init__",
        "__main__",
        "main",
        "manage",
        "conftest",
        "setup",
        "wsgi",
        "asgi",
        "app",
    }
)


class Fingerprint(BaseModel):
    """A generator's output, identified by a path convention AND a content
    marker that survives only while nobody has edited the file. Both halves
    are required: the path alone would flag every README."""

    generator: str
    path_glob: str
    marker: str


FINGERPRINTS: tuple[Fingerprint, ...] = (
    Fingerprint(
        generator="create-next-app",
        path_glob="README.md",
        marker="bootstrapped with [`create-next-app`]",
    ),
    Fingerprint(
        generator="create-next-app", path_glob="app/page.tsx", marker="Get started by editing"
    ),
    Fingerprint(
        generator="create-next-app", path_glob="app/page.js", marker="Get started by editing"
    ),
    Fingerprint(
        generator="create-next-app", path_glob="pages/index.js", marker="Get started by editing"
    ),
    Fingerprint(
        generator="create-react-app",
        path_glob="src/App.js",
        marker="Edit <code>src/App.js</code> and save to reload.",
    ),
    Fingerprint(
        generator="create-react-app",
        path_glob="src/App.tsx",
        marker="Edit <code>src/App.tsx</code> and save to reload.",
    ),
    Fingerprint(generator="vite", path_glob="index.html", marker="<title>Vite +"),
    Fingerprint(
        generator="django-admin",
        path_glob="manage.py",
        marker="Django's command-line utility for administrative tasks",
    ),
    Fingerprint(
        generator="django-admin",
        path_glob="*/settings.py",
        marker="keep the secret key used in production secret",
    ),
)


def scaffolded_paths(blobs: Mapping[str, str]) -> dict[str, str]:
    """path -> generator, for every blob still carrying its generator's
    marker. A path that matches a glob but whose marker is gone has been
    edited and is not reported."""
    out: dict[str, str] = {}
    for path in sorted(blobs):
        for fp in FINGERPRINTS:
            if fnmatch.fnmatch(path, fp.path_glob) and fp.marker in blobs[path]:
                out[path] = fp.generator
                break
    return out


def _finding(
    rule: str,
    severity: FindingSeverity,
    detail: str,
    fix_class: FixClass,
    path: str = "",
    evidence: str = "",
) -> TriageFinding:
    return TriageFinding(
        signal=SIGNAL_ID,
        rule=rule,
        severity=severity,
        detail=detail,
        fix_class=fix_class,
        path=path,
        evidence=evidence,
    )


def evaluate(
    paths: Sequence[str],
    blobs: Mapping[str, str],
    touch_counts: Mapping[str, int] | None,
    toolchain: ToolchainAdapter | None,
) -> SignalResult:
    """`paths` is every tracked path; `blobs` is text for the readable ones;
    `touch_counts` is path -> commits touching it, or None when the repository
    yields no usable history (D13)."""
    scaffolded = scaffolded_paths(blobs)
    findings: list[TriageFinding] = []

    for path, generator in sorted(scaffolded.items()):
        # A path absent from touch_counts (beyond max_commits, or an
        # unmatchable quoting artifact) must NOT escalate: the safe direction
        # for a false-positive-prone rule is to stay at the fingerprint level.
        count = touch_counts.get(path) if touch_counts else None
        untouched = count is not None and count <= 1
        findings.append(
            _finding(
                "generator_scaffold",
                "medium" if untouched else "low",
                f"{path} is unmodified {generator} output"
                f"{', untouched since import' if untouched else ''}. Removing or "
                f"replacing generator output is a decision about what the "
                f"application is.",
                FixClass.JUDGEMENT,
                path,
                # The marker itself is verbatim in the blob by construction, so
                # it is the natural evidence quote.
                next(
                    fp.marker
                    for fp in FINGERPRINTS
                    if fnmatch.fnmatch(path, fp.path_glob) and fp.marker in blobs[path]
                ),
            )
        )

    # Dead-code detection is language-specific: it needs the adapter's source
    # extensions and test globs, because import parsing is per-language. A repo
    # with no resolved adapter gets no unreferenced_module findings.
    exts = tuple(toolchain.source_extensions) if toolchain else ()
    test_globs = tuple(toolchain.test_globs) if toolchain else ()
    dead_source = [p for p in sorted(paths) if exts and p.endswith(exts)]

    if dead_source:
        imported = imported_modules(blobs[p] for p in dead_source if p in blobs)
        for path in dead_source:
            stem = posixpath.splitext(posixpath.basename(path))[0]
            if stem in _ENTRYPOINT_STEMS:
                continue
            if any(
                fnmatch.fnmatch(path, g) or fnmatch.fnmatch(posixpath.basename(path), g)
                for g in test_globs
            ):
                continue
            if stem in imported:
                continue
            findings.append(
                _finding(
                    "unreferenced_module",
                    "low",
                    f"{path} is not imported by any tracked source file. "
                    f"Deleting code is a decision, not a mechanical patch.",
                    FixClass.JUDGEMENT,
                    path,
                )
            )

    # Structure is language-AGNOSTIC: "does this repo have real code?" is not
    # a per-language question. Using the adapter's extensions here would make
    # the dimension permanently not_collected for the JS/TS repos most
    # FINGERPRINTS target (no JS adapter exists), and would score 0.0 for a
    # Python-marker repo whose only source is .js — a regression from
    # baseline v1's broad extension list.
    structure_source = [p for p in sorted(paths) if p.endswith(_SOURCE_EXTENSIONS)]
    if not structure_source:
        structure = Measurement.measured(0.0)
    else:
        ratio = len([p for p in structure_source if p in scaffolded]) / len(structure_source)
        structure = Measurement.measured(0.0 if ratio >= SCAFFOLD_RATIO_THRESHOLD else 1.0)

    history = (
        Measurement.measured(1.0)
        if touch_counts is not None
        else Measurement.not_collected(
            "no usable commit history: a single-commit repository says "
            "nothing about what has been touched"
        )
    )

    return SignalResult(
        signal=SIGNAL_ID,
        version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={
            M_STRUCTURE: structure,
            M_HISTORY_BASIS: history,
            M_SCAFFOLD_FILES: Measurement.measured(float(len(scaffolded))),
        },
    )
