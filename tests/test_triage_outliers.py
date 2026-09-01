"""FR-902 size and duplication outliers (E-41d)."""

from sdlc.measurement import CollectionState
from sdlc.toolchain.adapters import PythonToolchain, ToolchainAdapter
from sdlc.triage.models import FixClass
from sdlc.triage.signals import outliers


class _NoParser(ToolchainAdapter):
    """A language with thresholds but no function parser."""

    kind = None
    markers = ()
    source_extensions = (".xx",)
    max_file_loc = 10
    max_function_loc = 5
    min_clone_loc = 3

    def test_cmd(self, coverage: bool = True) -> str:
        return "true"

    def lint_cmd(self) -> str:
        return "true"

    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        return "true"


def _rules(result):
    return {f.rule for f in result.findings}


# ---- normalization ----------------------------------------------------


def test_normalized_lines_drops_blanks_and_whole_line_comments():
    text = "x = 1\n\n# a comment\n// another\n  y = 2\n"
    assert outliers.normalized_lines(text) == [(1, "x = 1"), (5, "y = 2")]


def test_normalized_lines_keeps_the_original_line_numbers():
    text = "\n\n\nz = 3\n"
    assert outliers.normalized_lines(text) == [(4, "z = 3")]


# ---- size rules -------------------------------------------------------


def test_oversized_file_fires_above_the_adapter_threshold():
    big = "".join(f"x{i} = {i}\n" for i in range(900))
    r = outliers.evaluate({"big.py": big}, PythonToolchain())
    f = next(f for f in r.findings if f.rule == "oversized_file")
    assert f.fix_class is FixClass.STRUCTURAL
    assert f.path == "big.py"


def test_a_file_under_the_threshold_does_not_fire():
    r = outliers.evaluate({"small.py": "x = 1\n"}, PythonToolchain())
    assert "oversized_file" not in _rules(r)


def test_oversized_function_fires_and_names_the_function():
    body = "".join(f"    y{i} = {i}\n" for i in range(150))
    r = outliers.evaluate({"m.py": f"def huge():\n{body}"}, PythonToolchain())
    f = next(f for f in r.findings if f.rule == "oversized_function")
    assert "huge" in f.detail
    assert f.fix_class is FixClass.STRUCTURAL


def test_function_metric_is_not_collected_when_the_language_has_no_parser():
    r = outliers.evaluate({"a.xx": "line\n" * 3}, _NoParser())
    assert r.metrics[outliers.M_FUNCTION_LOC].state is CollectionState.NOT_COLLECTED
    assert "oversized_function" not in _rules(r)
    # The SIGNAL still collected -- it measured file sizes.
    assert r.collected.state is CollectionState.MEASURED


def test_no_toolchain_leaves_both_size_metrics_not_collected():
    r = outliers.evaluate({"a.py": "x = 1\n"}, None)
    assert r.metrics[outliers.M_MAX_FILE_LOC].state is CollectionState.NOT_COLLECTED
    assert r.metrics[outliers.M_FUNCTION_LOC].state is CollectionState.NOT_COLLECTED
    assert r.findings == []


# ---- duplication ------------------------------------------------------


def test_a_clone_across_two_files_is_reported_once():
    block = "".join(f"a{i} = {i}\n" for i in range(40))
    r = outliers.evaluate({"one.py": block, "two.py": block}, PythonToolchain())
    dups = [f for f in r.findings if f.rule == "duplicated_block"]
    # ONE finding, not eleven: a 40-line clone scanned with a 30-line window
    # produces eleven overlapping hits, and clone_groups merges them.
    assert len(dups) == 1
    assert dups[0].fix_class is FixClass.JUDGEMENT
    assert "one.py" in dups[0].detail and "two.py" in dups[0].detail


def test_duplication_within_one_file_is_not_a_clone_group():
    block = "".join(f"a{i} = {i}\n" for i in range(40))
    r = outliers.evaluate({"one.py": block + block}, PythonToolchain())
    assert "duplicated_block" not in _rules(r)


def test_a_short_repeated_block_is_below_the_window():
    block = "a = 1\nb = 2\n"
    r = outliers.evaluate({"one.py": block, "two.py": block}, PythonToolchain())
    assert "duplicated_block" not in _rules(r)


def test_indentation_only_differences_still_count_as_a_clone():
    block = "".join(f"a{i} = {i}\n" for i in range(40))
    indented = "".join(f"    a{i} = {i}\n" for i in range(40))
    r = outliers.evaluate({"one.py": block, "two.py": indented}, PythonToolchain())
    assert "duplicated_block" in _rules(r)


def test_exceeding_the_file_cap_makes_the_ratio_not_collected():
    blobs = {f"f{i}.py": "x = 1\n" for i in range(outliers.MAX_FILES + 1)}
    r = outliers.evaluate(blobs, PythonToolchain())
    assert r.metrics[outliers.M_DUP_RATIO].state is CollectionState.NOT_COLLECTED
    assert "duplicated_block" not in _rules(r)


def test_the_duplication_ratio_is_measured_on_a_clean_repo():
    r = outliers.evaluate({"a.py": "x = 1\n"}, PythonToolchain())
    m = r.metrics[outliers.M_DUP_RATIO]
    assert m.state is CollectionState.MEASURED
    assert m.value == 0.0
