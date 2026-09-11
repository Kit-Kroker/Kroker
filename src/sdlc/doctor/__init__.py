"""F2 doctor -- setup diagnosis for this repo's own operating surface.

See docs/superpowers/specs/2026-09-10-f2-doctor-design.md. Doctor is
READ-ONLY: no check creates, writes, or deletes anything (spec section 8).
"""

from .checks import CHECKS, run_checks
from .models import CheckResult, Status, exit_code

__all__ = ["CHECKS", "CheckResult", "Status", "exit_code", "run_checks"]
