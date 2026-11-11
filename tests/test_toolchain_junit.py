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


# --- node_id interpretation seam (Task 5.5) -----------------------------------

# go-junit-report's shape: classname = import path, no `file` attribute.
GO_SHAPED_XML = """<?xml version="1.0"?><testsuite tests="2">
<testcase classname="example.com/m/a" name="TestAlpha" time="0.01"/>
<testcase classname="example.com/m/a" name="TestBeta" time="0.02"><failure/></testcase>
</testsuite>"""


def test_default_still_mangles_go_shaped_classnames():
    # Without a builder callable, testcase_outcomes keeps today's pytest
    # mangling verbatim -- the lossy behavior the adapter `node_id` member
    # exists to override per language. Pinned so the default cannot drift.
    assert testcase_outcomes(GO_SHAPED_XML) == {
        "example/com/m/a.py::TestAlpha": True,
        "example/com/m/a.py::TestBeta": False,
    }


def test_python_adapter_default_matches_internal_default():
    # The ABC default is a verbatim transcription of junit._node_id: on the
    # full legacy fixture above -- empty classname (collection error), a
    # class-level testcase, a parametrized id, backslash `file` attrs -- the
    # member and the internal default must produce byte-identical maps.
    assert testcase_outcomes(XML, PythonToolchain().node_id) == testcase_outcomes(XML)
