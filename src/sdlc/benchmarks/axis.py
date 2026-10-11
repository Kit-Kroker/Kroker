"""Round 015: the erosion-verbosity measurement (contract, data-model §3).

The pure core (`measure_files`, the constants, `AxisInput`) imports no
temporalio (SG-7); the activity decorator and the record builder join it
in T006 below the pure section. The tools are imported here and nowhere
else in src/ (plan import discipline).
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import math
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import radon
import yaml
from ast_grep_py import SgRoot
from radon.complexity import cc_visit
from radon.visitors import Function as RadonFunction
from temporalio import activity

from .models import (
    AxisBag,
    BenchmarkCell,
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    GraphAttribution,
    QualityScore,
    SpeedBag,
)
from .provenance import Provenance

# Contract §1.1: functions whose cyclomatic complexity is strictly above
# this carry the eroded share of the complexity mass. The source
# benchmark's threshold, adopted as written (spec default).
AXIS_EROSION_THRESHOLD = 10

# Data-model §4: the pinned verbosity rule set's version — the aggregation
# boundary (FR-010). A changed rule set ships under a new version.
RULESET_VERSION = "1"

# The pinned rule set lives beside this module (data-model §4). Module
# relative so an editable install (every deployment today) resolves it;
# a frozen wheel would need *.yml added to the package data first.
RULES_DIR = Path(__file__).parent / "rules" / "verbosity"


@dataclass
class AxisInput:
    """The activity's argument (data-model §1): the oracle input's five
    used fields plus the cell progress flag — a lost run is not measured
    without a checkout."""

    case_id: str
    repo_url: str
    run_id: str
    language: str | None  # manifest-declared; None = language not recorded
    base_branch: str = "main"
    code_finished: bool = False


def _mass(complexity: int, sloc: int) -> float:
    return complexity * math.sqrt(sloc)


class _RuleError(Exception):
    """A rule that cannot be loaded or compiled — the measurement fails
    with the rule's id in the reason, never a silent zero (data-model §4)."""

    def __init__(self, rule_id: str, detail: str):
        super().__init__(f"{rule_id}: {detail}")
        self.rule_id = rule_id


def _load_rules() -> list[tuple[str, dict]]:
    """The pinned verbosity rules, sorted by id (determinism, R-7).

    Each file is ast-grep's rule-document shape: id, language, rule.
    Anything unreadable, unparsable or off-shape fails the load with
    the rule's id. RULES_DIR is read at call time, never bound as a
    default argument (the broken-rule test swaps it).
    """
    rules: list[tuple[str, dict]] = []
    for path in sorted(RULES_DIR.glob("*.yml")):
        rule_id = path.stem
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as e:  # unreadable or invalid YAML
            raise _RuleError(rule_id, str(e)) from e
        if (
            not isinstance(doc, dict)
            or doc.get("id") != rule_id
            or doc.get("language") != "python"
            or not isinstance(doc.get("rule"), dict)
        ):
            raise _RuleError(rule_id, "not an (id, language, rule) document")
        rules.append((rule_id, doc["rule"]))
    rules.sort(key=lambda pair: pair[0])
    if not rules:
        raise _RuleError("", "rule set directory is empty")
    return rules


def _apply_rules(texts: list[tuple[Path, str]], rules: list[tuple[str, dict]]) -> int:
    """Flagged lines: the union of every rule match's whole line span over
    every file (contract §1.2). ast-grep lines are 0-based inclusive."""
    flagged: set[tuple[str, int]] = set()
    for path, text in texts:
        node = SgRoot(text, "python").root()
        for rule_id, rule in rules:
            try:
                # the YAML rule document is data; the binding's TypedDict
                # cannot prove its shape, so the config rides a cast
                matches = node.find_all(cast(Any, {"rule": rule}))
            except Exception as e:  # a rule that cannot compile
                raise _RuleError(rule_id, str(e)) from e
            for match in matches:
                span = match.range()
                for line in range(span.start.line, span.end.line + 1):
                    flagged.add((str(path), line))
    return len(flagged)


