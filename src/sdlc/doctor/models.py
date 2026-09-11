"""F2 doctor: what a check reports, and what that means for the exit code.

Four outcomes rather than three (spec section 4). SKIP is load-bearing: a
feature that is switched off has no configuration to be wrong, and rendering
that as PASS would claim doctor checked something it did not. SKIP is always
printed with its reason -- an omitted line is indistinguishable from a check
that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class CheckResult:
    """One check's verdict. Frozen: a rendered report must not be able to
    disagree with the exit code computed from the same list."""

    name: str
    status: Status
    detail: str

    @classmethod
    def ok(cls, name: str, detail: str = "") -> CheckResult:
        return cls(name=name, status=Status.PASS, detail=detail)

    @classmethod
    def warn(cls, name: str, detail: str) -> CheckResult:
        return cls(name=name, status=Status.WARN, detail=detail)

    @classmethod
    def fail(cls, name: str, detail: str) -> CheckResult:
        return cls(name=name, status=Status.FAIL, detail=detail)

    @classmethod
    def skip(cls, name: str, detail: str) -> CheckResult:
        return cls(name=name, status=Status.SKIP, detail=detail)


def exit_code(results: list[CheckResult], *, strict: bool) -> int:
    """0 unless something is broken. A FAIL always exits 1; a WARN exits 1
    only under --strict. SKIP never contributes -- it reports that a surface
    was not required, which is not a finding an operator must act on."""
    if any(r.status is Status.FAIL for r in results):
        return 1
    if strict and any(r.status is Status.WARN for r in results):
        return 1
    return 0
