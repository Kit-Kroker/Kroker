"""Coding-harness abstraction.

A harness executes an autonomous coding task inside a git worktree.
Both adapters normalize to HarnessRunResult. They are invoked from a
Temporal *activity* (never from workflow code) — see activities.py.

Asymmetries handled here:
  * claude:   `claude -p "<prompt>" --output-format json`; stdin supported;
              resume with `--resume <session_id>` (scoped to cwd/worktree).
  * opencode: `opencode run "<prompt>" --format json -m provider/model`;
              prompt is a positional arg (there is NO -p flag);
              continue with `-s <session_id>`; optional `--attach <url>`
              to reuse a warm `opencode serve` instance.
"""
from __future__ import annotations

import asyncio
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..models import HarnessKind, HarnessRunResult

SUMMARY_MAX = 4000  # keep Temporal payloads small

# Best-effort model → context window (tokens). Substring match; extend as
# needed. Used only to compute the context ceiling (Finding #7); unknown
# models fall back to the resume counter.
CONTEXT_WINDOWS = {
    "sonnet": 200_000,
    "opus": 200_000,
    "haiku": 200_000,
    "gpt-5": 400_000,
}


def context_window_for(model: str | None) -> int | None:
    if not model:
        return None
    m = model.lower()
    for key, win in CONTEXT_WINDOWS.items():
        if key in m:
            return win
    return None


# Env allowlist (Finding #8): the harness receives ONLY these vars from the
# worker environment, plus credentials deliberately injected via req.env.
# Never the worker's full os.environ (that is a bigger secret channel than
# the prompt). Covers POSIX + Windows toolchain essentials.
ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP",
    "SYSTEMROOT", "SYSTEMDRIVE", "USERPROFILE", "PATHEXT", "COMSPEC",
    "GIT_EXEC_PATH", "GIT_SSH", "SSH_AUTH_SOCK",
)


def build_env(req_env: dict[str, str],
              allowlist: tuple[str, ...] = ENV_ALLOWLIST) -> dict[str, str]:
    """Curated child environment: allowlisted worker vars, then the
    request's injected (repo-scoped, short-TTL) credentials."""
    env = {k: os.environ[k] for k in allowlist if k in os.environ}
    env.update(req_env)
    return env


@dataclass
class HarnessRequest:
    prompt: str
    cwd: str                              # the task's git worktree
    model: str | None = None
    session_id: str | None = None         # resume/continue a prior run
    timeout_s: int = 3600
    env: dict[str, str] = field(default_factory=dict)
    extra_args: list[str] = field(default_factory=list)


class CodingHarness(ABC):
    kind: HarnessKind

    @abstractmethod
    def build_cmd(self, req: HarnessRequest) -> list[str]: ...

    @abstractmethod
    def parse(self, stdout: str, exit_code: int) -> HarnessRunResult: ...

    async def run(self, req: HarnessRequest,
                  heartbeat=None) -> HarnessRunResult:
        cmd = self.build_cmd(req)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=req.cwd,
            env=build_env(req.env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def _pump() -> bytes:
            chunks: list[bytes] = []
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if heartbeat:
                    heartbeat()          # keep the Temporal activity alive
            return b"".join(chunks)

        try:
            stdout_b, _ = await asyncio.wait_for(
                asyncio.gather(_pump(), proc.wait()), timeout=req.timeout_s
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise

        result = self.parse(stdout_b.decode(errors="replace"),
                            proc.returncode or 0)
        if result.context_window is None:
            result.context_window = context_window_for(req.model)
        return result


class ClaudeCodeHarness(CodingHarness):
    kind = HarnessKind.CLAUDE_CODE

    def __init__(self, allowed_tools: str = "Read,Edit,Write,Bash",
                 permission_mode: str = "acceptEdits"):
        self.allowed_tools = allowed_tools
        self.permission_mode = permission_mode

    def build_cmd(self, req: HarnessRequest) -> list[str]:
        cmd = [
            "claude", "-p", req.prompt,
            "--output-format", "json",
            "--allowedTools", self.allowed_tools,
            "--permission-mode", self.permission_mode,
        ]
        if req.model:
            cmd += ["--model", req.model]
        if req.session_id:
            cmd += ["--resume", req.session_id]
        return cmd + req.extra_args

    def parse(self, stdout: str, exit_code: int) -> HarnessRunResult:
        session_id = cost = summary = None
        input_tokens = output_tokens = None
        try:
            payload = json.loads(stdout.strip().splitlines()[-1])
            session_id = payload.get("session_id")
            cost = payload.get("total_cost_usd")
            summary = payload.get("result") or payload.get("content")
            usage = payload.get("usage") or {}
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
        except (json.JSONDecodeError, IndexError):
            summary = stdout
        return HarnessRunResult(
            harness=self.kind, session_id=session_id, exit_code=exit_code,
            summary=(summary or "")[:SUMMARY_MAX], cost_usd=cost,
            input_tokens=input_tokens, output_tokens=output_tokens,
        )


class OpenCodeHarness(CodingHarness):
    kind = HarnessKind.OPENCODE

    def __init__(self, attach_url: str | None = None):
        # Point at a running `opencode serve` to skip MCP cold boots.
        self.attach_url = attach_url

    def build_cmd(self, req: HarnessRequest) -> list[str]:
        cmd = ["opencode", "run"]
        if req.model:
            cmd += ["-m", req.model]
        if req.session_id:
            cmd += ["-s", req.session_id]
        if self.attach_url:
            cmd += ["--attach", self.attach_url]
        cmd += ["--format", "json"]
        cmd += req.extra_args
        cmd.append(req.prompt)            # positional, must come last
        return cmd

    def parse(self, stdout: str, exit_code: int) -> HarnessRunResult:
        session_id = summary = None
        input_tokens = output_tokens = None
        try:
            payload = json.loads(stdout.strip().splitlines()[-1])
            session_id = payload.get("sessionID") or payload.get("session_id")
            summary = payload.get("text") or payload.get("result")
            usage = payload.get("usage") or {}
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
        except (json.JSONDecodeError, IndexError):
            summary = stdout
        return HarnessRunResult(
            harness=self.kind, session_id=session_id, exit_code=exit_code,
            summary=(summary or "")[:SUMMARY_MAX],
            input_tokens=input_tokens, output_tokens=output_tokens,
        )


HARNESSES: dict[HarnessKind, CodingHarness] = {
    HarnessKind.CLAUDE_CODE: ClaudeCodeHarness(),
    HarnessKind.OPENCODE: OpenCodeHarness(),
}
