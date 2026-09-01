"""Pure grading logic for the held-out oracle (E-31)."""

from sdlc.benchmarks.oracle import (
    _truncate_diff,
    grade_from_junit,
    held_out_ok,
    language_match,
)

JUNIT_MIXED = (
    '<testsuites><testsuite tests="4" failures="1" errors="1" skipped="0">'
    '<testcase name="a"/><testcase name="b"><failure/></testcase>'
    '<testcase name="c"><error/></testcase><testcase name="d"/>'
    "</testsuite></testsuites>"
)
JUNIT_ROOT_SUITE = (
    '<testsuite tests="2" failures="0" errors="0" skipped="0">'
    '<testcase name="a"/><testcase name="b"/></testsuite>'
)
JUNIT_WITH_SKIP = (
    '<testsuite tests="3" failures="0" errors="0" skipped="1">'
    '<testcase name="a"/><testcase name="b"/>'
    '<testcase name="c"><skipped/></testcase></testsuite>'
)


def test_grade_mixed_pass_fail_error():
    score, passed, total, _ = grade_from_junit(JUNIT_MIXED)
    assert (passed, total) == (2, 4)
    assert score == 0.5


def test_grade_all_pass_is_one():
    score, passed, total, _ = grade_from_junit(JUNIT_ROOT_SUITE)
    assert (score, passed, total) == (1.0, 2, 2)


def test_grade_excludes_skipped_from_denominator():
    score, passed, total, _ = grade_from_junit(JUNIT_WITH_SKIP)
    assert (passed, total) == (2, 2)  # skipped test dropped from both
    assert score == 1.0


def test_grade_malformed_returns_none():
    score, passed, total, detail = grade_from_junit("<not-xml")
    assert score is None and (passed, total) == (0, 0)
    assert "unparseable" in detail


def test_grade_empty_returns_none():
    assert grade_from_junit("")[0] is None


def test_grade_zero_gradable_returns_none():
    xml = '<testsuite tests="0" failures="0" errors="0" skipped="0"/>'
    score, _, _, detail = grade_from_junit(xml)
    assert score is None and "no gradable" in detail


def test_held_out_ok_true_when_no_oracle_paths():
    assert held_out_ok(["app.py", "src/store.py"]) is True


def test_held_out_ok_false_when_oracle_path_in_diff():
    assert held_out_ok(["app.py", "oracle/test_crud.py"]) is False
    assert held_out_ok(["oracle"]) is False


def test_language_match():
    assert language_match("python", "python") is True
    assert language_match("python", "typescript") is False
    assert language_match("python", None) is False


from sdlc.benchmarks.oracle import grade_testcases_from_junit

JUNIT_WITH_FILE_ATTR = (
    '<testsuites><testsuite tests="3" failures="1" errors="0" skipped="0">'
    '<testcase classname="test_crud" name="test_create_todo" '
    'file="test_crud.py"/>'
    '<testcase classname="test_crud" name="test_delete_todo" '
    'file="test_crud.py"><failure/></testcase>'
    '<testcase classname="test_crud" name="test_skipped" '
    'file="test_crud.py"><skipped/></testcase>'
    "</testsuite></testsuites>"
)

JUNIT_NO_FILE_ATTR = (
    '<testsuite tests="1" failures="0" errors="0" skipped="0">'
    '<testcase classname="test_crud" name="test_x"/></testsuite>'
)

JUNIT_NO_CLASSNAME = (
    '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="test_x"/></testsuite>'
)


def test_grade_testcases_keys_by_file_and_name_when_file_attr_present():
    results = grade_testcases_from_junit(JUNIT_WITH_FILE_ATTR)
    assert results == {
        "test_crud.py::test_create_todo": True,
        "test_crud.py::test_delete_todo": False,
    }
    # the skipped test is dropped entirely -- neither pass nor fail
    assert "test_crud.py::test_skipped" not in results


def test_grade_testcases_falls_back_to_classname_when_no_file_attr():
    results = grade_testcases_from_junit(JUNIT_NO_FILE_ATTR)
    assert results == {"test_crud::test_x": True}


def test_grade_testcases_falls_back_to_name_when_neither_present():
    results = grade_testcases_from_junit(JUNIT_NO_CLASSNAME)
    assert results == {"test_x": True}


def test_grade_testcases_error_child_is_failure():
    xml = (
        '<testsuite tests="1" failures="0" errors="1" skipped="0">'
        '<testcase name="a"><error/></testcase></testsuite>'
    )
    assert grade_testcases_from_junit(xml) == {"a": False}


def test_grade_testcases_empty_or_malformed_returns_empty_dict():
    assert grade_testcases_from_junit("") == {}
    assert grade_testcases_from_junit("<not-xml") == {}


def test_truncate_diff_passes_short_text_through_unchanged():
    text = "a" * 100
    assert _truncate_diff(text, max_chars=20000) == text


def test_truncate_diff_at_exact_boundary_unchanged():
    text = "a" * 20000
    assert _truncate_diff(text, max_chars=20000) == text


def test_truncate_diff_truncates_long_text_with_marker():
    text = "a" * 25000
    out = _truncate_diff(text, max_chars=20000)
    assert out.startswith("a" * 20000)
    assert out != text
    assert len(out) > 20000  # marker appended
    assert "truncated" in out
    assert "5000" in out  # chars omitted count
