"""S3 -- backend entry points (FR-912). The Contract tier.

Pattern fingerprints declared here rather than parsed through a
ToolchainAdapter (D4): Python is the only adapter, so parser-only extraction
would make Tier 2 Python-only in practice, and scaffold.FINGERPRINTS already
shows the JS/TS repositories Tier 0 actually receives.

FAIL-CLOSED (P2-D1). If a recognized framework has no fingerprint here, the
whole signal reports not_collected naming it and emits NO candidates -- even
when another framework did match. S3's members become CapabilityFingerprint's
Contract tier at weight 0.55, and D5's stated hazard is that a silently-empty
Contract tier makes E-47a's matcher renormalize onto weaker tiers and risk
handing a stored BC-NNN to an unrelated capability. Plan 1's
_unmeasured_carries_no_payload forbids records on a non-MEASURED row anyway,
so "partially extracted" is not representable in the contract.

Pure: blobs in, records out.
"""
from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping

from pydantic import BaseModel

from ....measurement import Measurement
from ..models import (
    C_BACKEND_ENTRY, CandidateMember, Confidence, EvidenceRef, MemberKind,
    ScanSignalId, ScanSignalResult, SignalOutput, SignalSource, SourceCandidate,
    family_of,
)
from ..naming import GENERIC_NAMES, LAYER_NAMES, head_token, normalize

SIGNAL_ID = "S3"
VERSION = 1


class Framework(BaseModel):
    """One framework we can both DETECT and EXTRACT from."""
    name: str
    # regexes (MULTILINE) proving the framework is IMPORTED, not merely
    # mentioned. Anchored to import/require/using lines so the marker table
    # itself, a test fixture, or a `# ported from django` comment cannot trip
    # fail-closed on a repo that does not use the framework (review finding 4).
    detect: tuple[str, ...]
    pattern: str                 # regex; groups are (method, path) or (name,)
    kind: MemberKind
    method_group: int = 0        # 0 = no method group; the verb is implicit
    value_group: int = 1


class Detector(BaseModel):
    """A framework we RECOGNIZE but cannot extract from. Its presence fails
    the signal closed (P2-D1) -- naming the gap is the whole point."""
    name: str
    detect: tuple[str, ...]


# Import-line anchors shared across languages. Each is a fragment the framework's
# own import statement matches; detected() pins it to a line start so a bare
# substring in a comment or string literal cannot match.
_PY_IMPORT = r"(?m)^[ \t]*(?:from[ ]+{m}\b|import[ ]+{m}\b)"
_ESM_IMPORT = r"(?m)^[ \t]*import\b[^\n]*\bfrom[ ]+['\"]{m}['\"]"
_CJS_REQUIRE = r"(?m)^[ \t]*(?:const|let|var)[ ]+\w+[ ]*=[ ]*require\([ ]*['\"]{m}['\"]\s*\)"
_GO_IMPORT = r'(?m)^[ \t]*"{m}"'
_JAVA_IMPORT = r"(?m)^[ \t]*import[ ]+{m}"
_CS_USING = r"(?m)^[ \t]*using[ ]+{m}"
_PHP_USE = r"(?m)^[ \t]*use[ ]+{m}"

# Extraction is deliberately conservative: a decorator or router call on one
# line with a literal path. A route assembled at runtime is not extracted,
# which is a miss, not a fabrication.
FRAMEWORKS: tuple[Framework, ...] = (
    Framework(
        name="fastapi",
        detect=(_PY_IMPORT.format(m="fastapi"),),
        pattern=r"@(?:\w+)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)",
        kind=MemberKind.HTTP_ROUTE, method_group=1, value_group=2),
    Framework(
        name="flask",
        detect=(_PY_IMPORT.format(m="flask"),),
        pattern=r"@(?:\w+)\.route\(\s*['\"]([^'\"]+)",
        kind=MemberKind.HTTP_ROUTE, value_group=1),
    Framework(
        name="express",
        detect=(_ESM_IMPORT.format(m="express"), _CJS_REQUIRE.format(m="express")),
        pattern=r"\b(?:app|router)\.(get|post|put|patch|delete)"
                r"\(\s*['\"]([^'\"]+)",
        kind=MemberKind.HTTP_ROUTE, method_group=1, value_group=2),
    Framework(
        name="nestjs",
        detect=(_ESM_IMPORT.format(m=r"@nestjs/common"),),
        pattern=r"@(Get|Post|Put|Patch|Delete)\(\s*['\"]?([^'\")]*)",
        kind=MemberKind.HTTP_ROUTE, method_group=1, value_group=2),
    Framework(
        name="click",
        detect=(_PY_IMPORT.format(m="click"),),
        pattern=r"@\w+\.command\([^)]*\)\s*\ndef\s+(\w+)",
        kind=MemberKind.CLI_COMMAND, value_group=1),
    Framework(
        name="celery",
        detect=(_PY_IMPORT.format(m="celery"),),
        pattern=r"@(?:shared_task|\w+\.task)\b[^\n]*\n(?:@[^\n]*\n)*"
                r"def\s+(\w+)",
        kind=MemberKind.SCHEDULED_JOB, value_group=1),
)

