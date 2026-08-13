"""S2 -- database schema clusters (FR-912).

Tables, foreign-key references, and the clusters they form. BrownKit clusters
"by FK connectivity + naming"; here NAMING clusters and FK CORROBORATES
(P3-D13), because union-find over foreign keys collapses a normalized schema
into one component and would emit a single "capability" covering the whole
database. The naming half is naming.normalize, so S5 can merge an S2 cluster
with the S1 package and the S3 controller that share its name -- which is what
finally lets a candidate reach HIGH (three distinct sources, D8).

D5 applies exactly as it does to S3: a repository with no parseable schema is
NOT a repository with no schema. An ORM we cannot fingerprint looks precisely
like an application with no database, and only one of those is safe to assert.

Also the home of `declarations()`, which SS4 reads: one extractor, two
consumers (FR-902's one-implementation rule, applied inside the phase). Safe
for the memo because SS4 declares `consumes=(S2, S3)` and rules_sha walks
`consumes` transitively, so this module's bytes are already hashed into SS4's
key.

Pure: blobs in, records out. The activity reads the tree.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from ....measurement import Measurement
from ..models import (
    C_SCHEMA, CandidateMember, Confidence, EvidenceRef, MemberKind,
    ScanSignalId, ScanSignalResult, SignalOutput, SignalSource, SourceCandidate,
    family_of,
)
from ..naming import head_token, normalize
from ..testpaths import is_test_path

SIGNAL_ID = "S2"
VERSION = 1

M_FK_EDGES = "fk_edges"
M_TABLES = "tables"

# Extensions the S1/S3 source list does not carry but a schema lives in.
EXTRA_EXTENSIONS: tuple[str, ...] = (".sql", ".prisma")

# How far past a declaration its field block is read. Bounded so a
# mis-detected declaration costs a few lines, not a whole file.
_FIELD_WINDOW = 120
_BLOCK_END = re.compile(r"^[ \t]*[)}][ \t]*;?[ \t]*$")

# (rule, origin, pattern). Group 1 is the declared name. `origin` is what
# SS4's SensitivityRecord records, which is why it is declared beside the
# pattern rather than guessed from the path.
_DECL_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("s2_sql_create_table", "table", re.compile(
        r"(?im)^[ \t]*create\s+table\s+(?:if\s+not\s+exists\s+)?"
        r"[`\"\[]?(?:[a-z_][a-z0-9_]*\.)?([a-z_][a-z0-9_]*)[`\"\]]?")),
    ("s2_prisma_model", "table", re.compile(
        r"(?m)^[ \t]*model[ \t]+([A-Za-z_]\w*)[ \t]*\{")),
    ("s2_sqlalchemy_tablename", "model", re.compile(
        r"""(?m)^[ \t]*__tablename__\s*=\s*['"]([A-Za-z_]\w*)['"]""")),
    ("s2_django_model", "model", re.compile(
        r"(?m)^[ \t]*class[ \t]+([A-Za-z_]\w*)\s*\([^)]*\bModel\b")),
    ("s2_typeorm_entity", "model", re.compile(
        r"(?m)^[ \t]*@Entity\([^)]*\)[\s\S]{0,200}?class[ \t]+([A-Za-z_]\w*)")),
)

