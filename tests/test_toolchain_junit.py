import pytest

from sdlc.toolchain.adapters import PythonToolchain
from sdlc.toolchain.junit import shell_safe, testcase_outcomes

XML = """<?xml version="1.0"?><testsuites><testsuite tests="5">
<testcase classname="" name="tests.test_broken" file="tests/test_broken.py"><error/></testcase>
<testcase classname="tests.test_a.TestC" name="test_y" file="tests\\test_a.py"><failure/></testcase>
<testcase classname="tests.test_a" name="test_p[2]" file="tests\\test_a.py"><failure/></testcase>
<testcase classname="tests.test_a" name="test_ok" file="tests\\test_a.py"/>
<testcase classname="tests.test_a" name="test_skip" file="tests\\test_a.py"><skipped/></testcase>
</testsuite></testsuites>"""


def test_node_ids_are_posix_and_class_aware():
    assert testcase_outcomes(XML) == {
        "tests/test_broken.py": False,
        "tests/test_a.py::TestC::test_y": False,
        "tests/test_a.py::test_p[2]": False,
        "tests/test_a.py::test_ok": True,
    }


def test_missing_or_unparseable_report_is_none_not_empty():
    assert testcase_outcomes("") is None
    assert testcase_outcomes("<not xml") is None


def test_crafted_ids_never_reach_a_shell():
    evil = 'tests/t.py::test_x["&del /q *&"]'
    assert not shell_safe(evil)
    assert shell_safe("tests/test_a.py::TestC::test_p[2]")
    with pytest.raises(ValueError):
        PythonToolchain().selected_tests_cmd([evil], "o.xml")
    with pytest.raises(ValueError):
        PythonToolchain().collect_ids_cmd([evil])
