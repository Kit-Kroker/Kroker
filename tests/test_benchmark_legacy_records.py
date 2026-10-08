"""PIN: stored benchmark records load; pre-012/012 shapes hold per record.

Contract 012 §7.1 in its no-regression reading (FR-027, ruling R-11):
every stored line that loaded at base still loads — no line skipped that
loaded at base. Lines that never loaded at base are pinned, not forgiven:
exactly 51 lines across five frozen ``bench-herdr-probe-*`` runs fail
validation on the removed ``harness`` value ``herdr`` (the value existed
when those runs were written and was removed with the adapter). Any other
validation failure fails this test.

Pre-012 vs 012 (T002 pinned "every stored record is pre-012"; amended in
T025 after the two authorized smoke runs added 012 records to the tree):
a non-drift record is either pre-012 (``kroker_commit`` None — is_pre012)
or a genuine 012 record carrying its commit. Anything in between fails.

Records are read IN PLACE, never copied or modified. The root is
resolved exactly as the recorder does (SDLC_BENCHMARKS_ROOT, default
``runs/benchmarks``). With no stored records the module skips: the
host/CI without a ``runs/`` mount is a valid environment.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sdlc.benchmarks.models import BenchmarkRecord

try:  # guarded: the helper arrives with the round's model edit
    from sdlc.benchmarks.models import is_pre012
except ImportError:
    is_pre012 = None  # type: ignore[assignment]

# The recorder is not edited by this task, so import its real root
# resolver (SDLC_BENCHMARKS_ROOT override, default runs/benchmarks).
from sdlc.benchmarks.recorder import _root as _resolve_records_root

DRIFT_CASE_ID = "_production"

# runs/ is frozen: the herdr-probe runs will never gain lines, so this
# count is stable. A different number means the rule drifted — stop and
# diagnose, do not loosen it here.
EXPECTED_TOLERATED = 51

_RECORDS_ROOT = Path(_resolve_records_root())
_RECORD_FILES = sorted(_RECORDS_ROOT.rglob("*.jsonl")) if _RECORDS_ROOT.is_dir() else []

if not _RECORD_FILES:
    pytest.skip(
        "no stored benchmark records under "
        f"{_RECORDS_ROOT} (SDLC_BENCHMARKS_ROOT or default runs/benchmarks); "
        "nothing stored here to pin compatibility against",
        allow_module_level=True,
    )


def _is_removed_herdr_harness(exc: ValidationError) -> bool:
    """True only for the one known never-loaded-at-base failure shape."""
    errors = exc.errors()
    # pydantic 2.13 omits "input_value" for this enum error, so "herdr" is
    # asserted only when the key is present; the single-error + loc + enum
    # type conditions pin the shape the rest of the way.
    input_value = errors[0].get("input_value")
    return (
        len(errors) == 1
        and errors[0].get("loc") == ("harness",)
        and errors[0].get("type") == "enum"
        and (input_value is None or input_value == "herdr")
    )


def test_stored_records_load_and_non_drift_are_pre012() -> None:
    non_empty_lines = 0
    validated = 0
    tolerated = 0
    for path in _RECORD_FILES:
        with path.open("r", encoding="utf-8") as handle:
            for lineno, raw in enumerate(handle, start=1):
                if not raw.strip():
                    continue
                non_empty_lines += 1
                try:
                    record = BenchmarkRecord.model_validate_json(raw)
                except ValidationError as exc:
                    if _is_removed_herdr_harness(exc):
                        tolerated += 1
                        continue
                    pytest.fail(f"{path}:{lineno} does not validate as BenchmarkRecord: {exc}")
                validated += 1
                if is_pre012 is not None and record.case_id != DRIFT_CASE_ID:
                    # T025 amendment: the stored tree is no longer purely
                    # pre-012 — the two authorized 012 smoke runs
                    # (bench-todo-api-greenfield-1791472617, -1791479569)
                    # added genuine 012 records with provenance. A record
                    # that fails is_pre012 must therefore carry its commit
                    # (a real 012 record), never be a malformed pre-012 one.
                    if not is_pre012(record):
                        assert record.kroker_commit is not None, (
                            f"{path}:{lineno} case_id={record.case_id!r} is neither "
                            "pre-012 (kroker_commit None) nor a provenance-carrying "
                            "012 record"
                        )
    assert tolerated == EXPECTED_TOLERATED, (
        f"tolerated {tolerated} never-loaded herdr lines, expected {EXPECTED_TOLERATED}"
    )
    assert validated + tolerated == non_empty_lines, (
        f"validated {validated} + tolerated {tolerated} != {non_empty_lines} non-empty lines"
    )
