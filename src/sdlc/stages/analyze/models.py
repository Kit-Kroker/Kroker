"""Artifact models for the analyze stage (spec A §2)."""

from __future__ import annotations

import posixpath
import re
from typing import Literal

from pydantic import BaseModel, Field

from ...benchmarks.models import AuditEvidence, CriterionAudit
from ..review.models import ReviewFinding


class Evidence(BaseModel):
    """One piece of evidence proposed by the Analyst (017 data-model §1.1)."""

    kind: Literal["file", "task_unchanged", "command"]
    ref: str | None = None
    expect: Literal["present", "absent"] | None = None


class CriterionTrace(BaseModel):
    """One acceptance criterion and the test(s)/evidence the Analyst says verify it."""

    task_id: str
    criterion: str
    tests: list[str] = Field(default_factory=list)
    key: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    """Clean-context Analyst output (stage 9 / FR-106). Emitted from
    orchestrator-assembled inputs only — the authoritative acceptance-criteria
    list + materialized integration diff + aggregate test output. The Analyst
    holds no tools, no repo, no worker session.

    The Analyst PROPOSES the criterion->test mapping; the workflow ENFORCES
    completeness against the plan's criteria. This model never carries a
    pass/fail verdict. `findings` ride along for memory/observability and are
    NOT wired as a blocking gate check.
    """

    traceability: list[CriterionTrace] = Field(default_factory=list)
    findings: list[ReviewFinding] = Field(default_factory=list)
    summary: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


def untraced_criteria(authoritative: list[tuple[str, str]], report: AnalysisReport) -> list[str]:
    """FR-106 enforcement (workflow-side, NOT the LLM's verdict).

    A criterion is traced iff the Analyst's report contains a CriterionTrace
    for that exact (task_id, criterion) with a non-empty `tests` list. Any
    authoritative criterion the report omits OR maps to zero tests is untraced.
    Enforced against the plan's authoritative set so an Analyst cannot hide a
    gap by forgetting to list a criterion. Returns "task_id: criterion" labels
    in authoritative order.
    """
    traced = {(t.task_id, t.criterion) for t in report.traceability if t.tests}
    return [
        f"{task_id}: {criterion}"
        for (task_id, criterion) in authoritative
        if (task_id, criterion) not in traced
    ]


class KeyedCriterion(BaseModel):
    """One authoritative criterion with its workflow-assigned key."""

    key: str
    task_id: str
    criterion: str


def criterion_keys(authoritative: list[tuple[str, str]]) -> list[KeyedCriterion]:
    """Assign keys "{task_id}#{n}" where n is 1-based within each task, in plan order."""
    counts: dict[str, int] = {}
    result: list[KeyedCriterion] = []
    for task_id, criterion in authoritative:
        n = counts.get(task_id, 0) + 1
        counts[task_id] = n
        result.append(KeyedCriterion(key=f"{task_id}#{n}", task_id=task_id, criterion=criterion))
    return result


class TraceInventory(BaseModel):
    """Activity-assembled inventory of tests, tree, and diffs (017 data-model §1.4)."""

    changed_files: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    tree: list[str] = Field(default_factory=list)
    task_changed: dict[str, int | None] = Field(default_factory=dict)
    task_files: dict[str, list[str]] = Field(default_factory=dict)
    truncated: dict[str, bool] = Field(default_factory=dict)


class TraceEnforcement(BaseModel):
    """Result of pure trace enforcement across all criteria (017 data-model §1.5)."""

    buckets: dict[str, int] = Field(default_factory=dict)
    untraced: list[str] = Field(default_factory=list)
    criteria_trace: list[CriterionAudit] = Field(default_factory=list)
    truncated: bool = False


class AnalyzeOutcome(BaseModel):
    """Workflow-side outcome returned by the analyze stage (017 data-model §1.3)."""

    report: AnalysisReport
    untraced: list[str] = Field(default_factory=list)


def _norm_path(p: str) -> str:
    return p.replace("\\", "/").strip().lstrip("./")


def _normalize_test_name(test_name: str) -> str:
    return re.sub(r"\[.*\]$", "", test_name.strip())


