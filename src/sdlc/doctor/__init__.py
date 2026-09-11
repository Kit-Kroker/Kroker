"""F2 doctor -- setup diagnosis for this repo's own operating surface.

See docs/superpowers/specs/2026-09-10-f2-doctor-design.md. Doctor is
READ-ONLY: no check creates, writes, or deletes anything (spec section 8).
"""

from .models import CheckResult, Status, exit_code

__all__ = ["CheckResult", "Status", "exit_code"]
