"""base_locator_exists: per-language base locator judgment (DS6 pre-filter)."""

import inspect

from sdlc.toolchain.adapters import GoToolchain, PythonToolchain


def test_default_is_isfile(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "a_test.py").write_text("", encoding="utf-8")
    py = PythonToolchain()
    assert py.base_locator_exists(str(tmp_path), "a_test.py") is True
    assert py.base_locator_exists(str(tmp_path), "pkg") is False  # dir is not a file
    assert py.base_locator_exists(str(tmp_path), "nope.py") is False


def test_seam_routes_through_the_hook():
    src = inspect.getsource(__import__("sdlc.stages.merge.scoping", fromlist=["x"]))
    assert "adapter.base_locator_exists(" in src
    assert "os.path.isfile(os.path.join(base_wt, file))" not in src


# --- GoToolchain override: locators are import paths, keyed by go.mod -------
# (scoping.py partitions ids on `::` and hands the part before it -- the
# classname = import path GoToolchain.node_id keys ids by -- to the hook).


def _go_fixture(tmp_path, go_mod_text):
    (tmp_path / "go.mod").write_text(go_mod_text, encoding="utf-8")
    (tmp_path / "internal" / "store").mkdir(parents=True)
    return GoToolchain()


def test_go_module_prefixed_dir_exists(tmp_path):
    go = _go_fixture(tmp_path, "module example.com/foo\n")
    assert go.base_locator_exists(str(tmp_path), "example.com/foo/internal/store") is True


def test_go_bare_module_root_exists(tmp_path):
    go = _go_fixture(tmp_path, "module example.com/foo\n")
    assert go.base_locator_exists(str(tmp_path), "example.com/foo") is True


def test_go_sibling_locator_is_absent(tmp_path):
    # A locator outside the root module is absent even when a nested go.mod
    # would name it: nested module files are not scanned (brief pin).
    go = _go_fixture(tmp_path, "module example.com/foo\n")
    (tmp_path / "other.io" / "x").mkdir(parents=True)
    (tmp_path / "other.io" / "go.mod").write_text("module other.io/x\n", encoding="utf-8")
    assert go.base_locator_exists(str(tmp_path), "other.io/x") is False


def test_go_module_line_trailing_comment(tmp_path):
    go = _go_fixture(tmp_path, "module example.com/foo // v2\n")
    assert go.base_locator_exists(str(tmp_path), "example.com/foo/internal/store") is True


def test_go_module_line_quoted_path(tmp_path):
    go = _go_fixture(tmp_path, 'module "example.com/foo"\n')
    assert go.base_locator_exists(str(tmp_path), "example.com/foo/internal/store") is True


def test_go_first_module_directive_wins(tmp_path):
    # Two directives is not valid go.mod, but the pin is deterministic
    # anyway: the FIRST directive decides, later ones are never consulted.
    go = _go_fixture(tmp_path, "module example.com/foo\n\nmodule other.io/x\n")
    assert go.base_locator_exists(str(tmp_path), "example.com/foo/internal/store") is True
    assert go.base_locator_exists(str(tmp_path), "other.io/x") is False


def test_go_no_go_mod_is_absent(tmp_path):
    (tmp_path / "internal" / "store").mkdir(parents=True)
    go = GoToolchain()
    assert go.base_locator_exists(str(tmp_path), "example.com/foo/internal/store") is False


def test_go_dotdot_component_is_contained(tmp_path):
    # Report-derived classnames are arbitrary strings, and a `..` component
    # satisfies the module prefix LEXICALLY while isdir stats outside the
    # base worktree -- containment guard must reject it. The escape target
    # is a real dir outside `base` (tmp_path/escape/etc = base/../escape/etc),
    # so without the guard this isdir provably answers True (RED).
    base = tmp_path / "base"
    base.mkdir()
    (base / "go.mod").write_text("module example.com/foo\n", encoding="utf-8")
    (tmp_path / "escape" / "etc").mkdir(parents=True)
    go = GoToolchain()
    assert go.base_locator_exists(str(base), "example.com/foo/../escape/etc") is False
    assert go.base_locator_exists(str(base), "example.com/foo/../../etc") is False


def test_go_absolute_form_is_contained(tmp_path):
    # `module//etc` passes the prefix check lexically (rel = "/etc") and
    # carries no `..`, but os.path.join DISCARDS root for a component that
    # starts with `/` -- unguarded, isdir probed the real absolute /etc and
    # answered True (RED on Linux). A leading slash (and a backslash, the
    # Windows path separator) cannot occur in a Go import path: malformed
    # -> absent, deferring to the authoritative collect step.
    base = tmp_path / "base"
    base.mkdir()
    (base / "go.mod").write_text("module example.com/foo\n", encoding="utf-8")
    go = GoToolchain()
    assert go.base_locator_exists(str(base), "example.com/foo//etc") is False
    assert go.base_locator_exists(str(base), "example.com/foo\\..\\escape") is False


def test_go_unparseable_module_line_is_absent(tmp_path):
    # No path (`module` alone) or a whitespace-bearing path: nothing maps
    # the locator onto the tree, so the answer is absent, not a guess.
    (tmp_path / "internal" / "store").mkdir(parents=True)
    go = GoToolchain()
    (tmp_path / "go.mod").write_text("module\n", encoding="utf-8")
    assert go.base_locator_exists(str(tmp_path), "example.com/foo/internal/store") is False
    (tmp_path / "go.mod").write_text('module "example.com/foo" extra\n', encoding="utf-8")
    assert go.base_locator_exists(str(tmp_path), "example.com/foo/internal/store") is False
