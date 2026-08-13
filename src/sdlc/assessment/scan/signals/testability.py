"""QS3 -- testability findings (FR-912).

BrownKit's patterns, ported as a declared table with a recommended seam per
pattern -- because "inject a clock" is the actionable half, and E-53 may seed
a fix run from it.

ONE finding per (path, pattern), with the occurrence count in the detail
(P3-D10). A per-line finding would put thousands of rows in the FR-921 bundle
for one common habit, and each row's key -- an evidence hash -- would differ,
so E-44's delta would report a phantom resolved+new pair whenever a line
moved. `key` is therefore empty and testability_identity keys on
(pattern, path), which is exactly the stability E-44 D3 asks for.

Test files are not scanned: a clock read inside a test is the test's own
business, and flagging it would bury the findings that matter.

Pure: blobs in, records out.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import BaseModel

from ....measurement import Measurement
from ..models import (
    C_TESTABILITY, ScanSignalId, ScanSignalResult, SignalOutput, SignalSource,
    TestabilityFinding, family_of,
)
from ..testpaths import is_test_path

SIGNAL_ID = "QS3"
VERSION = 1

_MAX_EVIDENCE = 400


class _Pattern(BaseModel):
    # arbitrary_types_allowed: a compiled regex is not a Pydantic-native type,
    # and compiling once at import is the point of the table.
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    name: str
    severity: str                   # blocks | impedes | smell
    regex: re.Pattern[str]
    seam: str
    detail: str


PATTERNS: tuple[_Pattern, ...] = (
    _Pattern(
        name="static-clock-access", severity="impedes",
        regex=re.compile(
            r"\b(?:datetime\.datetime\.now|datetime\.now|datetime\.utcnow"
            r"|time\.time|Date\.now|new Date\(\)|DateTime\.Now"
            r"|System\.currentTimeMillis|time\.Now)\s*\("),
        seam="Inject a clock (a callable returning the current time).",
        detail="Reads the wall clock directly, so a test cannot choose the "
               "time it runs at."),
    _Pattern(
        name="unseeded-randomness", severity="impedes",
        regex=re.compile(
            r"\b(?:random\.(?:random|randint|choice|shuffle|uniform)"
            r"|Math\.random|uuid\.uuid4|crypto\.randomUUID"
            r"|rand\.Intn|new Random\(\))\s*\("),
        seam="Inject a random source, or seed it from configuration.",
        detail="Produces a different value on every run, so an assertion "
               "cannot be written against it."),
    _Pattern(
        name="direct-http-call", severity="impedes",
        regex=re.compile(
            r"\b(?:requests\.(?:get|post|put|patch|delete)"
            r"|httpx\.(?:get|post|put|patch|delete)"
            r"|urllib\.request\.urlopen|new HttpClient|axios\.(?:get|post)"
            r"|http\.Get|fetch)\s*\("),
        seam="Inject a client or gateway interface.",
        detail="Calls the network from business logic, so a test must reach "
               "the network or monkey-patch a module."),
    _Pattern(
        name="direct-file-io", severity="smell",
        regex=re.compile(
            r"\b(?:open\s*\(\s*['\"]|Path\([^)]*\)\.(?:read_text|write_text)"
            r"|fs\.(?:readFileSync|writeFileSync)|File\.ReadAllText"
            r"|ioutil\.ReadFile)\s*\(?"),
        seam="Inject a reader/writer, or pass the content in.",
        detail="Touches the filesystem from business logic, so a test needs "
               "a real file to exercise it."),
    _Pattern(
        name="sleep-in-production", severity="impedes",
        regex=re.compile(
            r"\b(?:time\.sleep|asyncio\.sleep|Thread\.sleep|setTimeout"
            r"|time\.Sleep)\s*\("),
        seam="Make the wait injectable, or drive it from an event.",
        detail="Blocks for a fixed duration, which makes every test that "
               "crosses it slow and timing-dependent."),
    _Pattern(
        name="singleton-access", severity="blocks",
        regex=re.compile(
            r"\b\w+\.getInstance\s*\(\s*\)|\bSingleton\.\w+"),
        seam="Pass the collaborator in rather than reaching for the "
             "singleton.",
        detail="Reaches a global instance, so a test cannot substitute it "
               "without mutating global state."),
    _Pattern(
        name="module-level-mutable-global", severity="smell",
        regex=re.compile(r"(?m)^[A-Za-z_]\w*\s*(?::[^=\n]+)?=\s*(?:\[\s*\]"
                         r"|\{\s*\}|set\(\)|dict\(\)|list\(\))\s*$"),
        seam="Move the state behind a factory or a fixture.",
        detail="Module-level mutable state leaks between tests in the same "
               "process."),
    _Pattern(
        name="env-read-in-business-logic", severity="smell",
        regex=re.compile(
            r"\b(?:os\.environ\[|os\.getenv\s*\(|process\.env\."
            r"|Environment\.GetEnvironmentVariable\s*\()"),
        seam="Read configuration once at the edge and pass it in.",
        detail="Reads the environment where it is used, so a test must set "
               "process-wide state to steer it."),
)


def evaluate(blobs: Mapping[str, str]) -> SignalOutput:
    """`blobs` is path -> text for every readable, in-bound source blob.

    A clean tree is a MEASURED zero: every source blob was read and no
    pattern fired. That is the same conclusion S1 reaches for a tree with no
    source files, and the opposite of S3's -- S3 cannot see routes it has no
    fingerprint for, while these patterns are the whole definition of what is
    being looked for.
    """
    findings: list[TestabilityFinding] = []
    for path in sorted(blobs):
        if is_test_path(path):
            continue
        text = blobs[path]
        for pattern in PATTERNS:
            matches = list(pattern.regex.finditer(text))
            if not matches:
                continue
            first = matches[0]
            line = text.count("\n", 0, first.start()) + 1
            quote = text.splitlines()[line - 1].strip()[:_MAX_EVIDENCE]
            occurrences = (f" {len(matches)} occurrence(s) in this file."
                           if len(matches) > 1 else "")
            findings.append(TestabilityFinding(
                severity=pattern.severity, pattern=pattern.name,
                detail=f"{pattern.detail}{occurrences}",
                recommended_seam=pattern.seam, path=path, line=line,
                evidence=quote))

    findings.sort(key=lambda f: (f.path, f.pattern))
    collected = Measurement.measured(float(len(findings)))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.QS3, family=family_of(ScanSignalId.QS3),
            version=VERSION, source=SignalSource.COMPUTED,
            collected=collected, categories={C_TESTABILITY: collected}),
        testability=findings)
