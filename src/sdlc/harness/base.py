"""Base harness abstraction and runtime environment.

A harness executes an autonomous coding task inside a git worktree.
All adapters inherit from CodingHarness and normalize to HarnessRunResult.
They are invoked from a Temporal *activity* (never from workflow code).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..core.models import HarnessKind
from ..process import kill_process_tree
from .containment import (
    Policy,
)
from .models import (
    ContainmentLayer,
    ContainmentReport,
    DeferredToolUse,
    HarnessRunResult,
    HarnessSession,
    ToolDenial,
    ToolGrant,
)

SUMMARY_MAX = 4000  # keep Temporal payloads small

_log = logging.getLogger(__name__)

# Best-effort model → context window (tokens). Substring match; extend as
# needed. Used only to compute the context ceiling (Finding #7); unknown
# models fall back to the resume counter.
CONTEXT_WINDOWS = {
    "sonnet": 200_000,
    "opus": 200_000,
    "haiku": 200_000,
    "gpt-5": 400_000,
    "glm": 1_000_000,
}


def context_window_for(model: str | None) -> int | None:
    if not model:
        return None
    m = model.lower()
    for key, win in CONTEXT_WINDOWS.items():
        if key in m:
            return win
    return None


def _split_reason(text: str) -> tuple[str, str]:
    """Split the hook's `[rule-id] reason` back apart."""
    if text.startswith("[") and "] " in text:
        rid, _, rest = text[1:].partition("] ")
        return rid, rest
    return "unknown", text


# Env allowlist (Finding #8): the harness receives ONLY these vars from the
# worker environment, plus credentials deliberately injected via req.env.
# Never the worker's full os.environ (that is a bigger secret channel than
# the prompt). Covers POSIX + Windows toolchain essentials.
ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TMP",
    "TEMP",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "USERPROFILE",
    "PATHEXT",
    "COMSPEC",
    "GIT_EXEC_PATH",
    "GIT_SSH",
    "SSH_AUTH_SOCK",
    # Without these, Windows' Python install manager (`py install`) can't
    # find its real cache/install root and silently falls back to a
    # relative "Python/" directory inside the task's cwd — which then gets
    # swept into the checkpoint commit by `git add -A` and collides with
    # integration's own copy of the same fallback during merge.
    "LOCALAPPDATA",
    "APPDATA",
)


def build_env(
    req_env: dict[str, str], allowlist: tuple[str, ...] = ENV_ALLOWLIST
) -> dict[str, str]:
    """Curated child environment: allowlisted worker vars, then the
    request's injected (repo-scoped, short-TTL) credentials."""
    env = {k: os.environ[k] for k in allowlist if k in os.environ}
    env.update(req_env)
    return env


@dataclass
class HarnessRequest:
    prompt: str
    cwd: str  # the task's git worktree
    model: str | None = None
    session_id: str | None = None  # resume/continue a prior run
    timeout_s: int = 3600
    env: dict[str, str] = field(default_factory=dict)
    extra_args: list[str] = field(default_factory=list)
    # E-88 step 2 §A: the root the FENCE measures against, when it differs
    # from where the process runs. A non-lead crew role runs with cwd = the
    # worktree (so it can read the diff it is criticising) and write_root =
    # its orchestration directory (so it can write nowhere else). None means
    # "the same as cwd", which is every non-crew caller.
    write_root: str | None = None
    # C2: whether this is a REPAIR attempt (attempt >= 2 in the code stage's
    # fix loop, including the operator-REVISE continuation), which activates
    # `phase: repair` policy rules -- the contract's test files. Set by the
    # LOOP, never inferred here: both CrewTurnInput construction sites
    # hardcode attempt=1, so an activity-side inference would silently
    # unfreeze every crew repair attempt. A thawed attempt sets this back to
    # False for exactly one attempt.
    repair: bool = False


def _log_live_event(line: str) -> None:
    """Best-effort live logging of one opencode --format json event line as
    it streams. Never raises: a line that doesn't parse (e.g. Claude Code's
    single final JSON payload, which isn't line-delimited) is silently
    skipped — parse-time failure logging is handled separately in parse()."""
    line = line.strip()
    if not line:
        return
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return
    if not isinstance(ev, dict):
        return
    ev_type = ev.get("type")
    session_id = ev.get("sessionID") or ev.get("session_id")
    if ev_type == "step_start":
        _log.info("harness step_start session_id=%s", session_id)
    elif ev_type == "step_finish":
        part = ev.get("part")
        if not isinstance(part, dict):
            part = {}
        tokens = part.get("tokens")
        if not isinstance(tokens, dict):
            tokens = {}
        _log.info(
            "harness step_finish session_id=%s input_tokens=%s output_tokens=%s cost_usd=%s",
            session_id,
            tokens.get("input"),
            tokens.get("output"),
            part.get("cost"),
        )
    elif ev_type == "text":
        part = ev.get("part")
        if not isinstance(part, dict):
            part = {}
        _log.debug("harness text session_id=%s chars=%d", session_id, len(part.get("text") or ""))


