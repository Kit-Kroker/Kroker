"""S4 -- frontend entry points (FR-912).

BrownKit's rule is that routes are grouped "by user journey, not by component
hierarchy": /payments, /payments/:id and /payments/new are ONE candidate. That
is the same reduction S3 applies to PaymentController + PaymentSettlementJob,
so it uses the same normalizer (D9, naming.py).

Two extraction shapes, because frameworks split that way:
  * FILE CONVENTION -- Next.js app/ and pages/, SvelteKit src/routes/, Nuxt
    pages/. The path IS the route.
  * CONFIGURED ROUTES -- React Router / Vue Router objects, where a literal
    `path:` or `path=` carries it.

FAIL-CLOSED on a recognized-but-unfingerprinted framework, exactly as S3 is
(P2-D1): extracting only what we recognise would hand a partial route set
downstream while looking complete.

Pure: blobs in, records out.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from ....measurement import Measurement
from ..models import (
    C_FRONTEND_ENTRY,
    CandidateMember,
    Confidence,
    EvidenceRef,
    MemberKind,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    SourceCandidate,
    family_of,
)
from ..naming import head_token, normalize

SIGNAL_ID = "S4"
VERSION = 1

FRONTEND_EXTENSIONS: tuple[str, ...] = (
    ".tsx",
    ".jsx",
    ".ts",
    ".js",
    ".vue",
    ".svelte",
    ".json",
)

# A dependency name in a package.json is the honest detector: a framework a
# repository DEPENDS on is one it uses, while an import in one file may be a
# comment or a fixture (S3's review finding 4, one signal over).
_DEP = r'"{m}"\s*:'

SUPPORTED_DEPS: tuple[tuple[str, str], ...] = (
    ("next", _DEP.format(m="next")),
    ("sveltekit", _DEP.format(m=r"@sveltejs/kit")),
    ("nuxt", _DEP.format(m="nuxt")),
    ("react_router", _DEP.format(m=r"react-router(?:-dom)?")),
    ("vue_router", _DEP.format(m=r"vue-router")),
)

UNSUPPORTED_DEPS: tuple[tuple[str, str], ...] = (
    ("angular", _DEP.format(m=r"@angular/core")),
    ("ember", _DEP.format(m=r"ember-source")),
    ("remix", _DEP.format(m=r"@remix-run/react")),
    ("solid_start", _DEP.format(m=r"@solidjs/start")),
)

# (framework, path regex, the group holding the route-bearing path segment)
_FILE_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("next", re.compile(r"^(?:src/)?app/(.*/)?page\.(?:tsx|jsx|ts|js)$")),
    (
        "next",
        re.compile(
            r"^(?:src/)?pages/(?!api/)(?!_(?:app|document|error))(.*)"
            r"\.(?:tsx|jsx|ts|js)$"
        ),
    ),
    ("sveltekit", re.compile(r"^(?:src/)?routes/(.*/)?\+page\.svelte$")),
    ("nuxt", re.compile(r"^(?:src/)?pages/(.*)\.vue$")),
)

# A literal route in a router config. Both shapes in one table because a Vue
# route object and a React Router object are the same literal.
_CONFIG_ROUTES: tuple[re.Pattern[str], ...] = (
    re.compile(r"""<Route\b[^>]*\bpath\s*=\s*['"]([^'"]+)['"]"""),
    re.compile(r"""\bpath\s*:\s*['"]([^'"]+)['"]"""),
)

# Segments that prefix a route rather than name a journey.
_PATH_PREFIXES: frozenset[str] = frozenset(
    {
        "app",
        "pages",
        "routes",
        "src",
        "_next",
        "public",
    }
)


class _Route(BaseModel):
    model_config = {"frozen": True}
    value: str
    path: str
    line: int | None = None


def _url_from_path(captured: str) -> str:
    """A file-convention route from the captured path fragment.

    Route groups -- Next's `(marketing)`, SvelteKit's `(app)` -- are layout
    devices and carry no URL segment. Dynamic segments become `:name` so a
    route reads the same whichever framework wrote it, and a catch-all
    becomes `*`.
    """
    segments: list[str] = []
    for raw in captured.strip("/").split("/"):
        if not raw or raw == "index":
            continue
        if raw.startswith("(") and raw.endswith(")"):
            continue
        if raw.startswith("[...") or raw.startswith("[[..."):
            segments.append("*")
            continue
        if raw.startswith("[") and raw.endswith("]"):
            segments.append(f":{raw.strip('[]')}")
            continue
        segments.append(raw)
    return "/" + "/".join(segments)


def detected(blobs: Mapping[str, str]) -> tuple[set[str], set[str]]:
    """(supported, unsupported) frontend frameworks the repository DEPENDS
    on, read from every package.json in the tree."""
    manifests = "\n".join(
        blobs[p] for p in sorted(blobs) if posixpath.basename(p) == "package.json"
    )
    supported = {name for name, pattern in SUPPORTED_DEPS if re.search(pattern, manifests)}
    unsupported = {name for name, pattern in UNSUPPORTED_DEPS if re.search(pattern, manifests)}
    return supported, unsupported


def _file_routes(blobs: Mapping[str, str], active: set[str]) -> list[_Route]:
    out: list[_Route] = []
    for path in sorted(blobs):
        for framework, pattern in _FILE_ROUTES:
            if framework not in active:
                continue
            match = pattern.match(path)
            if match:
                out.append(_Route(value=_url_from_path(match.group(1) or ""), path=path))
                break
    return out


def _config_routes(blobs: Mapping[str, str]) -> list[_Route]:
    out: list[_Route] = []
    for path in sorted(blobs):
        if posixpath.basename(path) == "package.json":
            continue
        text = blobs[path]
        for pattern in _CONFIG_ROUTES:
            for match in pattern.finditer(text):
                raw = match.group(1).strip()
                if not raw.startswith("/"):
                    continue
                out.append(
                    _Route(
                        value=re.sub(r"\*+$", "*", raw),
                        path=path,
                        line=text.count("\n", 0, match.start()) + 1,
                    )
                )
    return out


def _journey(route: _Route) -> str:
    """The journey a route belongs to: its first non-parameter, non-prefix
    segment, falling back to the head token of its file's parent directory."""
    for segment in route.value.strip("/").split("/"):
        if not segment or segment[0] in ":*":
            continue
        if segment.lower() in _PATH_PREFIXES:
            continue
        return segment
    parent = posixpath.basename(posixpath.dirname(route.path))
    return head_token(parent) if parent else "root"


