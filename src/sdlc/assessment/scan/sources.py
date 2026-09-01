"""The source-file extension list shared by S1 and S3 (review finding 1).

Sited here -- a scan-level constant that belongs to neither signal -- because
both signals select their blobs with it: S1 groups source files into packages,
and S3 extracts entry points from source blobs. Editing this tuple changes
both signals' output, so both declare it as a `rule_module` and `rules_sha`
hashes it into both memo keys. Without that, adding `.vue` or dropping `.rb`
would silently serve a stale S3 (the exact E-3 / D10 hazard).

Language-agnostic and deliberately NOT ToolchainAdapter.source_extensions:
only PythonToolchain exists, so gating on the adapter would make the scan
report nothing for the JS/TS repositories Tier 0 actually receives. This
mirrors triage/signals/scaffold.py's own _SOURCE_EXTENSIONS, re-declared
here rather than imported -- scan/ may not import triage/signals/ (module
purity, spec section 3).
"""

from __future__ import annotations

SOURCE_EXTENSIONS: tuple[str, ...] = (
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".php",
    ".cs",
    ".kt",
    ".swift",
    ".scala",
    ".ex",
    ".exs",
    ".vue",
    ".svelte",
)
