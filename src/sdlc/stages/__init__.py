"""The pipeline's vertical slices.

STAGE_MODULES is explicit and ordered, never auto-discovered: registration
must stay deterministic and greppable, and there must be exactly one place to
edit when a stage is added. Entries appear here as their slice migrates.

Rule: adding a module to STAGE_MODULES and deleting its worker.py import
are one edit, never two.
"""

from __future__ import annotations

from types import ModuleType

STAGE_MODULES: tuple[ModuleType, ...] = ()