# Group 1 is the REFERENCED table/model.
_FK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)references\s+[`\"\[]?(?:[a-z_][a-z0-9_]*\.)?"
               r"([a-z_][a-z0-9_]*)"),
    re.compile(r"ForeignKey\(\s*['\"]([A-Za-z_]\w*)\."),
    re.compile(r"(?:ForeignKey|OneToOneField|ManyToManyField)\("
               r"\s*['\"]?([A-Za-z_]\w*)"),
    re.compile(r"(?m)^[ \t]*\w+[ \t]+([A-Za-z_]\w*)(?:\[\])?\??[ \t]+"
               r"@relation\b"),
)

_FIELD_PATTERNS: tuple[re.Pattern[str], ...] = (
    # SQL column inside a CREATE TABLE body.
    re.compile(r"""^[ \t]*[`"\[]?([a-z_][a-z0-9_]*)[`"\]]?[ \t]+"""
               r"(?:varchar|char|text|int|integer|bigint|smallint|serial|"
               r"numeric|decimal|float|double|real|bool|boolean|date|"
               r"timestamptz|timestamp|time|uuid|jsonb|json|bytea|blob)\b",
               re.IGNORECASE),
    # ORM attribute.
    re.compile(r"^[ \t]*([A-Za-z_]\w*)\s*=\s*(?:models\.|db\.|sa\.)?"
               r"(?:Column|mapped_column|CharField|TextField|IntegerField|"
               r"BooleanField|DateTimeField|DateField|DecimalField|"
               r"FloatField|EmailField|UUIDField|JSONField)\b"),
    # Prisma / TypeORM typed field.
    re.compile(r"^[ \t]*([A-Za-z_]\w*)\??[ \t:]+(?:String|Int|BigInt|Float|"
               r"Decimal|Boolean|DateTime|Json|Bytes|string|number|boolean|"
               r"Date)\b"),
)


class TableDecl(BaseModel):
    """One declared table or entity, and where it was declared."""
    model_config = {"frozen": True}
    name: str
    rule: str
    origin: str                     # "table" | "model" -- SS4 records it
    path: str
    line: int
    fields: tuple[str, ...] = ()


def _block(lines: list[str], start: int, starts: set[int]) -> list[str]:
    """A declaration's body: the lines after `start` up to the first block
    terminator, the next declaration, or _FIELD_WINDOW -- whichever comes
    first."""
    out: list[str] = []
    for index in range(start + 1, min(len(lines), start + 1 + _FIELD_WINDOW)):
        if index in starts or _BLOCK_END.match(lines[index]):
            break
        out.append(lines[index])
    return out


def _fields(block: list[str]) -> tuple[str, ...]:
    """Field names in declaration order, de-duplicated. Order is preserved
    rather than sorted because a column order is a fact about the schema and
    SS4 quotes these back."""
    out: list[str] = []
    for line in block:
        for pattern in _FIELD_PATTERNS:
            match = pattern.match(line)
            if match and match.group(1) not in out:
                out.append(match.group(1))
                break
    return tuple(out)


def declarations(blobs: Mapping[str, str]) -> list[TableDecl]:
    """Every table/entity declared in `blobs`, sorted by (path, line).

    Test paths are skipped: a CREATE TABLE inside a fixture describes the
    test, not the product (P3-D9).
    """
    out: list[TableDecl] = []
    for path in sorted(blobs):
        if is_test_path(path):
            continue
        text = blobs[path]
        lines = text.splitlines()
        found: list[tuple[int, str, str, str]] = []      # (line, name, rule, origin)
        for rule, origin, pattern in _DECL_PATTERNS:
            for match in pattern.finditer(text):
                lineno = text.count("\n", 0, match.start())
                found.append((lineno, match.group(1), rule, origin))
        starts = {lineno for lineno, _, _, _ in found}
        for lineno, name, rule, origin in sorted(found):
            out.append(TableDecl(
                name=name, rule=rule, origin=origin, path=path,
                line=lineno + 1,
                fields=_fields(_block(lines, lineno, starts))))
    return sorted(out, key=lambda d: (d.path, d.line, d.name))


def _cluster_key(name: str) -> str:
    """The key two tables must share to cluster by NAME. head_token before
    normalize, so 'order_items' and 'orders' both reach 'order' -- the same
    reduction S3 applies to PaymentSettlementJob (D9)."""
    return normalize(head_token(name)) or name.strip().lower()


def _fk_targets(text: str) -> set[str]:
    return {m.group(1) for pattern in _FK_PATTERNS
            for m in pattern.finditer(text)}


def _gap(reason: str) -> SignalOutput:
    nc = Measurement.not_collected(reason)
    return SignalOutput(row=ScanSignalResult(
        signal=ScanSignalId.S2, family=family_of(ScanSignalId.S2),
        version=VERSION, source=SignalSource.COMPUTED, collected=nc,
        categories={C_SCHEMA: nc}))


def evaluate(blobs: Mapping[str, str],
             skipped: Sequence[str] = ()) -> SignalOutput:
    """`blobs` is path -> text for every readable, in-bound blob whose
    extension is a source or schema extension. `skipped` names the blobs over
    MAX_BLOB_BYTES; a partial table set must not pass as a complete one
    (spec section 6)."""
    if skipped:
        return _gap(
            f"schema_clusters: {len(skipped)} blob(s) over MAX_BLOB_BYTES "
            f"not read (first: {skipped[0]}); a partial scan must not pass "
            f"as a complete one (spec section 6)")
    decls = declarations(blobs)
    if not decls:
        return _gap(
            f"schema_clusters: no table or entity declaration matched any of "
            f"{sorted(rule for rule, _, _ in _DECL_PATTERNS)}; a repository "
            f"with no parseable schema is not a repository with no schema "
            f"(D5)")

    clusters: dict[str, list[TableDecl]] = {}
    for decl in decls:
        clusters.setdefault(_cluster_key(decl.name), []).append(decl)

    candidates: list[SourceCandidate] = []
    for root in sorted(clusters):
        group = sorted(clusters[root], key=lambda d: (d.name, d.path))
        names = sorted({d.name for d in group})
        # P3-D13: FK references CORROBORATE a cluster, they do not merge one.
        # Counted over the files this cluster's tables are declared in, which
        # is as precise as a signal that does not parse blocks can be.
        cluster_edges = sum(len(_fk_targets(blobs[path]))
                            for path in sorted({d.path for d in group}))
        if cluster_edges and len(names) > 1:
            contribution = Confidence.HIGH
            detail = (f"{len(names)} table(s) sharing the stem {root!r}, "
                      f"declared alongside {cluster_edges} foreign-key "
                      f"reference(s).")
        elif len(names) > 1:
            contribution = Confidence.MEDIUM
            detail = (f"{len(names)} table(s) sharing the stem {root!r}; no "
                      f"foreign key is declared beside them.")
        else:
            contribution = Confidence.LOW
            detail = (f"one table, {names[0]!r}, and no other table shares "
                      f"its name stem.")
        candidates.append(SourceCandidate(
            signal=ScanSignalId.S2, local_id=f"S2-{root}",
            name=min(names, key=lambda n: (len(n), n)),
            rule="s2_schema_cluster", detail=detail,
            confidence_contribution=contribution,
            members=[CandidateMember(kind=MemberKind.DB_TABLE, value=n,
                                     path=next(d.path for d in group
                                               if d.name == n))
                     for n in names],
            evidence=[EvidenceRef(path=d.path, lines=str(d.line))
                      for d in group],
            metrics={
                M_TABLES: Measurement.measured(float(len(names))),
                M_FK_EDGES: Measurement.measured(float(cluster_edges)),
            }))

    candidates.sort(key=lambda c: c.local_id)
    collected = Measurement.measured(float(len(candidates)))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S2, family=family_of(ScanSignalId.S2),
            version=VERSION, source=SignalSource.COMPUTED,
            collected=collected, categories={C_SCHEMA: collected}),
        sources=candidates)
