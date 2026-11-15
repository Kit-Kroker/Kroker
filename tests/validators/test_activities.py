"""Activities of the FR-205 validators library (`sdlc.validators.activities`).

Called directly as plain functions here (no worker): the contract under test
is the mapping itself; the registration test only pins that the worker boot
path picks the module's ACTIVITIES up.
"""

from __future__ import annotations

from sdlc.validators import ACTIVITIES
from sdlc.validators.activities import paths_exist


def test_paths_exist_maps_existence(tmp_path):  # direct activity-function call, no worker
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x")
    assert paths_exist(str(tmp_path), ["src/app.py", "src/missing.py"]) == {
        "src/app.py": True,
        "src/missing.py": False,
    }


def test_paths_exist_maps_empty_and_dot_prefixed_tokens(tmp_path):
    """Empty tokens map to False -- they must never resolve to the repo root."""
    (tmp_path / "app.py").write_text("x")
    assert paths_exist(str(tmp_path), ["", "  ", "./app.py"]) == {
        "": False,
        "  ": False,
        "./app.py": True,
    }


def test_paths_exist_settles_absolute_form_against_the_repo(tmp_path):
    """Final-review pin: an absolute-form citation must not escape the repo.
    pathlib's `root / "/src/app.py"` would REPLACE the root and stat the
    worker HOST filesystem, false-missing a real repo file -- and a false
    missing path DISCARDs the question citing it downstream."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x")
    assert paths_exist(str(tmp_path), ["/src/app.py"]) == {"/src/app.py": True}


def test_dotdot_segment_tokens_are_unsettled_and_never_missing(tmp_path):
    """A token with a `..` path segment cannot be settled against the repo:
    it is not checked and not mapped, so it never lands in the consumer's
    missing set (`frozenset(p for p, ok in exists.items() if not ok)`,
    clarify/step.py) and can never ground a question discard. Windows
    separators normalize first, so the backslash form is caught too."""
    (tmp_path / "app.py").write_text("x")
    exists = paths_exist(str(tmp_path), ["app.py", "../../etc/passwd.py", "..\\..\\etc\\passwd.py"])
    missing = frozenset(p for p, ok in exists.items() if not ok)
    assert missing == set()
    assert exists == {"app.py": True}  # only the settleable token is mapped


def test_validators_package_exports_activities_list():
    assert ACTIVITIES == [paths_exist]


def test_worker_registers_paths_exist():
    from sdlc.worker import get_worker_activities

    assert any(fn.__name__ == "paths_exist" for fn in get_worker_activities())
