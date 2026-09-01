"""promptfoo integration for the prompt gate (E-82)."""

from __future__ import annotations

import os
import shutil
import sysconfig


def promptfoo_bin() -> str | None:
    """Absolute path to the promptfoo CLI, or None when it is not installed.

    ``shutil.which`` alone is not enough. ``pip install -e .[eval]`` installs
    the Python wrapper, which drops a console script into the interpreter's
    scripts directory -- and that directory is frequently NOT on the shell
    PATH (notably on Windows, and in any venv the shell has not activated).
    Since promptfoo is declared as a Python dependency here, resolve it
    through the Python environment rather than trusting the shell.

    PATH is still consulted first, so an explicit `npm install -g promptfoo`
    or a user-preferred build wins over the wrapper.
    """
    found = shutil.which("promptfoo")
    if found:
        return found
    scripts = sysconfig.get_path("scripts")
    for name in ("promptfoo.exe", "promptfoo"):
        candidate = os.path.join(scripts, name)
        if os.path.isfile(candidate):
            return candidate
    return None