UNSUPPORTED_FRAMEWORKS: tuple[Detector, ...] = (
    Detector(name="django", detect=(_PY_IMPORT.format(m="django"),)),
    Detector(name="spring", detect=(_JAVA_IMPORT.format(m=r"org\.springframework"),)),
    Detector(name="rails", detect=(
        r"(?m)^[ \t]*Rails\.application\b",
        r"(?m)^[ \t]*(?:require|gem)[ ]+['\"]rails['\"]")),
    Detector(name="laravel", detect=(_PHP_USE.format(m=r"Illuminate\\"),)),
    Detector(name="gin", detect=(_GO_IMPORT.format(m=r"github\.com/gin-gonic/gin"),)),
    Detector(name="echo", detect=(_GO_IMPORT.format(m=r"github\.com/labstack/echo"),)),
    Detector(name="aspnet", detect=(_CS_USING.format(m=r"Microsoft\.AspNetCore"),)),
    Detector(name="grpc", detect=(
        _PY_IMPORT.format(m="grpc"),
        r"(?m)^[ \t]*import[ ]+io\.grpc",
        _CS_USING.format(m=r"Grpc\.(?:AspNetCore|Core)"))),
)

# Route segments that prefix an API rather than name a business operation.
_PATH_PREFIXES: frozenset[str] = frozenset({
    "api", "apis", "rest", "graphql", "v1", "v2", "v3", "internal", "public",
    "admin", "_next",
})

# Which member kind is most contract-ish, for choosing the rule a mixed
# candidate reports. Ordered, not a set: the answer must be deterministic.
_KIND_RULE: tuple[tuple[MemberKind, str], ...] = (
    (MemberKind.HTTP_ROUTE, "s3_http_route"),
    (MemberKind.GRPC_METHOD, "s3_grpc_method"),
    (MemberKind.QUEUE_TOPIC, "s3_queue_consumer"),
    (MemberKind.SCHEDULED_JOB, "s3_scheduled_job"),
    (MemberKind.CLI_COMMAND, "s3_cli_command"),
)


def detected(blobs: Mapping[str, str]) -> tuple[set[str], set[str]]:
    """(supported, unsupported) framework names present in the tree.

    A framework is "present" only if it is IMPORTED: each `detect` entry is a
    MULTILINE regex pinned to a line start so the marker table itself, a test
    fixture quoted as a string literal, or a `# ported from django` comment
    cannot trip detection -- fail-closed keys off this, so it must be as
    precise as the extraction (review finding 4, P2-D1).
    """
    text = "\n".join(blobs[p] for p in sorted(blobs))
    supported = {f.name for f in FRAMEWORKS
                 if any(re.search(d, text) for d in f.detect)}
    unsupported = {d.name for d in UNSUPPORTED_FRAMEWORKS
                   if any(re.search(p, text) for p in d.detect)}
    return supported, unsupported


def _business_name(value: str, path: str, kind: MemberKind) -> str:
    """The business operation an entry point belongs to.

    For a route, the first path segment that is not a prefix or a parameter.
    For everything else, the HEAD TOKEN of the file stem -- which is what
    makes D9's worked example work: PaymentController, PaymentSettlementJob
    and PaymentEventConsumer share 'Payment' and nothing shorter. Stripping
    suffixes alone would leave 'PaymentSettlement' and split the candidate
    three ways, which is precisely the split-by-channel BrownKit forbids.

    A stem that names a delivery channel rather than an operation
    ('cli.py', 'routes.py') falls back to the parent directory: 'routes.py'
    names no capability, but 'payments/routes.py' does.
    """
    if kind is MemberKind.HTTP_ROUTE:
        for segment in value.split()[-1].split("/"):
            if not segment or segment[0] in "{:<*":
                continue
            if segment.lower() in _PATH_PREFIXES:
                continue
            return segment
    stem = posixpath.splitext(posixpath.basename(path))[0]
    if stem.lower() in LAYER_NAMES or stem.lower() in GENERIC_NAMES:
        parent = posixpath.basename(posixpath.dirname(path))
        if parent:
            return head_token(parent)
    return head_token(stem)


