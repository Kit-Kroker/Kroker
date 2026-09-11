"""DS3: two-point multiset difference over a line-independent identity."""

import ast
import itertools
import pathlib

from sdlc.change_scope import delta, normalize_line, normalize_path, rename_map

# DS9: scanner-trigger text is assembled at runtime, never literal in source.
EVAL_S = "return " + "ev" + "al(s)"
EVAL_T = "return " + "ev" + "al(t)"


def _k(t):
    return t


def test_identical_finding_at_both_points_is_preexisting():
    f = ("sec", "dangerous-eval", "a.py", EVAL_S)
    assert delta([f], [f], _k, {}) == ([], 1, 0)


def test_second_identical_finding_in_one_file_is_introduced():
    """The multiset case: a set difference would read 2 - 1 as nothing."""
    f = ("sec", "dangerous-eval", "a.py", EVAL_S)
    introduced, pre, res = delta([f], [f, f], _k, {})
    assert introduced == [f] and pre == 1 and res == 0


def test_rename_maps_the_base_path_so_a_moved_finding_stays_preexisting():
    base = [("lint", "F401", "old.py", "import os")]
    head = [("lint", "F401", "new.py", "import os")]
    assert delta(base, head, _k, rename_map([["old.py", "new.py"]])) == ([], 1, 0)


def test_a_deleted_finding_counts_resolved_never_introduced():
    base = [("lint", "F401", "gone.py", "import os")]
    assert delta(base, [], _k, {}) == ([], 0, 1)


def test_an_edited_line_reads_introduced_the_fail_toward_blocking_direction():
    base = [("sec", "dangerous-eval", "a.py", EVAL_S)]
    head = [("sec", "dangerous-eval", "a.py", EVAL_T)]
    introduced, pre, res = delta(base, head, _k, {})
    assert introduced == head and pre == 0 and res == 1


def test_normalize_path_is_repo_relative_posix():
    assert normalize_path(".\\src\\a.py") == "src/a.py"
    assert normalize_path("./src/a.py") == "src/a.py"
    assert normalize_path("/src/a.py") == "src/a.py"


def test_normalize_line_collapses_whitespace():
    assert normalize_line("  x =\t f( s )  \n") == "x = f( s )"


def test_delta_is_order_independent():
    """NFR-10, per-module pattern: byte-identical across input order."""
    base = [("l", "F401", "a.py", "import os"), ("l", "E501", "b.py", "x")]
    head = [
        ("l", "F401", "a.py", "import os"),
        ("l", "F401", "a.py", "import os"),
        ("l", "E501", "c.py", "y"),
    ]
    expected = delta(base, head, _k, {})
    for b in itertools.permutations(base):
        for h in itertools.permutations(head):
            assert delta(list(b), list(h), _k, {}) == expected


def test_module_is_pure():
    tree = ast.parse(pathlib.Path("src/sdlc/change_scope.py").read_text(encoding="utf-8"))
    imported = {
        a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    imported |= {
        (n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
    }
    assert imported <= {"__future__", "collections", "typing"}, imported
    called = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "open" not in called