def _is_test_valid(test_cite: str, inventory_tests: list[str]) -> bool:
    cite_norm = _normalize_test_name(test_cite)
    if not cite_norm:
        return False
    inv_unparam = [_normalize_test_name(t) for t in inventory_tests]
    if cite_norm in inv_unparam:
        return True
    suffix = f"::{cite_norm}"
    matches = [t for t in inv_unparam if t.endswith(suffix)]
    return len(matches) == 1


def enforce_traces(
    criteria: list[KeyedCriterion],
    report: AnalysisReport,
    inventory: TraceInventory,
) -> TraceEnforcement:
    """Pure trace enforcement per research D-4 and contract C-2."""
    by_key: dict[str, CriterionTrace] = {}
    by_text: dict[tuple[str, str], CriterionTrace] = {}
    for item in report.traceability:
        if item.key and item.key not in by_key:
            by_key[item.key] = item
        pair = (item.task_id, item.criterion)
        if pair not in by_text:
            by_text[pair] = item

    tree_set = {_norm_path(p) for p in inventory.tree}
    changed_set = {_norm_path(p) for p in inventory.changed_files}

    buckets = {"test": 0, "file": 0, "command": 0, "empty": 0}
    untraced: list[str] = []
    audits: list[CriterionAudit] = []
    any_ref_cut = False

    for kc in criteria:
        matched_trace: CriterionTrace | None = by_key.get(kc.key) or by_text.get(
            (kc.task_id, kc.criterion)
        )
        audit_ev: list[AuditEvidence] = []

        if matched_trace is not None:
            # 1. Tests in trace.tests
            for t in matched_trace.tests:
                is_valid = _is_test_valid(t, inventory.tests)
                test_ref_cut = t
                if len(t) > 200:
                    any_ref_cut = True
                    test_ref_cut = t[:200]
                audit_ev.append(
                    AuditEvidence(kind="test", ref=test_ref_cut, expect=None, valid=is_valid)
                )

            # 2. Evidence items in trace.evidence
            for ev in matched_trace.evidence:
                ref_raw = ev.ref
                ev_ref_cut: str | None = ref_raw
                if ref_raw is not None and len(ref_raw) > 200:
                    any_ref_cut = True
                    ev_ref_cut = ref_raw[:200]

                valid = False
                if ev.kind == "file":
                    ref_norm = _norm_path(ref_raw) if ref_raw else ""
                    expect = ev.expect or "present"
                    if expect == "present":
                        valid = bool(ref_norm and ref_norm in tree_set)
                    elif expect == "absent":
                        basename = posixpath.basename(ref_norm)
                        contained = bool(
                            ref_norm and (ref_norm in kc.criterion or basename in kc.criterion)
                        )
                        valid = bool(ref_norm and ref_norm not in changed_set and contained)
                elif ev.kind == "task_unchanged":
                    task_diff_count = inventory.task_changed.get(kc.task_id)
                    valid = task_diff_count == 0
                elif ev.kind == "command":
                    valid = False

                audit_ev.append(
                    AuditEvidence(kind=ev.kind, ref=ev_ref_cut, expect=ev.expect, valid=valid)
                )

            # Determine bucket by precedence: test > file > command > empty
            has_valid_test = any(ae.kind == "test" and ae.valid for ae in audit_ev)
            has_valid_file = any(
                ae.kind in ("file", "task_unchanged") and ae.valid for ae in audit_ev
            )
            has_command = any(ae.kind == "command" for ae in audit_ev)

            if has_valid_test:
                bucket: Literal["test", "file", "command", "empty"] = "test"
            elif has_valid_file:
                bucket = "file"
            elif has_command:
                bucket = "command"
            else:
                bucket = "empty"
        else:
            bucket = "empty"

        buckets[bucket] += 1
        if bucket in ("command", "empty"):
            untraced.append(f"{kc.task_id}: {kc.criterion}")

        audits.append(CriterionAudit(key=kc.key, bucket=bucket, evidence=audit_ev))

    truncated = (len(audits) > 300) or any_ref_cut
    criteria_trace = audits[:300]

    return TraceEnforcement(
        buckets=buckets,
        untraced=untraced,
        criteria_trace=criteria_trace,
        truncated=truncated,
    )
