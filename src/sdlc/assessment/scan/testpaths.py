"""Which paths are TEST paths -- shared by S2, QS1, QS2 and QS3 (P3-D9).

A scan-level constant belonging to no single signal, sited here for the reason
sources.py is: four signals read it, so editing the tuple changes four
signals' output, and all four therefore declare it as a `rule_module` so
rules_sha hashes it into all four memo keys. Without that, adding "*.cy.ts"
would silently serve a stale QS1 -- the exact E-3 / D10 hazard.

Deliberately NOT ToolchainAdapter.test_globs: only PythonToolchain exists, so
gating on the adapter would make QS1 report nothing for the JS/TS repositories
Tier 0 actually receives (D4's reasoning, verbatim). The adapter's tuple stays
the authority for the TRIAGE tier, which resolves a real toolchain first.
"""

from __future__ import annotations

import fnmatch
import posixpath

# fnmatch's '*' crosses '/', so "tests/**" matches "tests/a/b.py" and
# "*/tests/**" matches any nested tests directory. Both shapes are kept
# because a convention is sometimes a basename ("test_*.py") and sometimes a
# path ("cypress/**"), exactly as baseline.find_test_files handles them.
TEST_PATH_GLOBS: tuple[str, ...] = (
    # python
    "test_*.py",
    "*_test.py",
    "conftest.py",
    "tests/**",
    "*/tests/**",
    # javascript / typescript
    "*.test.js",
    "*.test.jsx",
    "*.test.ts",
    "*.test.tsx",
    "*.spec.js",
    "*.spec.jsx",
    "*.spec.ts",
    "*.spec.tsx",
    "*.cy.js",
    "*.cy.ts",
    "__tests__/**",
    "*/__tests__/**",
    # go / rust / jvm / dotnet
    "*_test.go",
    "tests.rs",
    "*Test.java",
    "*Tests.java",
    "*Test.kt",
    "*Test.cs",
    "*Tests.cs",
    "src/test/**",
    "*/src/test/**",
    # ruby / php
    "*_spec.rb",
    "*Test.php",
    "spec/**",
    "*/spec/**",
    # cross-language directories
    "e2e/**",
    "*/e2e/**",
    "cypress/**",
    "*/cypress/**",
    "playwright/**",
    "*/playwright/**",
)


def is_test_path(path: str) -> bool:
    """True when `path` matches a test convention, by full repo-relative path
    OR by basename -- conventions come in both shapes."""
    base = posixpath.basename(path)
    return any(
        fnmatch.fnmatch(path, glob) or fnmatch.fnmatch(base, glob) for glob in TEST_PATH_GLOBS
    )