def measure_files(paths: Iterable[Path]) -> AxisBag:
    """The pure measurement over already-collected files (contract §1).

    Files are visited in sorted path order, rules in sorted id order
    (determinism, research R-7). Erosion per §1.1: mass = CC * sqrt(SLOC)
    per radon function block, SLOC = endline - lineno + 1 (radon spells
    the span end `endline`); the share of mass in blocks with CC above
    AXIS_EROSION_THRESHOLD. Verbosity per §1.2: the union of the rule
    matches' line spans over the files' non-blank lines. A rule that
    cannot be loaded or compiled fails the whole measurement with its id
    in the reason — never a silently clean tree.

    Raises on unreadable or unparseable files — the fail-safe wrapper
    (the activity, T006) turns any raise into `measurement failed`.
    """
    files = sorted(Path(p) for p in paths)
    texts = [(path, path.read_text(encoding="utf-8")) for path in files]
    loc = 0
    functions_total = 0
    functions_over = 0
    mass_total = 0.0
    mass_over = 0.0
    for _path, text in texts:
        loc += sum(1 for line in text.splitlines() if line.strip())
        for block in cc_visit(text):
            if not isinstance(block, RadonFunction):
                continue  # class wrappers are containers, not functions
            functions_total += 1
            sloc = block.endline - block.lineno + 1
            mass = _mass(block.complexity, sloc)
            mass_total += mass
            if block.complexity > AXIS_EROSION_THRESHOLD:
                functions_over += 1
                mass_over += mass
    if functions_total == 0:
        # No denominator: an honest absence, never 0.0 (contract §1.1).
        return AxisBag(reason="no functions", files=len(files), loc=loc)
    try:
        flagged = _apply_rules(texts, _load_rules())
    except _RuleError as e:
        detail = f"rule {e.rule_id}" if e.rule_id else "empty rule set"
        return AxisBag(reason=f"measurement failed: {detail}", files=len(files), loc=loc)
    return AxisBag(
        erosion=(mass_over / mass_total),
        verbosity=(flagged / loc if loc else 0.0),
        functions_total=functions_total,
        functions_over=functions_over,
        mass_total=mass_total,
        mass_over=mass_over,
        flagged_lines=flagged,
        loc=loc,
        files=len(files),
        head=None,  # the activity fills the branch head
        ruleset_version=RULESET_VERSION,
        tools={
            "radon": radon.__version__,
            "ast-grep": importlib_metadata.version("ast-grep-py"),
        },
    )


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


@activity.defn
async def measure_code_axis(inp: AxisInput) -> AxisBag:
    """The fail-safe writer (contract §2): measures the produced diff at the
    integration branch head. NEVER raises — every failure path returns a bag
    with its reason, so the run's grade and records are unaffected (FR-006).
    Preconditions short-circuit in order, each before any checkout (§2.3);
    its own detached worktree mirrors the oracle's pattern and is removed
    in a finally (§2.6). Needs no network (FR-007). Async like every other
    benchmark activity — the worker runs no sync-activity executor."""

    def _reason(reason: str) -> AxisBag:
        return AxisBag(reason=reason)

    if not inp.code_finished:
        return _reason("code stage did not finish")
    if inp.language != "python":
        # covers language not recorded (None) — same honest absence
        return _reason("language not python")
    parent = tempfile.mkdtemp(prefix="axis-")
    wt = os.path.join(parent, "wt")
    branch = f"sdlc/{inp.run_id}/integration"
    try:
        # Detached checkout of the produced head: --detach sidesteps git's
        # "already checked out" if the run's integration worktree exists.
        add = _git(["worktree", "add", "--detach", wt, branch], inp.repo_url)
        if add.returncode != 0:
            return _reason("integration branch absent")
        head = _git(["rev-parse", "HEAD"], wt)
        diff = _git(["diff", "--name-only", f"{inp.base_branch}...HEAD"], wt)
        changed = [ln.strip() for ln in diff.stdout.splitlines() if ln.strip()]
        measured = sorted(p for p in changed if p.endswith(".py"))
        if not measured:
            return _reason("no python files in diff")
        bag = measure_files([Path(wt) / p for p in measured])
        return bag.model_copy(update={"head": head.stdout.strip()})
    except Exception as e:  # never raises past this boundary
        return _reason(f"measurement failed: {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def axis_record(
    cell: BenchmarkCell,
    bag: AxisBag,
    bench_run_id: str,
    run_id: str,
    started: datetime,
    ended: datetime,
    *,
    provenance: Provenance | None,
    graph_sha: str | None = None,
) -> BenchmarkRecord:
    """The pure record builder the workflow calls after the cell record
    (data-model §2, the cell_record pattern): identity and provenance
    fields identical to the cell record's, quality score=None with judge
    "axis" (figures never enter a quality figure, FR-011), outcome
    not_evaluated, speed spanning the measurement, the bag on .axis."""
    graph = GraphAttribution(graph_sha=graph_sha) if graph_sha else None
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id=bench_run_id,
        case_id=cell.case_id,
        scope=BenchmarkScope.AXIS,
        stage="axis",
        role="axis",
        harness=cell.harness,
        lead_harness=cell.lead_harness,
        model="deterministic",
        prompt_sha="none:deterministic",
        quality=QualityScore(score=None, judge="axis"),
        speed=SpeedBag(
            wall_clock_s=(ended - started).total_seconds(), started_at=started, ended_at=ended
        ),
        outcome=BenchmarkOutcome.NOT_EVALUATED,
        kroker_commit=(provenance.kroker_commit if provenance is not None else None),
        tree_dirty=(provenance.tree_dirty if provenance is not None else None),
        arm=cell.arm_name,
        cell_id=cell.cell_id,
        axis=bag,
        graph=graph,
    )
