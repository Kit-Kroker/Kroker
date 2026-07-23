# Cursor Harness Adapter (E-35) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `cursor-agent` as a third coding-harness adapter beside `claude`/`opencode`, plus a boot-time harness version-drift check (folded E-24 intent).

**Architecture:** `CursorHarness` is a third `CodingHarness` subclass in `src/sdlc/harness/adapters.py`, registered in the `HARNESSES` dict — which makes it selectable everywhere `HarnessKind` is generic (`run_coding_task`, `expand_matrix`). Cursor's `cursor-agent` non-interactive output mirrors Claude Code's stream-json Agent-SDK shape, so the adapter is a near-twin of `ClaudeCodeHarness`. A `check_harness_versions()` helper runs at worker boot (after `validate_registry`), warning on drift and skipping when a CLI is absent.

**Tech Stack:** Python 3.14, Pydantic v2, pytest, Temporal (worker boot only).

## Global Constraints

- **Adapter + unit tests only.** No live `cursor-agent` run, no CLI install, no auth. Tests hit `parse`/`normalise_session`/`build_cmd`/`check_harness_versions` against synthetic fixtures — never a real subprocess.
- **Version pins (verbatim):** `claude` → `"2.1.218"`, `opencode` → `"1.18.4"`, `cursor-agent` → `None` (declared-but-unpinned placeholder; the check skips a `None` pin so it never warns spuriously until the CLI exists).
- **Version check is warn-on-drift and never raises.** A patch bump must not brick the worker. CLI absent (CI/fakes) → skip silently.
- **Cursor is made available/selectable only** — do **not** add `HarnessKind.CURSOR` to any benchmark case's `harnesses` list.
- **Schema is Cursor's documented shape, not a captured transcript.** Flag `_TOOL_MAP` keys, `usage` token key names, and whether `total_cost_usd` is emitted as verify-before-trusting-live-axis items (code comments), per spec §5.
- **No changes** to `harness/session.py`, `benchmarks/matrix.py`, or any case manifest.
- Logger name for all adapter logging/tests: `sdlc.harness.adapters`.

---

### Task 1: `CursorHarness` adapter + enum + registration

**Files:**
- Modify: `src/sdlc/models.py` (add enum member near line 22-24)
- Modify: `src/sdlc/harness/adapters.py` (add `CursorHarness`, extend `HARNESSES` near line 489-492)
- Test: `tests/test_cursor_harness.py` (create)

**Interfaces:**
- Consumes: `CodingHarness` (ABC), `HarnessRequest`, `HarnessRunResult`, `HarnessSession`, `SessionEvent`, `SUMMARY_MAX`, `_log` — all already in `adapters.py`; `digest_of` from `sdlc.harness.session`.
- Produces: `HarnessKind.CURSOR`; `CursorHarness()` with `build_cmd(req) -> list[str]`, `parse(stdout, exit_code) -> HarnessRunResult`, `normalise_session(stdout) -> HarnessSession`; `HARNESSES[HarnessKind.CURSOR]`.

- [ ] **Step 1: Add the enum member**

In `src/sdlc/models.py`, extend `HarnessKind` (currently lines 22-24):

```python
class HarnessKind(str, Enum):
    CLAUDE_CODE = "claude_code"   # claude -p
    OPENCODE = "opencode"         # opencode run
    CURSOR = "cursor"             # cursor-agent -p (E-35)
```

- [ ] **Step 2: Write the failing adapter tests**

Create `tests/test_cursor_harness.py`:

