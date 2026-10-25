"""Tests for sdlc.artifacts.generated (017 T004, US5, FR-050)."""

from __future__ import annotations

import pytest

from sdlc.artifacts.generated import GENERATED_DIRS, is_generated


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        # Non-generated source paths
        ("src/sdlc/tools.py", False),
        ("tests/test_foo.py", False),
        ("README.md", False),
        ("app/main.py", False),
        ("docs/index.md", False),
        ("package.json", False),
        ("requirements.txt", False),
        # Direct or nested __pycache__ and .pyc
        ("__pycache__/foo.py", True),
        ("foo/__pycache__/bar.cpython-313.pyc", True),
        ("foo.pyc", True),
        ("dir/sub/file.pyc", True),
        # Test and linter caches (GENERATED_DIRS)
        (".pytest_cache/v/cache/nodeids", True),
        (".mypy_cache/3.13/foo.data.json", True),
        (".ruff_cache/content/abc", True),
        (".tox/py313/bin/pytest", True),
        # Egg-info pattern matching
        ("my_package.egg-info/PKG-INFO", True),
        ("nested/dir/pkg.egg-info/SOURCES.txt", True),
        # Dependency/vendor paths not in GENERATED_DIRS
        ("node_modules/express/index.js", False),
        (".venv/lib/python3.13/site-packages/pip", False),
        ("vendor/bundle/setup.rb", False),
        ("dist/bundle.js", False),
        ("build/lib/module.py", False),
        (".next/server/pages.js", False),
        (".git/config", False),
        # Windows-style backslashes
        ("src\\__pycache__\\test.pyc", True),
        ("foo\\.pytest_cache\\test", True),
        ("dist\\bundle.js", False),
    ],
)
def test_is_generated(path: str, expected: bool):
    assert is_generated(path) is expected


def test_generated_dirs_set():
    assert GENERATED_DIRS == frozenset(
        {
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            ".tox",
        }
    )
