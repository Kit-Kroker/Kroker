"""Pin the capture order behind the opt-in private-store tests (backlog
2026-11-03-private-leak-dotenv-import-order).

The skip decision of the opt-in tests keys on ``REAL_PRIVATE_ROOT``. It must
be frozen at conftest import -- before any test module exists -- because
``src/sdlc/worker.py`` runs ``load_dotenv()`` at import time and can inject
the machine's ``.env`` binding into ``os.environ`` mid-collection: whichever
module imports ``sdlc.worker`` first decides what a module-local
``os.environ.get()`` in a later-collected test module sees. On a store-bound
machine that made ``test_private_leak``'s 60s+ repo scan run inside the
default fast tier while the same file alone skipped it.
"""

import ast
import os
import sys
from pathlib import Path

from tests.conftest import REAL_PRIVATE_ROOT

# Simulate dotenv mid-suite, the way worker.py's import-time load_dotenv()
# does: set the variable at THIS module's import. Collection imports this
# module after tests/conftest.py (conftest always comes first), so by the
# time this line runs the capture must already be frozen. The value points
# at a path that cannot exist as a store, so even a hypothetical leak of the
# binding into the opt-in tests degrades to the ABSENT_NOTE skip, not a
# store read. The autouse _no_private_cases_root fixture scrubs the variable
# before each test, and no module reads it at import time any more.
_SIMULATED_BINDING = str(Path(__file__).resolve().parent / ".simulated-dotenv-store-NONEXISTENT")
os.environ["SDLC_PRIVATE_CASES_ROOT"] = _SIMULATED_BINDING


def test_conftest_capture_is_frozen_before_test_module_imports():
    """The constant the opt-in tests skip on must never reflect an import
    that happened after conftest -- including this module's simulated dotenv
    write, and including a re-execution of conftest under a second module
    identity (the ``from tests.conftest import`` alias)."""
    assert REAL_PRIVATE_ROOT != _SIMULATED_BINDING
    # The alias exposes exactly the module object pytest captured in. A
    # second module object would have re-read os.environ at THIS import --
    # after the simulated write above -- and its constant would equal the
    # simulated binding, failing the previous assert.
    assert sys.modules["tests.conftest"].REAL_PRIVATE_ROOT is REAL_PRIVATE_ROOT


def test_conftest_registers_the_tests_conftest_alias_at_import():
    """Source pin: tests/conftest.py must register itself under the
    ``tests.conftest`` name at module import. This pytest (9.x) imports
    every conftest under its bare basename ``conftest``, and a later
    nested conftest (tests/fixtures/conftest.py) REPLACES that entry --
    the bare name is not a stable handle, and pytest never creates the
    dotted name itself. Without this registration, the first helper
    import (``from tests.conftest import ...``, the repo convention)
    would import the file a second time as a fresh module, re-executing
    the REAL_PRIVATE_ROOT capture mid-collection -- after whichever test
    module first imported sdlc.worker and let load_dotenv() run. The
    harm lands at collection of files that sort before any test could
    observe it, so the registration is pinned in source, not at runtime
    (same approach as the repo's other source-grep pins). Parsed as an AST,
    not matched as text: a commented-out registration must fail this pin."""
    source = (Path(__file__).resolve().parent / "conftest.py").read_text(encoding="utf-8")
    calls = [
        n
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "setdefault"
        and isinstance(n.func.value, ast.Attribute)
        and isinstance(n.func.value.value, ast.Name)
        and n.func.value.value.id == "sys"
        and n.func.value.attr == "modules"
        and n.args
        and isinstance(n.args[0], ast.Constant)
        and n.args[0].value == "tests.conftest"
    ]
    assert calls, (
        "tests/conftest.py lost its sys.modules.setdefault('tests.conftest', ...) "
        "registration: without it the first `from tests.conftest import ...` "
        "re-executes the file mid-suite and re-reads SDLC_PRIVATE_CASES_ROOT "
        "after dotenv importers have run (backlog "
        "2026-11-03-private-leak-dotenv-import-order)"
    )
