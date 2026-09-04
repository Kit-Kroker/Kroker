"""QS4 -- environment and CI signals, computed half (FR-912).

ci_present is triage's `baseline`, inherited and folded in by the workflow
(D2/D7). This module adds the two facts a boolean cannot carry: what the
pipeline's stages ARE, and which environments the repository declares on each
side.

Environment drift is CI-vs-CONFIG, not CI-vs-declared (P3-D7). BrownKit
compares against `qa_scope.environments`, which comes from /enrich -- E-56,
unbuilt. Rather than report the category permanently not_collected, drift is
computed between the two declarations the repository itself carries; when
there is no CI side at all the category says so and names E-56.

YAML is parsed with safe_load behind an expansion guard (P3-D8): safe_load
does not execute code, but anchors still expand, and a CI file comes from an
untrusted repository (NFR-9). A file that trips the guard, or that does not
parse, degrades ALONE -- the other workflows still report.

Pure: paths and blobs in, records out. Nothing here runs a pipeline.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence

import yaml

from sdlc.assessment.scan.models import (
    C_CI_PRESENT,
    C_CI_STAGES,
    C_ENV_DRIFT,
    CiStageRecord,
    EnvironmentRecord,
    EvidenceRef,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    TestLevel,
    family_of,
    inherited_pending,
)

from ....measurement import Measurement

SIGNAL_ID = "QS4"
VERSION = 1

# P3-D8's guard. A CI file larger than this, or with more alias references
# than this, is refused rather than expanded.
MAX_CI_BYTES = 256_000
MAX_ALIASES = 50
_ALIAS = re.compile(r"(?m)(?<![\w*])\*[A-Za-z_][\w-]*")

_CI_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\.github/workflows/[^/]+\.ya?ml$"),
    re.compile(r"(^|/)\.gitlab-ci\.ya?ml$"),
    re.compile(r"(^|/)azure-pipelines\.ya?ml$"),
    re.compile(r"(^|/)\.circleci/config\.ya?ml$"),
    re.compile(r"(^|/)\.travis\.ya?ml$"),
    re.compile(r"(^|/)Jenkinsfile$"),
)

# The environment names a drift comparison is meaningful over. A free-form
# name would make every directory an "environment".
ENVIRONMENT_NAMES: frozenset[str] = frozenset(
    {
        "dev",
        "development",
        "test",
        "testing",
        "qa",
        "uat",
        "stage",
        "staging",
        "preprod",
        "pre-production",
        "prod",
        "production",
        "sandbox",
        "demo",
    }
)

_ENV_CONFIG_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|/)\.env\.([A-Za-z0-9_-]+)$"),
    re.compile(r"(^|/)appsettings\.([A-Za-z]+)\.json$"),
    re.compile(r"(^|/)application-([A-Za-z0-9]+)\.(?:ya?ml|properties)$"),
    re.compile(r"(^|/)config/([A-Za-z0-9]+)\.(?:ya?ml|json|toml)$"),
    re.compile(
        r"(^|/)(?:k8s|kubernetes|deploy|overlays|helm)/"
        r"([A-Za-z0-9]+)/"
    ),
)

_TEST_CMD = re.compile(
    r"(?i)\b(pytest|tox\b|npm (?:run )?test|yarn test|pnpm test|go test"
    r"|mvn\b[^\n]*\btest|gradle\b[^\n]*\btest|jest|vitest|cargo test"
    r"|dotnet test|rspec|phpunit|playwright test|cypress run)"
)

# (level, pattern). Ordered: the strongest claim first, same rule as QS1's.
_LEVEL_HINTS: tuple[tuple[TestLevel, re.Pattern[str]], ...] = (
    (TestLevel.E2E, re.compile(r"(?i)\b(e2e|playwright|cypress|selenium)\b")),
    (TestLevel.PERFORMANCE, re.compile(r"(?i)\b(k6|locust|gatling|jmeter)\b")),
    (TestLevel.CONTRACT, re.compile(r"(?i)\b(pact|contract-test)\b")),
    (TestLevel.INTEGRATION, re.compile(r"(?i)\bintegration\b")),
)

_JENKINS_STAGE = re.compile(r"""stage\s*\(\s*['"]([^'"]+)['"]\s*\)""")


def is_ci_path(path: str) -> bool:
    return any(pattern.search(path) for pattern in _CI_PATTERNS)


def is_env_config_path(path: str) -> str:
    """The environment a config path names, or "" when it names none."""
    for pattern in _ENV_CONFIG_PATTERNS:
        match = pattern.search(path)
        if match:
            name = match.groups()[-1].lower()
            if name in ENVIRONMENT_NAMES:
                return name
    return ""


def _safe_yaml(text: str) -> dict | None:
    """A parsed mapping, or None when the document is too large, too
    alias-heavy, unparseable, or simply not a mapping (P3-D8)."""
    if len(text.encode("utf-8", "replace")) > MAX_CI_BYTES:
        return None
    if len(_ALIAS.findall(text)) > MAX_ALIASES:
        return None
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return doc if isinstance(doc, dict) else None


def _unreadable_blocking() -> Measurement:
    return Measurement.not_collected(
        "required checks are a branch-protection setting, not a tracked "
        "file, so they are not readable at a pinned commit (E-59)"
    )


def _levels(text: str, runs_tests: bool) -> list[TestLevel]:
    if not runs_tests:
        return []
    for level, pattern in _LEVEL_HINTS:
        if pattern.search(text):
            return [level]
    return [TestLevel.UNIT]


def _step_text(job: dict) -> str:
    steps = job.get("steps")
    parts: list[str] = []
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                parts.extend(str(step.get(k, "")) for k in ("run", "uses", "name"))
            elif isinstance(step, str):
                parts.append(step)
    script = job.get("script")
    if isinstance(script, list):
        parts.extend(str(s) for s in script)
    elif isinstance(script, str):
        parts.append(script)
    return "\n".join(p for p in parts if p)


def _environment(job: dict) -> str:
    value = job.get("environment")
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, dict):
        return str(value.get("name", "")).strip().lower()
    return ""


def _jobs(doc: dict) -> list[tuple[str, dict]]:
    """(name, job) pairs. GitHub nests them under `jobs`; GitLab puts them at
    the top level, where a job is any mapping carrying a `script`."""
    jobs = doc.get("jobs")
    if isinstance(jobs, dict):
        return [(str(name), job) for name, job in jobs.items() if isinstance(job, dict)]
    return [
        (str(name), job) for name, job in doc.items() if isinstance(job, dict) and "script" in job
    ]


def _stages_from_doc(path: str, doc: dict) -> list[CiStageRecord]:
    """Stages from an already-parsed workflow mapping. `_safe_yaml` is the
    caller's responsibility so evaluate can tell a refusal from an empty
    workflow apart (P3-D8, spec section 6)."""
    out: list[CiStageRecord] = []
    for order, (name, job) in enumerate(_jobs(doc)):
        body = _step_text(job)
        runs_tests = bool(_TEST_CMD.search(body))
        out.append(
            CiStageRecord(
                workflow=path,
                stage=name,
                order=order,
                runs_tests=runs_tests,
                test_levels=_levels(f"{name}\n{body}", runs_tests),
                deploys_to=_environment(job),
                blocking=_unreadable_blocking(),
            )
        )
    return out


def _stages_from_jenkinsfile(path: str, text: str) -> list[CiStageRecord]:
    matches = list(_JENKINS_STAGE.finditer(text))
    out: list[CiStageRecord] = []
    for order, match in enumerate(matches):
        end = matches[order + 1].start() if order + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        runs_tests = bool(_TEST_CMD.search(body))
        out.append(
            CiStageRecord(
                workflow=path,
                stage=match.group(1),
                order=order,
                runs_tests=runs_tests,
                test_levels=_levels(f"{match.group(1)}\n{body}", runs_tests),
                blocking=_unreadable_blocking(),
            )
        )
    return out


def evaluate(
    paths: Sequence[str], blobs: Mapping[str, str], skipped: Sequence[str] = ()
) -> SignalOutput:
    """`paths` is every tracked path (the config side of the drift
    comparison); `blobs` is path -> text for the CI files that were read.
    `skipped` names CI files over MAX_BLOB_BYTES; an unreadable CI file makes
    the stage list partial exactly as a refused one does (spec section 6)."""
    ci_paths = sorted(p for p in paths if is_ci_path(p))
    stages: list[CiStageRecord] = []
    refused: list[str] = list(skipped)  # oversized == unreadable
    for path in ci_paths:
        text = blobs.get(path)
        if text is None:
            continue
        if posixpath.basename(path) == "Jenkinsfile":
            stages.extend(_stages_from_jenkinsfile(path, text))
            continue
        doc = _safe_yaml(text)
        if doc is None:
            refused.append(path)
        else:
            stages.extend(_stages_from_doc(path, doc))
    stages.sort(key=lambda s: (s.workflow, s.order, s.stage))

    # A CI file we read but could not parse makes the stage list PARTIAL: an
    # unparseable workflow may carry stages we cannot see, so measured(N) would
    # pass a partial count as complete -- the FR-915 conflation. The pipeline
    # side of env_drift is incomplete for the same reason. (spec section 6,
    # P3-D8.)
    if refused:
        nc = Measurement.not_collected(
            f"ci_stages: {len(refused)} CI file(s) not parsed -- over "
            f"MAX_BLOB_BYTES or unparseable (first: {refused[0]}); a partial "
            f"stage list must not pass as a complete one (spec section 6, "
            f"P3-D8)"
        )
        return SignalOutput(
            row=ScanSignalResult(
                signal=ScanSignalId.QS4,
                family=family_of(ScanSignalId.QS4),
                version=VERSION,
                source=SignalSource.COMPUTED,
                collected=nc,
                categories={
                    C_CI_STAGES: nc,
                    C_ENV_DRIFT: nc,
                    C_CI_PRESENT: inherited_pending(C_CI_PRESENT),
                },
            ),
            ci=[],
            environments=[],
        )

    in_ci = {s.deploys_to for s in stages if s.deploys_to}
    in_config: dict[str, list[str]] = {}
    for path in sorted(paths):
        name = is_env_config_path(path)
        if name:
            in_config.setdefault(name, []).append(path)

    environments = [
        EnvironmentRecord(
            name=name,
            in_ci=name in in_ci,
            in_config=name in in_config,
            evidence=[EvidenceRef(path=p) for p in in_config.get(name, [])],
        )
        for name in sorted(in_ci | set(in_config))
    ]

    if ci_paths:
        drift = Measurement.measured(float(sum(1 for e in environments if e.drifted)))
    else:
        drift = Measurement.not_collected(
            "env_drift: no CI configuration in the tree, so there is no "
            "pipeline side to compare the committed environment configs "
            "against (P3-D11). The declared-scope comparison BrownKit makes "
            "needs /enrich's qa_scope, which is E-56"
        )

    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.QS4,
            family=family_of(ScanSignalId.QS4),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=Measurement.measured(float(len(stages))),
            categories={
                C_CI_STAGES: Measurement.measured(float(len(stages))),
                C_ENV_DRIFT: drift,
                C_CI_PRESENT: inherited_pending(C_CI_PRESENT),
            },
        ),
        ci=stages,
        environments=environments,
    )