def _gap(reason: str) -> SignalOutput:
    nc = Measurement.not_collected(reason)
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S4,
            family=family_of(ScanSignalId.S4),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=nc,
            categories={C_FRONTEND_ENTRY: nc},
        )
    )


def evaluate(blobs: Mapping[str, str], skipped: Sequence[str] = ()) -> SignalOutput:
    """`blobs` is path -> text for every readable, in-bound frontend blob.
    `skipped` names the blobs over MAX_BLOB_BYTES; a partial route set must
    not pass as a complete one (spec section 6)."""
    if skipped:
        return _gap(
            f"frontend_entry_points: {len(skipped)} blob(s) over "
            f"MAX_BLOB_BYTES not read (first: {skipped[0]}); a partial scan "
            f"must not pass as a complete one (spec section 6)"
        )
    supported, unsupported = detected(blobs)
    if unsupported:
        return _gap(
            f"frontend_entry_points: detected framework(s) "
            f"{sorted(unsupported)} have no fingerprint here; extracting only "
            f"{sorted(supported)} would hand a partial route set downstream "
            f"while looking complete (D5, P2-D1)"
        )
    if not supported:
        return _gap(
            "frontend_entry_points: no frontend framework in any package.json "
            "dependency list -- BrownKit's has_frontend=false adaptation, "
            "recorded as a gap rather than as an empty route list (D5)"
        )

    routes = _file_routes(blobs, supported) + _config_routes(blobs)
    if not routes:
        return _gap(
            f"frontend_entry_points: {sorted(supported)} is declared, but no "
            f"route matched a file convention or a literal router path -- a "
            f"framework whose routes we cannot read is not a framework with "
            f"no routes (D5)"
        )

    grouped: dict[str, list[_Route]] = {}
    for route in routes:
        name = _journey(route)
        grouped.setdefault(normalize(name) or name.lower(), []).append(route)

    candidates: list[SourceCandidate] = []
    for key, group in sorted(grouped.items()):
        members = [
            CandidateMember(kind=MemberKind.FRONTEND_ROUTE, value=r.value, path=r.path, line=r.line)
            for r in group
        ]
        candidates.append(
            SourceCandidate(
                signal=ScanSignalId.S4,
                local_id=f"S4-{key}",
                name=key,
                rule="s4_route_journey",
                detail=f"{len(members)} route(s) grouped by user journey, not by "
                f"component hierarchy.",
                confidence_contribution=(
                    Confidence.HIGH
                    if len(members) > 2
                    else Confidence.MEDIUM
                    if len(members) > 1
                    else Confidence.LOW
                ),
                members=members,
                evidence=[
                    EvidenceRef(path=r.path, lines=str(r.line) if r.line else "") for r in group
                ],
            )
        )

    candidates.sort(key=lambda c: c.local_id)
    collected = Measurement.measured(float(len(candidates)))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S4,
            family=family_of(ScanSignalId.S4),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=collected,
            categories={C_FRONTEND_ENTRY: collected},
        ),
        sources=candidates,
    )
