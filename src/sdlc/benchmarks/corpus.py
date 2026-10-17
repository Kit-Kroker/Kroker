"""Corpus discovery and smoke case resolution (round 015, Phase 2, US1/US2)."""

from __future__ import annotations

from pathlib import Path

import yaml

from .acceptance import Exposure, Reason, Verdict, load_acceptance
from .models import CaseRole, CaseSpec, CaseVisibility
from .oracle_id import oracle_identity

EXIT_CASES = 8
EXIT_PRIVATE = 2


class CorpusRow:
    """A row representing one case's status in the corpus."""

    def __init__(
        self,
        *,
        case_id: str,
        role: CaseRole,
        visibility: CaseVisibility | None,
        exposure: Exposure,
        verdict: Verdict | None,
        reason: Reason | None,
        stale: bool | str,
    ) -> None:
        self.case_id = case_id
        self.role = role
        self.visibility = visibility
        self.exposure = exposure
        self.verdict = verdict
        self.reason = reason
        self.stale = stale


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


def corpus_status(cases_root: Path | str | None = None) -> list[CorpusRow]:
    """Inspects all cases and builds a CorpusRow for each.

    016 (FR-017/FR-022): with ``cases_root`` given, behaviour is exactly as
    before (one root, exposure from the acceptance record). With None, the
    walk spans both roots via ``iter_case_dirs()`` and every row's exposure
    comes from ``root_exposure`` — where the case lives, not what an old
    record says (D-4).

    Stale logic:
    - If there is no acceptance.yaml: stale is 'not assessed'
    - If there is an acceptance.yaml:
      - compute current oracle_identity (if oracle/ exists)
      - if record.oracle_id != current identity: stale is True
      - else: stale is False
    """
    from .paths import iter_case_dirs, root_exposure

    if cases_root is not None:
        root = Path(cases_root)
        specs = load_corpus(root)
        pairs = [(root, root / spec.case_id) for spec in specs]
        specs_by_dir = {root / spec.case_id: spec for spec in specs}
        exposure_from_root = False
    else:
        pairs = iter_case_dirs()
        specs_by_dir = {}
        for _root, case_dir in pairs:
            raw = yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))
            specs_by_dir[case_dir] = CaseSpec(**raw)
        exposure_from_root = True

    rows: list[CorpusRow] = []

    for _root, case_dir in pairs:
        spec = specs_by_dir[case_dir]
        record = load_acceptance(case_dir)

        oracle_dir = case_dir / "oracle"
        current_oid = oracle_identity(oracle_dir) if oracle_dir.is_dir() else None

        verdict: Verdict | None = None
        reason: Reason | None = None
        exposure: Exposure = "repo_public"
        stale: bool | str

        if record is None:
            stale = "not assessed"
        else:
            verdict = record.verdict
            reason = record.reason
            exposure = record.exposure
            if current_oid is not None and record.oracle_id != current_oid:
                stale = True
            elif current_oid is None and record.oracle_id is not None:
                stale = True
            else:
                stale = False
        if exposure_from_root:
            exposure = root_exposure(case_dir)

        rows.append(
            CorpusRow(
                case_id=spec.case_id,
                role=spec.role,
                visibility=spec.visibility,
                exposure=exposure,
                verdict=verdict,
                reason=reason,
                stale=stale,
            )
        )

    return rows


def render_corpus_status(rows: list[CorpusRow], store_note: str | None = None) -> str:
    """Renders ASCII table of corpus status and summary tally.

    016: ``store_note`` is None for byte-identical legacy output; with a
    note, it is printed as the closing line (the three shapes
    ``dispatch_corpus`` may pass live there)."""
    lines: list[str] = []

    # Table header
    lines.append(
        f"{'Case':<38} {'Role':<8} {'Visibility':<11} {'Exposure':<12} "
        f"{'Verdict':<14} {'Reason':<14} {'Stale':<12}"
    )
    lines.append("-" * 115)

    n_accepted_or_provisional = 0
    n_private = 0

    parked_lines: list[str] = []

    for r in rows:
        role_str = r.role.value
        vis_str = r.visibility.value if r.visibility is not None else "-"
        exp_str = r.exposure
        verdict_str = r.verdict.value if r.verdict is not None else "-"
        reason_str = r.reason.value if r.reason is not None else "-"
        if isinstance(r.stale, bool):
            stale_str = "yes" if r.stale else "no"
        else:
            stale_str = str(r.stale)

        lines.append(
            f"{r.case_id:<38} {role_str:<8} {vis_str:<11} {exp_str:<12} "
            f"{verdict_str:<14} {reason_str:<14} {stale_str:<12}"
        )

        if r.role == CaseRole.PARKED:
            parked_lines.append(f"  {r.case_id}: parked ({reason_str})")

        # Tally counts only non-stale accepted or provisional corpus cases
        if r.role == CaseRole.CORPUS and r.stale is False:
            if r.verdict in (Verdict.ACCEPTED, Verdict.PROVISIONAL):
                n_accepted_or_provisional += 1
                if r.visibility == CaseVisibility.PRIVATE:
                    n_private += 1

    lines.append("")
    if parked_lines:
        lines.append("Parked cases:")
        lines.extend(parked_lines)
        lines.append("")

    lines.append(
        f"{n_accepted_or_provisional} of {EXIT_CASES} accepted or provisional, "
        f"{n_private} of {EXIT_PRIVATE} private"
    )

    if store_note is not None:
        lines.append(store_note)

    return "\n".join(lines)
