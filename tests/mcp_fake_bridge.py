"""The fake bridge for MCP parity tests (022 T023, plan T040).

Run as a subprocess by tests/test_operator_mcp_parity.py (T024) through
the REAL server binary's --bridge-cmd, and directly by the T010 hygiene
case:

    python tests/mcp_fake_bridge.py <data_dir> [record.json] [--print-in-verb]

<data_dir> backs operator_fakes.build_fake_deps (board + fake fleet).
[record.json], when given, receives the recorder dump (signals + starts)
after serve() returns — US2's write parity asserts against it. With
--print-in-verb, the list_projects verb misbehaves by print()ing before
it runs: everything it prints must land on stderr, because fd 1 is the
protocol channel (the hygiene case pins its marker on stderr).

Stdlib + sdlc only; no pytest import (it must run cold in a subprocess).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# sys.path[0] is this file's directory (tests/), so the sibling fakes
# module imports without a package context.
from operator_fakes import build_fake_deps, record_to

from sdlc.operator import bridge, tools


def _install_printing_verb() -> None:
    """Make list_projects print() before running (the hygiene probe).

    The marker string is pinned by test_fake_bridge_print_in_verb_keeps_
    stdout_pure_json: after isolate_stdout(), print() writes to fd 2, so
    the marker must appear on stderr and never on the protocol channel.
    """

    real = tools.list_projects

    async def printing_list_projects(deps, **kwargs):
        print("HYGIENE-MARKER-7f3a: a verb print()ed; this must land on stderr")
        return await real(deps, **kwargs)

    tools.list_projects = printing_list_projects


def main() -> None:
    argv = [a for a in sys.argv[1:]]
    print_flag = "--print-in-verb" in argv
    argv = [a for a in argv if a != "--print-in-verb"]
    data_dir = Path(argv[0]) if argv else Path(".mcp_fake_bridge_data")
    data_dir.mkdir(parents=True, exist_ok=True)
    record = Path(argv[1]) if len(argv) > 1 else None
    # The confirmed=false race (FR-006): with this env set, the fake
    # handles KEEP the pending item after signaling, so the reply comes
    # back confirmed=false (parity tests flip it per spawn).
    keep_pending = os.environ.get("SDLC_FAKE_KEEP_PENDING") == "1"

    def dump_record() -> None:
        if record is None:
            return
        try:
            record_to(record)
        except Exception:
            # No deps built yet: an empty timeline still gives the test a
            # file to read.
            record.write_text('{"signals": [], "started": []}\n', encoding="utf-8")

    def wrap_handle(handle) -> None:
        # Eager record dumps: the server kills this child on its own exit
        # (kill_on_drop), so an exit-time dump alone races the SIGKILL.
        # The timeline is on disk the moment it changes.
        original = handle.signal

        async def signal(name, *args, **kw):
            await original(name, *args, **kw)
            dump_record()

        handle.signal = signal

    def factory(actor: str):
        deps = build_fake_deps(data_dir, actor)
        if keep_pending:
            for handle in deps.recorder.handles.values():
                handle.drop_on_signal = False
        if record is not None:
            for handle in deps.recorder.handles.values():
                wrap_handle(handle)
            dump_record()
        return deps

    proto = bridge.isolate_stdout()  # protocol fd 1; prints go to stderr
    if print_flag:
        _install_printing_verb()
    try:
        asyncio.run(bridge._serve_pipes(factory, proto))
    finally:
        # Starts (US3) and any straggler state still land here.
        dump_record()


if __name__ == "__main__":
    main()
