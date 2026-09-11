"""SG-3: pin the real pytest/ruff shapes the scoped gate depends on."""

import os
import sysconfig
import textwrap

import pytest

from sdlc.process import _bounded_shell
from sdlc.toolchain.adapters import PythonToolchain, ToolchainAdapter
from sdlc.toolchain.junit import testcase_outcomes

PY = PythonToolchain()

TESTS = textwrap.dedent(
    """
    import pytest
    class TestC:
        def test_y(self):
            assert False
    @pytest.mark.parametrize("n", [1, 2])
    def test_p(n):
        assert n == 1
    def test_ok():
        pass
    """
)


def _suite(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(TESTS, encoding="utf-8")
    (tmp_path / "tests" / "test_broken.py").write_text(
        "import nonexistent_mod_xyz\n\n\ndef test_z():\n    pass\n", encoding="utf-8"
    )


async def _sh(cmd, cwd):
    """Through the production shell path (never subprocess shell=True in test
    source: the regex scanner's shell-injection rule would flag it as
    introduced). `pytest`/`ruff` resolve from the test interpreter's scripts
    dir, as _ensure_python_env's PATH would."""
    env = dict(os.environ)
    env["PATH"] = sysconfig.get_path("scripts") + os.pathsep + env.get("PATH", "")
    return await _bounded_shell(cmd, str(cwd), 120, env=env)


@pytest.mark.asyncio
async def test_full_run_survives_a_collection_error_and_names_every_case(tmp_path):
    _suite(tmp_path)
    await _sh(PY.integration_test_cmd(".sdlc-junit.xml", coverage=False), tmp_path)
    outcomes = testcase_outcomes((tmp_path / ".sdlc-junit.xml").read_text(encoding="utf-8"))
    assert outcomes == {
        "tests/test_broken.py": False,
        "tests/test_a.py::TestC::test_y": False,
        "tests/test_a.py::test_p[1]": True,
        "tests/test_a.py::test_p[2]": False,
        "tests/test_a.py::test_ok": True,
    }


@pytest.mark.asyncio
async def test_collect_only_lists_node_ids(tmp_path):
    _suite(tmp_path)
    code, out = await _sh(PY.collect_ids_cmd(["tests/test_a.py"]), tmp_path)
    assert PY.parse_collected_ids(out) == {
        "tests/test_a.py::TestC::test_y",
        "tests/test_a.py::test_p[1]",
        "tests/test_a.py::test_p[2]",
        "tests/test_a.py::test_ok",
    }


@pytest.mark.asyncio
async def test_selected_run_reports_only_the_named_ids(tmp_path):
    _suite(tmp_path)
    ids = ["tests/test_a.py::TestC::test_y", "tests/test_a.py::test_p[2]", "tests/test_broken.py"]
    await _sh(PY.selected_tests_cmd(ids, "sel.xml"), tmp_path)
    outcomes = testcase_outcomes((tmp_path / "sel.xml").read_text(encoding="utf-8"))
    assert set(outcomes) == set(ids)
    assert not any(outcomes.values())


def _lint_tree(tmp_path, body: str):
    (tmp_path / "ruff.toml").write_text('[lint]\nselect = ["F401"]\n', encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text(body, encoding="utf-8")


@pytest.mark.asyncio
async def test_ruff_json_parses_to_relative_rows(tmp_path):
    _lint_tree(tmp_path, "x = 1\nimport os\n")
    code, out = await _sh(PY.lint_json_cmd(), tmp_path)
    assert PY.parse_lint(code, out, str(tmp_path)) == [("F401", "pkg/m.py", 2)]


@pytest.mark.asyncio
async def test_a_clean_tree_is_an_empty_measured_list(tmp_path):
    _lint_tree(tmp_path, "x = 1\n")
    code, out = await _sh(PY.lint_json_cmd(), tmp_path)
    assert PY.parse_lint(code, out, str(tmp_path)) == []


def test_tool_failure_is_none_not_empty():
    assert PY.parse_lint(2, "error: boom", ".") is None
    e902 = '[{"code": "E902", "filename": "/x/a.py", "location": {"row": 1}}]'
    assert PY.parse_lint(0, e902, "/x") is None
    assert PY.parse_lint(0, "not json", ".") is None


def test_integration_cmd_drops_maxfail_but_test_cmd_keeps_it():
    cmd = PY.integration_test_cmd(".sdlc-junit.xml")
    assert "--maxfail" not in cmd
    for flag in ("--continue-on-collection-errors", "junit_family=legacy", "--junitxml="):
        assert flag in cmd
    assert "--maxfail=25" in PY.test_cmd(coverage=True)  # triage's probe is untouched


def test_the_scoped_contract_is_abstract():
    for name in (
        "lint_json_cmd",
        "parse_lint",
        "integration_test_cmd",
        "collect_ids_cmd",
        "parse_collected_ids",
        "selected_tests_cmd",
    ):
        assert name in ToolchainAdapter.__abstractmethods__, name


def test_python_declares_policy_paths_and_suppression_syntax():
    assert "pyproject.toml" in PY.lint_policy_globs and "ruff.toml" in PY.lint_policy_globs
    import re

    assert re.search(PY.suppression_pattern, "import os  # noqa: F401")