```python
import json

from sdlc.harness.adapters import CursorHarness, HarnessRequest, HARNESSES
from sdlc.harness.session import digest_of
from sdlc.models import HarnessKind


def test_cursor_parse_extracts_tokens_and_cost():
    payload = {"type": "result", "session_id": "cur1",
               "total_cost_usd": 0.07, "result": "done",
               "usage": {"input_tokens": 900, "output_tokens": 42}}
    res = CursorHarness().parse(json.dumps(payload), 0)
    assert res.session_id == "cur1"
    assert res.cost_usd == 0.07
    assert res.input_tokens == 900
    assert res.output_tokens == 42
    assert res.harness == HarnessKind.CURSOR


def test_cursor_parse_raw_fallback_on_non_json():
    res = CursorHarness().parse("not json at all", 1)
    assert res.summary == "not json at all"


def test_cursor_normalise_session_yields_canonical_events():
    stream = "\n".join([
        json.dumps({"type": "system", "session_id": "cur1",
                    "model": "sonnet-4.5"}),
        json.dumps({"type": "assistant", "session_id": "cur1", "message": {
            "content": [
                {"type": "text", "text": "let me edit"},
                {"type": "tool_use", "name": "edit_file",
                 "input": {"path": "app.py"}},
                {"type": "tool_use", "name": "run_terminal_cmd",
                 "input": {"command": "pytest"}},
            ]}}),
        json.dumps({"type": "result", "session_id": "cur1", "result": "ok",
                    "usage": {"input_tokens": 5, "output_tokens": 1}}),
    ])
    sess = CursorHarness().normalise_session(stream)
    assert sess.model == "sonnet-4.5"
    kinds = [e.kind for e in sess.events]
    assert "model_turn" in kinds
    assert "file_write" in kinds
    assert "command" in kinds
    dig = digest_of(sess)
    assert dig.files_written == 1
    assert dig.model_turns == 1


def test_cursor_build_cmd_headless_flags():
    cmd = CursorHarness().build_cmd(HarnessRequest(
        prompt="do stuff", cwd="/tmp/wt", model="sonnet-4.5",
        session_id="cur1", extra_args=["--x"]))
    assert cmd[0] == "cursor-agent"
    assert "-p" in cmd and "do stuff" in cmd
    assert "--output-format" in cmd and "stream-json" in cmd
    assert "--model" in cmd and "sonnet-4.5" in cmd
    assert "--resume" in cmd and "cur1" in cmd
    assert "--force" in cmd
    assert "--x" in cmd


def test_cursor_registered_in_harnesses():
    assert isinstance(HARNESSES[HarnessKind.CURSOR], CursorHarness)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_cursor_harness.py -v`
Expected: FAIL at collection — `ImportError: cannot import name 'CursorHarness'`.

- [ ] **Step 4: Implement `CursorHarness`**

In `src/sdlc/harness/adapters.py`, add the class immediately **before** the `HARNESSES` dict (currently line 489). It mirrors `ClaudeCodeHarness`; the `_TOOL_MAP` keys and `usage`/`total_cost_usd` field names are Cursor's documented schema (verify against a real transcript before the live axis is trusted — spec §5):

```python
class CursorHarness(CodingHarness):
    kind = HarnessKind.CURSOR
    cli = "cursor-agent"
    # E-24 pin: None = declared-but-unpinned. Set once the CLI is installed
    # and a real `cursor-agent --version` can be captured. A None pin is
    # skipped by check_harness_versions (no spurious drift warning).
    expected_version = None

    def __init__(self, force: bool = True):
        # Headless auto-approve of edits/commands (≈ claude --permission-mode
        # acceptEdits / opencode --auto). Without it a non-interactive run
        # blocks on an approval that never arrives -> empty diff.
        self.force = force

    def build_cmd(self, req: HarnessRequest) -> list[str]:
        # cursor-agent mirrors Claude Code's Agent-SDK stream-json output.
        cmd = ["cursor-agent", "-p", req.prompt,
               "--output-format", "stream-json"]
        if req.model:
            cmd += ["--model", req.model]
        if req.session_id:
            cmd += ["--resume", req.session_id]
        if self.force:
            cmd.append("--force")
        return cmd + req.extra_args

    def parse(self, stdout: str, exit_code: int) -> HarnessRunResult:
        session_id = cost = summary = None
        input_tokens = output_tokens = None
        payload = None
        for ln in stdout.strip().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                ev = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict) and ev.get("type") == "result":
                payload = ev
        if payload is not None:
            session_id = payload.get("session_id")
            cost = payload.get("total_cost_usd")   # ASSUMPTION: may be absent
                                                    # -> cursor cells are
                                                    # quality-only (spec §5)
            summary = payload.get("result") or payload.get("content")
            usage = payload.get("usage") or {}
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
        else:
            _log.warning("cursor parse: no result event in stream, falling "
                         "back to raw stdout as summary")
            summary = stdout
        return HarnessRunResult(
            harness=self.kind, session_id=session_id, exit_code=exit_code,
            summary=(summary or "")[:SUMMARY_MAX], cost_usd=cost,
            input_tokens=input_tokens, output_tokens=output_tokens,
        )

    # Cursor tool name -> canonical event kind + which input field is the
    # target. ASSUMPTION (spec §5): confirm these names against a real
    # `cursor-agent --output-format stream-json` transcript before trusting
    # the live cursor axis. Unmapped tools degrade to a generic tool_call.
    _TOOL_MAP = {
        "read_file": ("file_read", "path"),
        "edit_file": ("file_write", "path"),
        "write": ("file_write", "path"),
        "run_terminal_cmd": ("command", "command"),
        "shell": ("command", "command"),
    }

    def normalise_session(self, stdout: str) -> HarnessSession:
        events: list[SessionEvent] = []
        session_id = model = None
        cost = in_tok = out_tok = None
        for ln in stdout.strip().splitlines():
            try:
                ev = json.loads(ln.strip())
            except json.JSONDecodeError:
                continue
            if not isinstance(ev, dict):
                continue
            session_id = session_id or ev.get("session_id")
            etype = ev.get("type")
            if etype == "system":
                model = model or ev.get("model")
            elif etype in ("assistant", "user"):
                msg = ev.get("message") or {}
                for block in msg.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text" and block.get("text"):
                        events.append(SessionEvent(kind="model_turn",
                                                   text=block["text"]))
                    elif btype == "tool_use":
                        name = block.get("name") or "tool"
                        kind, field = self._TOOL_MAP.get(name, ("tool_call", ""))
                        inp = block.get("input") or {}
                        target = inp.get(field) if field else json.dumps(inp)[:500]
                        events.append(SessionEvent(kind=kind, tool=name,
                                                   target=target))
                    elif btype == "tool_result":
                        content = block.get("content")
                        if isinstance(content, list):
                            content = " ".join(
                                c.get("text", "") for c in content
                                if isinstance(c, dict))
                        events.append(SessionEvent(
                            kind="tool_result",
                            exit_code=1 if block.get("is_error") else None,
                            text=(content or "")[:2000] or None))
            elif etype == "result":
                usage = ev.get("usage") or {}
                cost = ev.get("total_cost_usd")
                in_tok = usage.get("input_tokens")
                out_tok = usage.get("output_tokens")
                events.append(SessionEvent(kind="result",
                                           text=(ev.get("result") or "")[:2000]))
        return HarnessSession(harness=self.kind, session_id=session_id,
                              model=model, events=events, cost_usd=cost,
                              input_tokens=in_tok, output_tokens=out_tok)
```

