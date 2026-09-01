"""Fixtures under this directory are DATA, not tests.

mini_calc is a miniature DevEval-shaped repository (E-79) whose unit_tests/
and acceptance_tests/ match pytest's discovery globs; without this ignore the
project's own suite tries to collect them and fails on `import calc`.

The ignore lives here rather than inside mini_calc/ on purpose: a conftest at
that repository's root would be copied into the generated case's reference/
dir, and would then suppress collection of the real oracle during
`sdlc benchmark verify-case`.
"""

collect_ignore_glob = ["mini_calc/*"]
