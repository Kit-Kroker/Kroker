"""Corpus discovery and smoke case resolution (round 015, Phase 2, US1/US2)."""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import CaseRole, CaseSpec


def load_corpus(cases_root: Path | str) -> list[CaseSpec]:
    """Load every CaseSpec found directly under `cases_root/*/case.yaml`."""
    root = Path(cases_root)
    specs: list[CaseSpec] = []
    for case_yaml in sorted(root.glob("*/case.yaml")):
        raw = yaml.safe_load(case_yaml.read_text(encoding="utf-8"))
        specs.append(CaseSpec(**raw))
    return specs


def smoke_case(cases_root: Path | str) -> CaseSpec:
    """Return the unique case in `cases_root` with role == CaseRole.SMOKE.
    Raise ValueError if there is not exactly one smoke case."""
    corpus = load_corpus(cases_root)
    smokes = [s for s in corpus if s.role == CaseRole.SMOKE]
    if len(smokes) != 1:
        raise ValueError(f"expected exactly one smoke case under {cases_root}, found {len(smokes)}")
    return smokes[0]