Then extend the `HARNESSES` registry (currently lines 489-492):

```python
HARNESSES: dict[HarnessKind, CodingHarness] = {
    HarnessKind.CLAUDE_CODE: ClaudeCodeHarness(),
    HarnessKind.OPENCODE: OpenCodeHarness(),
    HarnessKind.CURSOR: CursorHarness(),
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_cursor_harness.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/models.py src/sdlc/harness/adapters.py tests/test_cursor_harness.py
git commit -m "feat(harness): cursor-agent adapter, registered in HARNESSES (E-35)"
```

---

### Task 2: Version-pin-at-boot check (folded E-24)

**Files:**
- Modify: `src/sdlc/harness/adapters.py` (imports; `cli`/`expected_version`/`version_cmd` on `CodingHarness`; pins on `ClaudeCodeHarness`/`OpenCodeHarness`; new `check_harness_versions`)
- Modify: `src/sdlc/worker.py` (call it after `validate_registry`, near line 58)
- Test: `tests/test_cursor_harness.py` (append)

**Interfaces:**
- Consumes: `HARNESSES`, `_log`, `shutil` (already imported), plus new `subprocess`/`re` imports.
- Produces: `CodingHarness.cli: str`, `CodingHarness.expected_version: str | None`, `CodingHarness.version_cmd() -> list[str]`; `check_harness_versions(harnesses=None) -> None`.

- [ ] **Step 1: Write the failing version-check tests**

Append to `tests/test_cursor_harness.py`:

```python
import logging

from sdlc.harness.adapters import check_harness_versions


def test_version_check_warns_on_drift(monkeypatch, caplog):
    from sdlc.harness import adapters
    monkeypatch.setattr(adapters.shutil, "which", lambda c: "/usr/bin/" + c)

    class _Res:
        stdout = "9.9.9 (drifted)"
    monkeypatch.setattr(adapters.subprocess, "run", lambda *a, **k: _Res())
    caplog.set_level(logging.WARNING, logger="sdlc.harness.adapters")
    check_harness_versions()   # claude pinned 2.1.218 vs 9.9.9 -> drift
    assert any("version drift" in r.message for r in caplog.records)


def test_version_check_skips_when_cli_absent(monkeypatch, caplog):
    from sdlc.harness import adapters
    monkeypatch.setattr(adapters.shutil, "which", lambda c: None)
    caplog.set_level(logging.WARNING, logger="sdlc.harness.adapters")
    check_harness_versions()
    assert not any("version drift" in r.message for r in caplog.records)


def test_version_check_silent_on_match(monkeypatch, caplog):
    from sdlc.harness import adapters
    monkeypatch.setattr(adapters.shutil, "which", lambda c: "/usr/bin/" + c)
    versions = {"claude": "2.1.218 (Claude Code)", "opencode": "1.18.4",
                "cursor-agent": "0.0.0"}

    def _run(cmd, *a, **k):
        class _R:
            stdout = versions.get(cmd[0], "0.0.0")
        return _R()
    monkeypatch.setattr(adapters.subprocess, "run", _run)
    caplog.set_level(logging.WARNING, logger="sdlc.harness.adapters")
    check_harness_versions()   # claude+opencode match pins; cursor unpinned
    assert not any("version drift" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_cursor_harness.py -k version -v`
