"""Round 015: the erosion-verbosity measurement (contract, data-model §3).

The pure core (`measure_files`, the constants, `AxisInput`) imports no
temporalio (SG-7); the activity decorator and the record builder join it
in T006 below the pure section. The tools are imported here and nowhere
else in src/ (plan import discipline).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import radon
from radon.complexity import cc_visit
from radon.visitors import Function as RadonFunction

from .models import AxisBag

# Contract §1.1: functions whose cyclomatic complexity is strictly above
# this carry the eroded share of the complexity mass. The source
# benchmark's threshold, adopted as written (spec default).
AXIS_EROSION_THRESHOLD = 10

# Data-model §4: the pinned verbosity rule set's version — the aggregation
# boundary (FR-010). A changed rule set ships under a new version.
RULESET_VERSION = "1"


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


def measure_files(paths: Iterable[Path]) -> AxisBag:
    """The pure measurement over already-collected files (contract §1).

    Files are visited in sorted path order (determinism, research R-7).
    Erosion per §1.1: mass = CC * sqrt(SLOC) per radon function block,
    SLOC = endline - lineno + 1 (radon spells the span end `endline`);
    the share of mass in blocks with CC above AXIS_EROSION_THRESHOLD.
    The verbosity rule application joins in T005; until then flagged
    lines read zero and verbosity is flagged/loc.

    Raises on unreadable or unparseable files — the fail-safe wrapper
    (the activity, T006) turns any raise into `measurement failed`.
    """
    files = sorted(Path(p) for p in paths)
    loc = 0
    functions_total = 0
    functions_over = 0
    mass_total = 0.0
    mass_over = 0.0
    for path in files:
        text = path.read_text(encoding="utf-8")
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
    return AxisBag(
        erosion=(mass_over / mass_total),
        verbosity=0.0,  # the rule application lands in T005
        functions_total=functions_total,
        functions_over=functions_over,
        mass_total=mass_total,
        mass_over=mass_over,
        flagged_lines=0,
        loc=loc,
        files=len(files),
        head=None,  # the activity fills the branch head
        ruleset_version=RULESET_VERSION,
        tools={"radon": radon.__version__},
    )