class CodingHarness(ABC):
    kind: HarnessKind
    cli: str = ""  # executable name on PATH
    expected_version: str | None = None  # E-24 pin; None = declared-unpinned

    def version_cmd(self) -> list[str]:
        return [self.cli, "--version"]

    @abstractmethod
    def build_cmd(self, req: HarnessRequest) -> list[str]: ...

    @abstractmethod
    def parse(self, stdout: str, exit_code: int) -> HarnessRunResult: ...

    def normalise_session(self, stdout: str) -> HarnessSession:
        """Canonical transcript from this harness's stdout stream (ADR-16:
        normalisation is the adapter's job). Base default: metadata-only
        session with no events — a harness without a normaliser degrades
        to digest-of-nothing rather than failing capture."""
        return HarnessSession(harness=self.kind)

    # ADR-17: what this CLI can actually enforce. A harness declaring an
    # empty set fails closed when containment is enabled, rather than
    # running unpoliced and looking contained.
    containment: frozenset[ContainmentLayer] = frozenset()

    # E-17: whether this CLI can SUSPEND a tool call for a human decision.
    # claude has `defer`; nothing else does. A harness declaring False keeps
    # escalate rules as plain denials, reported via rules_escalatable.
    supports_escalation: bool = False

    def apply_containment(
        self, policy: Policy, req: HarnessRequest, grants: list[ToolGrant] | None = None
    ) -> ContainmentReport:
        """Compile `policy` into this CLI's own mechanisms, mutating `req`.
        Base default: enforce nothing and say so."""
        return ContainmentReport(
            enabled=True, layers_active=[], rules_unenforceable=[r.id for r in policy.rules]
        )

    def normalise_deferral(self, stdout: str) -> DeferredToolUse | None:
        """The tool call this run suspended at, if any (E-17, mirroring
        normalise_denials). Base default: this harness cannot suspend."""
        return None

    def normalise_denials(self, stdout: str) -> list[ToolDenial]:
        """Blocked tool calls from this harness's stream (ADR-17, mirroring
        normalise_session). Base default: none reported."""
        return []

    async def run(self, req: HarnessRequest, heartbeat=None) -> HarnessRunResult:
        cmd = self.build_cmd(req)
        # Resolve via PATH — Windows npm shims are .cmd files that
        # CreateProcess can't find without an explicit extension.
        resolved = shutil.which(cmd[0])
        if resolved:
            cmd[0] = resolved
        _log.debug(
            "harness start kind=%s model=%s session_id=%s cwd=%s",
            self.kind.value,
            req.model,
            req.session_id,
            req.cwd,
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=req.cwd,
            env=build_env(req.env),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10_000_000,  # opencode text events can exceed the 64KB
            # default StreamReader line limit
            start_new_session=True,  # C6: makes the whole tree killable as
            # a POSIX process group; a documented no-op on Windows
        )

        async def _pump() -> bytes:
            chunks: list[bytes] = []
            buf = b""
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    _log_live_event(line.decode(errors="replace"))
                if heartbeat:
                    heartbeat()  # keep the Temporal activity alive
            if buf.strip():
                _log_live_event(buf.decode(errors="replace"))
            return b"".join(chunks)

        async def _pump_stderr() -> str:
            # Drained concurrently with stdout — an unread stderr pipe can
            # fill its OS buffer and deadlock the child if it writes enough.
            chunks: list[bytes] = []
            size = 0
            assert proc.stderr is not None
            while True:
                chunk = await proc.stderr.read(65536)
                if not chunk:
                    break
                if size < SUMMARY_MAX:
                    chunks.append(chunk)
                    size += len(chunk)
            return b"".join(chunks).decode(errors="replace")[:SUMMARY_MAX]

        start = time.monotonic()
        try:
            stdout_b, stderr_s, _ = await asyncio.wait_for(
                asyncio.gather(_pump(), _pump_stderr(), proc.wait()),
                timeout=req.timeout_s,
            )
        except TimeoutError:
            await asyncio.shield(kill_process_tree(proc))
            _log.warning("harness timeout kind=%s cwd=%s cmd=%s", self.kind.value, req.cwd, cmd)
            raise
        except asyncio.CancelledError:
            # Temporal activity cancellation. shield() so a second cancel
            # landing mid-cleanup can't abort the kill before it completes.
            await asyncio.shield(kill_process_tree(proc))
            raise
        except Exception:
            await asyncio.shield(kill_process_tree(proc))
            raise
        duration_s = time.monotonic() - start

        result = self.parse(stdout_b.decode(errors="replace"), proc.returncode or 0)
        # E-38: keep the raw stream for activity-side capture. PrivateAttr —
        # never serialized, never enters workflow state.
        result._raw_stdout = stdout_b.decode(errors="replace")
        if result.context_window is None:
            result.context_window = context_window_for(req.model)

        _log.info(
            "harness done kind=%s exit_code=%s session_id=%s "
            "duration_s=%.1f input_tokens=%s output_tokens=%s cost_usd=%s",
            self.kind.value,
            result.exit_code,
            result.session_id,
            duration_s,
            result.input_tokens,
            result.output_tokens,
            result.cost_usd,
        )
        if result.exit_code != 0 or stderr_s:
            _log.warning(
                "harness stderr kind=%s exit_code=%s stderr=%s",
                self.kind.value,
                result.exit_code,
                stderr_s,
            )
        return result