Expected: FAIL at collection — `ImportError: cannot import name 'check_harness_versions'`.

- [ ] **Step 3: Add version metadata + the check helper**

In `src/sdlc/harness/adapters.py`, add two imports near the top (with the existing `import shutil`, lines 17-22):

```python
import re
import subprocess
```

Extend the `CodingHarness` ABC (currently starts line 121) with class-level version metadata, right under `kind`:

```python
class CodingHarness(ABC):
    kind: HarnessKind
    cli: str = ""                          # executable name on PATH
    expected_version: str | None = None    # E-24 pin; None = declared-unpinned

    def version_cmd(self) -> list[str]:
        return [self.cli, "--version"]
```

Set the pins on the two existing adapters (verbatim from Global Constraints). On `ClaudeCodeHarness` (currently line 229-230), under `kind = HarnessKind.CLAUDE_CODE`:

```python
class ClaudeCodeHarness(CodingHarness):
    kind = HarnessKind.CLAUDE_CODE
    cli = "claude"
    expected_version = "2.1.218"
```

On `OpenCodeHarness` (currently line 346-347), under `kind = HarnessKind.OPENCODE`:

```python
class OpenCodeHarness(CodingHarness):
    kind = HarnessKind.OPENCODE
    cli = "opencode"
    expected_version = "1.18.4"
```

Add the helper immediately **after** the `HARNESSES` dict (end of file):

```python
_VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def check_harness_versions(
        harnesses: dict[HarnessKind, CodingHarness] | None = None) -> None:
    """E-24 (folded into E-35): warn when an installed harness CLI has drifted
    from its pinned version — the failure mode where a silent CLI upgrade
    breaks an adapter's parse. Never raises (a patch bump must not brick the
    worker). Skips silently when the CLI is absent (CI/fakes) or unpinned."""
    for h in (harnesses or HARNESSES).values():
        if not h.expected_version or not h.cli:
            continue
        if shutil.which(h.cli) is None:
            _log.debug("harness version check: %s not on PATH, skipping", h.cli)
            continue
        try:
            out = subprocess.run(h.version_cmd(), capture_output=True,
                                 text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as e:
            _log.debug("harness version check: %s --version failed: %s",
                       h.cli, e)
            continue
        m = _VERSION_RE.search(out.stdout or "")
        found = m.group(1) if m else None
        if found != h.expected_version:
            _log.warning("harness version drift: %s is %s, pinned %s "
                         "(adapter parse may break; capture a fresh transcript "
                         "and update the pin)", h.cli, found, h.expected_version)
        else:
            _log.debug("harness version ok: %s %s", h.cli, found)
```

- [ ] **Step 4: Run the version tests to verify they pass**

Run: `python -m pytest tests/test_cursor_harness.py -k version -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Wire the check into worker boot**

In `src/sdlc/worker.py`, add the import (near line 34, beside `from .agents.loader import ...`):

```python
from .harness.adapters import check_harness_versions
```

Then call it in `main()` immediately after the `validate_registry` line (currently line 58):

```python
    # Fail closed: a registry that violates the ADR-6 family-inequality
    # invariant must never boot a worker (FR-204/US-5).
    validate_registry(load_registry())
    # E-24 (via E-35): warn — not fail — on harness CLI version drift.
    check_harness_versions()
```

- [ ] **Step 6: Run the full new suite + the existing harness suite**

Run: `python -m pytest tests/test_cursor_harness.py tests/test_harness_parse.py -v`
Expected: PASS (all cursor tests + all existing harness-parse tests still green).

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/harness/adapters.py src/sdlc/worker.py tests/test_cursor_harness.py
git commit -m "feat(harness): warn-on-drift version pin at boot for all harnesses (E-24 via E-35)"
```

---

## Notes for the implementer

- **Do not** add `HarnessKind.CURSOR` to any `benchmarks/cases/*/case.yaml` `harnesses:` list. Availability is the deliverable; enabling a live cursor cell waits on the CLI being installed + authenticated.
- The `_TOOL_MAP` keys and the `total_cost_usd`/`usage` field names are Cursor's *documented* schema. They are correct for building and unit-testing the adapter, but the spec (§5) flags them for confirmation against a real `cursor-agent --output-format stream-json` transcript before the live cursor axis is trusted. The code comments say the same — leave them.
- `check_harness_versions()` uses blocking `subprocess.run`; that is intentional — it runs once at boot before the Temporal `Worker` starts, so briefly blocking the event loop is fine.