def _members(blobs: Mapping[str, str], active: set[str]
             ) -> list[tuple[CandidateMember, str]]:
    """(member, business name) for every extractable entry point."""
    out: list[tuple[CandidateMember, str]] = []
    for framework in FRAMEWORKS:
        if framework.name not in active:
            continue
        regex = re.compile(framework.pattern)
        for path in sorted(blobs):
            for match in regex.finditer(blobs[path]):
                raw = match.group(framework.value_group)
                # An empty extract (NestJS bare `@Get()`, or any decorator
                # whose path group matched nothing) carries no contract: the
                # real route is the controller's runtime base path, which we
                # cannot read. Emitting it would mint a member named after the
                # HTTP verb and group unrelated controllers by method -- a
                # fabrication at Contract-tier weight, the harm D5 exists to
                # prevent. A route we cannot extract is a miss, not a guess
                # (review finding 2).
                if not raw or not raw.strip():
                    continue
                if framework.method_group:
                    value = f"{match.group(framework.method_group).upper()} {raw}"
                elif framework.kind is MemberKind.HTTP_ROUTE:
                    # Flask's @route defaults to GET when no methods= is given;
                    # naming the verb keeps every HTTP member one shape.
                    value = f"GET {raw}"
                else:
                    value = raw
                line = blobs[path].count("\n", 0, match.start()) + 1
                out.append((
                    CandidateMember(kind=framework.kind, value=value,
                                    path=path, line=line),
                    _business_name(value, path, framework.kind)))
    return out


def _contribution(members: list[CandidateMember]) -> Confidence:
    """Corroboration WITHIN S3: several channels agreeing on one operation is
    the strongest thing one source can say. Still one source, so S5's
    cross-source rule (D8) is unaffected -- this is advisory metadata for
    E-48."""
    if len({m.kind for m in members}) > 1:
        return Confidence.HIGH
    return Confidence.MEDIUM if len(members) > 1 else Confidence.LOW


def _gap(reason: str) -> SignalOutput:
    nc = Measurement.not_collected(reason)
    return SignalOutput(row=ScanSignalResult(
        signal=ScanSignalId.S3, family=family_of(ScanSignalId.S3),
        version=VERSION, source=SignalSource.COMPUTED, collected=nc,
        categories={C_BACKEND_ENTRY: nc}))


def evaluate(blobs: Mapping[str, str]) -> SignalOutput:
    """`blobs` is path -> text for every readable, in-bound source blob."""
    supported, unsupported = detected(blobs)

    if unsupported:
        return _gap(
            f"backend_entry_points: detected framework(s) "
            f"{sorted(unsupported)} have no fingerprint in FRAMEWORKS; "
            f"extracting only {sorted(supported)} would hand a partial "
            f"Contract tier downstream, which D5 forbids (P2-D1)")
    if not supported:
        return _gap(
            f"backend_entry_points: no recognized backend framework in "
            f"{sorted(f.name for f in FRAMEWORKS)}; a repository with no "
            f"parseable entry points is not a repository with none (D5)")

    grouped: dict[str, list[CandidateMember]] = {}
    for member, name in _members(blobs, supported):
        grouped.setdefault(normalize(name) or name.lower(), []).append(member)

    candidates: list[SourceCandidate] = []
    for key, members in sorted(grouped.items()):
        by_kind = sorted({m.kind for m in members}, key=lambda k: k.value)
        rule = next((r for kind, r in _KIND_RULE if kind in by_kind),
                    "s3_entry_point")
        counts = ", ".join(
            f"{sum(1 for m in members if m.kind is kind)} "
            f"{kind.value.replace('_', ' ')}(s)" for kind in by_kind)
        candidates.append(SourceCandidate(
            signal=ScanSignalId.S3, local_id=f"S3-{key}", name=key,
            rule=rule,
            detail=f"{counts} grouped by business operation, not by "
                   f"technical type.",
            confidence_contribution=_contribution(members),
            members=members,
            evidence=[EvidenceRef(path=m.path, lines=str(m.line))
                      for m in members if m.path]))

    candidates.sort(key=lambda c: c.local_id)
    collected = Measurement.measured(float(len(candidates)))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S3, family=family_of(ScanSignalId.S3),
            version=VERSION, source=SignalSource.COMPUTED,
            collected=collected, categories={C_BACKEND_ENTRY: collected}),
        sources=candidates)
